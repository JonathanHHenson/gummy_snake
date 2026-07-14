use super::*;
use std::hash::{Hash, Hasher};
use std::io::{Read, Seek, SeekFrom};
use std::time::UNIX_EPOCH;

/// Native decoded sample bytes retained by the process-wide source cache.
pub const SAMPLE_SOURCE_CACHE_BUDGET_BYTES: usize = 64 * 1024 * 1024;
/// Target-rate planar bytes retained by the process-wide resample cache.
pub const SAMPLE_RESAMPLE_CACHE_BUDGET_BYTES: usize = 128 * 1024 * 1024;
const RESAMPLER_RADIUS: isize = 16;
const RESAMPLER_CUTOFF_MARGIN: f64 = 0.94;

#[derive(Clone, Debug)]
pub(crate) struct SampleSource {
    pub(crate) left: Arc<Vec<f64>>,
    pub(crate) right: Arc<Vec<f64>>,
    pub(crate) duration: f64,
    pub(crate) stereo: bool,
    pub(crate) sample_rate: u32,
}

impl SampleSource {
    pub(crate) fn len(&self) -> usize {
        self.left.len().min(self.right.len())
    }

    fn byte_len(&self) -> usize {
        self.left
            .capacity()
            .saturating_add(self.right.capacity())
            .saturating_mul(std::mem::size_of::<f64>())
    }
}

#[derive(Clone, Debug, Eq)]
struct SampleAssetIdentity {
    canonical_path: String,
    byte_len: u64,
    modified_nanos: u128,
}

impl PartialEq for SampleAssetIdentity {
    fn eq(&self, other: &Self) -> bool {
        self.canonical_path == other.canonical_path
            && self.byte_len == other.byte_len
            && self.modified_nanos == other.modified_nanos
    }
}

impl Hash for SampleAssetIdentity {
    fn hash<H: Hasher>(&self, state: &mut H) {
        self.canonical_path.hash(state);
        self.byte_len.hash(state);
        self.modified_nanos.hash(state);
    }
}

impl SampleAssetIdentity {
    fn from_path(path: &str) -> SynthResult<Self> {
        let canonical = fs::canonicalize(path).map_err(|error| {
            SynthError::new(format!("Could not resolve sample asset {path}: {error}"))
        })?;
        let metadata = fs::metadata(&canonical).map_err(|error| {
            SynthError::new(format!(
                "Could not inspect sample asset {}: {error}",
                canonical.display()
            ))
        })?;
        let modified_nanos = metadata
            .modified()
            .ok()
            .and_then(|modified| modified.duration_since(UNIX_EPOCH).ok())
            .map_or(0, |duration| duration.as_nanos());
        Ok(Self {
            canonical_path: canonical.to_string_lossy().into_owned(),
            byte_len: metadata.len(),
            modified_nanos,
        })
    }
}

#[derive(Clone)]
struct CacheEntry {
    source: Arc<SampleSource>,
    bytes: usize,
    generation: u64,
}

#[derive(Clone, Debug, Eq, Hash, PartialEq)]
struct ResampleKey {
    identity: SampleAssetIdentity,
    target_rate: u32,
}

#[derive(Clone, Copy, Debug, Default, Eq, PartialEq)]
pub struct SampleCacheDiagnostics {
    pub source_hits: u64,
    pub source_misses: u64,
    pub source_evictions: u64,
    pub source_bytes: usize,
    pub source_entries: usize,
    pub source_budget_bytes: usize,
    pub resample_hits: u64,
    pub resample_misses: u64,
    pub resample_evictions: u64,
    pub resample_bytes: usize,
    pub resample_entries: usize,
    pub resample_budget_bytes: usize,
    pub stale_invalidations: u64,
    pub lock_contentions: u64,
}

#[derive(Default)]
struct SampleCacheState {
    sources: HashMap<SampleAssetIdentity, CacheEntry>,
    resamples: HashMap<ResampleKey, CacheEntry>,
    generation: u64,
    source_bytes: usize,
    resample_bytes: usize,
    source_hits: u64,
    source_misses: u64,
    source_evictions: u64,
    resample_hits: u64,
    resample_misses: u64,
    resample_evictions: u64,
    stale_invalidations: u64,
    lock_contentions: u64,
}

impl SampleCacheState {
    fn next_generation(&mut self) -> u64 {
        self.generation = self.generation.wrapping_add(1).max(1);
        self.generation
    }

    fn invalidate_stale_path(&mut self, current: &SampleAssetIdentity) {
        let stale_sources = self
            .sources
            .keys()
            .filter(|identity| {
                identity.canonical_path == current.canonical_path && *identity != current
            })
            .cloned()
            .collect::<Vec<_>>();
        let stale_resamples = self
            .resamples
            .keys()
            .filter(|key| {
                key.identity.canonical_path == current.canonical_path && key.identity != *current
            })
            .cloned()
            .collect::<Vec<_>>();
        for identity in stale_sources {
            if let Some(entry) = self.sources.remove(&identity) {
                self.source_bytes = self.source_bytes.saturating_sub(entry.bytes);
                self.stale_invalidations += 1;
            }
        }
        for key in stale_resamples {
            if let Some(entry) = self.resamples.remove(&key) {
                self.resample_bytes = self.resample_bytes.saturating_sub(entry.bytes);
                self.stale_invalidations += 1;
            }
        }
    }

    fn evict_sources_to_budget(&mut self) {
        while self.source_bytes > SAMPLE_SOURCE_CACHE_BUDGET_BYTES && self.sources.len() > 1 {
            let Some(oldest) = self
                .sources
                .iter()
                .min_by_key(|(_, entry)| entry.generation)
                .map(|(key, _)| key.clone())
            else {
                break;
            };
            if let Some(entry) = self.sources.remove(&oldest) {
                self.source_bytes = self.source_bytes.saturating_sub(entry.bytes);
                self.source_evictions += 1;
            }
        }
    }

    fn evict_resamples_to_budget(&mut self) {
        while self.resample_bytes > SAMPLE_RESAMPLE_CACHE_BUDGET_BYTES && self.resamples.len() > 1 {
            let Some(oldest) = self
                .resamples
                .iter()
                .min_by_key(|(_, entry)| entry.generation)
                .map(|(key, _)| key.clone())
            else {
                break;
            };
            if let Some(entry) = self.resamples.remove(&oldest) {
                self.resample_bytes = self.resample_bytes.saturating_sub(entry.bytes);
                self.resample_evictions += 1;
            }
        }
    }

    fn diagnostics(&self) -> SampleCacheDiagnostics {
        SampleCacheDiagnostics {
            source_hits: self.source_hits,
            source_misses: self.source_misses,
            source_evictions: self.source_evictions,
            source_bytes: self.source_bytes,
            source_entries: self.sources.len(),
            source_budget_bytes: SAMPLE_SOURCE_CACHE_BUDGET_BYTES,
            resample_hits: self.resample_hits,
            resample_misses: self.resample_misses,
            resample_evictions: self.resample_evictions,
            resample_bytes: self.resample_bytes,
            resample_entries: self.resamples.len(),
            resample_budget_bytes: SAMPLE_RESAMPLE_CACHE_BUDGET_BYTES,
            stale_invalidations: self.stale_invalidations,
            lock_contentions: self.lock_contentions,
        }
    }
}

fn sample_cache() -> &'static Mutex<SampleCacheState> {
    static SAMPLE_CACHE: OnceLock<Mutex<SampleCacheState>> = OnceLock::new();
    SAMPLE_CACHE.get_or_init(|| Mutex::new(SampleCacheState::default()))
}

fn lock_sample_cache() -> SynthResult<std::sync::MutexGuard<'static, SampleCacheState>> {
    match sample_cache().try_lock() {
        Ok(guard) => Ok(guard),
        Err(std::sync::TryLockError::WouldBlock) => {
            let mut guard = sample_cache()
                .lock()
                .map_err(|_| SynthError::new("synth sample cache lock was poisoned."))?;
            guard.lock_contentions += 1;
            Ok(guard)
        }
        Err(std::sync::TryLockError::Poisoned(_)) => {
            Err(SynthError::new("synth sample cache lock was poisoned."))
        }
    }
}

pub fn sample_cache_diagnostics() -> SampleCacheDiagnostics {
    sample_cache()
        .lock()
        .map(|cache| cache.diagnostics())
        .unwrap_or(SampleCacheDiagnostics {
            source_budget_bytes: SAMPLE_SOURCE_CACHE_BUDGET_BYTES,
            resample_budget_bytes: SAMPLE_RESAMPLE_CACHE_BUDGET_BYTES,
            ..SampleCacheDiagnostics::default()
        })
}

pub fn reset_sample_cache_diagnostics() {
    if let Ok(mut cache) = sample_cache().lock() {
        cache.source_hits = 0;
        cache.source_misses = 0;
        cache.source_evictions = 0;
        cache.resample_hits = 0;
        cache.resample_misses = 0;
        cache.resample_evictions = 0;
        cache.stale_invalidations = 0;
        cache.lock_contentions = 0;
    }
}

#[cfg(test)]
pub(crate) fn sample_cache_contains_path(path: &Path) -> bool {
    let canonical_path = fs::canonicalize(path)
        .unwrap_or_else(|_| path.to_path_buf())
        .to_string_lossy()
        .into_owned();
    sample_cache().lock().is_ok_and(|cache| {
        cache
            .sources
            .keys()
            .any(|identity| identity.canonical_path == canonical_path)
            || cache
                .resamples
                .keys()
                .any(|key| key.identity.canonical_path == canonical_path)
    })
}

/// Probe duration directly from WAV/FLAC metadata without decoding or resampling.
pub fn sample_duration(value: &SynthValue) -> SynthResult<f64> {
    let path = resolve_sample_path(value)?;
    probe_sample_file(&path).map(|metadata| metadata.duration)
}

pub(crate) fn sample_source(value: &SynthValue, sample_rate: u32) -> SynthResult<SampleSource> {
    if sample_rate == 0 {
        return Err(SynthError::new(
            "sample target rate must be greater than zero.",
        ));
    }
    let path = resolve_sample_path(value)?;
    cached_sample_file(&path, sample_rate)
}

fn resolve_sample_path(value: &SynthValue) -> SynthResult<String> {
    let sample_name = match value {
        SynthValue::List(values) => values.first(),
        other => Some(other),
    }
    .ok_or_else(|| SynthError::new("sample event does not specify a sample name."))?;
    if let SynthValue::String(path) = sample_name {
        if fs::metadata(path).is_ok() {
            return Ok(path.clone());
        }
    }
    let name = match sample_name {
        SynthValue::String(name) => name.trim_start_matches(':').to_owned(),
        _ => {
            return Err(SynthError::new(
                "sample event value must be a sample name or file path.",
            ))
        }
    };
    if let Some(path) = packaged_sample_path(&name) {
        return Ok(path.to_string_lossy().into_owned());
    }
    Err(SynthError::new(format!(
        "Sample {name:?} was not found. Provide an existing file path or install the packaged Sonic Pi sample assets."
    )))
}

pub(crate) fn packaged_sample_path(name: &str) -> Option<PathBuf> {
    let trimmed = name.trim_start_matches(':');
    if trimmed.is_empty() {
        return None;
    }
    let stem = Path::new(trimmed)
        .file_stem()
        .and_then(|value| value.to_str())
        .unwrap_or(trimmed);
    let file_names = [
        format!("{stem}.flac"),
        format!("{stem}.wav"),
        format!("{stem}.aif"),
        format!("{stem}.aiff"),
    ];
    for root in packaged_sample_roots() {
        for file_name in &file_names {
            let candidate = root.join(file_name);
            if fs::metadata(&candidate).is_ok() {
                return Some(candidate);
            }
        }
    }
    None
}

pub(crate) fn packaged_sample_roots() -> Vec<PathBuf> {
    let mut roots = Vec::new();
    if let Ok(root) = std::env::var("GUMMYSNAKE_SAMPLE_DIR") {
        roots.push(PathBuf::from(root));
    }
    if let Ok(current_dir) = std::env::current_dir() {
        for ancestor in current_dir.ancestors() {
            roots.push(ancestor.join("assets/samples/sonic_pi"));
            roots.push(ancestor.join("gummy_snake/assets/samples/sonic_pi"));
        }
    }
    if let Some(manifest_dir) = option_env!("CARGO_MANIFEST_DIR") {
        let manifest = PathBuf::from(manifest_dir);
        roots.push(manifest.join("../../assets/samples/sonic_pi"));
    }
    roots
}

pub(crate) fn cached_sample_file(path: &str, sample_rate: u32) -> SynthResult<SampleSource> {
    let identity = SampleAssetIdentity::from_path(path)?;
    let native = cached_native_source(&identity)?;
    if native.sample_rate == sample_rate {
        return Ok((*native).clone());
    }

    let key = ResampleKey {
        identity: identity.clone(),
        target_rate: sample_rate,
    };
    {
        let mut cache = lock_sample_cache()?;
        cache.invalidate_stale_path(&identity);
        let generation = cache.next_generation();
        if let Some(entry) = cache.resamples.get_mut(&key) {
            entry.generation = generation;
            let source = Arc::clone(&entry.source);
            cache.resample_hits += 1;
            return Ok((*source).clone());
        }
        cache.resample_misses += 1;
    }

    let resampled = Arc::new(resample_source(&native, sample_rate)?);
    let mut cache = lock_sample_cache()?;
    let generation = cache.next_generation();
    if let Some(entry) = cache.resamples.get_mut(&key) {
        entry.generation = generation;
        return Ok((*entry.source).clone());
    }
    let bytes = resampled.byte_len();
    if bytes > SAMPLE_RESAMPLE_CACHE_BUDGET_BYTES {
        return Err(SynthError::new(format!(
            "resampled asset {} requires {bytes} bytes, exceeding the sample resample cache budget of {SAMPLE_RESAMPLE_CACHE_BUDGET_BYTES} bytes.",
            identity.canonical_path
        )));
    }
    cache.resample_bytes = cache.resample_bytes.saturating_add(bytes);
    cache.resamples.insert(
        key,
        CacheEntry {
            source: Arc::clone(&resampled),
            bytes,
            generation,
        },
    );
    cache.evict_resamples_to_budget();
    Ok((*resampled).clone())
}

fn cached_native_source(identity: &SampleAssetIdentity) -> SynthResult<Arc<SampleSource>> {
    {
        let mut cache = lock_sample_cache()?;
        cache.invalidate_stale_path(identity);
        let generation = cache.next_generation();
        if let Some(entry) = cache.sources.get_mut(identity) {
            entry.generation = generation;
            let source = Arc::clone(&entry.source);
            cache.source_hits += 1;
            return Ok(source);
        }
        cache.source_misses += 1;
    }

    let decoded = Arc::new(load_sample_file_native(&identity.canonical_path)?);
    let mut cache = lock_sample_cache()?;
    cache.invalidate_stale_path(identity);
    let generation = cache.next_generation();
    if let Some(entry) = cache.sources.get_mut(identity) {
        entry.generation = generation;
        return Ok(Arc::clone(&entry.source));
    }
    let bytes = decoded.byte_len();
    if bytes > SAMPLE_SOURCE_CACHE_BUDGET_BYTES {
        return Err(SynthError::new(format!(
            "decoded asset {} requires {bytes} bytes, exceeding the sample source cache budget of {SAMPLE_SOURCE_CACHE_BUDGET_BYTES} bytes.",
            identity.canonical_path
        )));
    }
    cache.source_bytes = cache.source_bytes.saturating_add(bytes);
    cache.sources.insert(
        identity.clone(),
        CacheEntry {
            source: Arc::clone(&decoded),
            bytes,
            generation,
        },
    );
    cache.evict_sources_to_budget();
    Ok(decoded)
}

fn load_sample_file_native(path: &str) -> SynthResult<SampleSource> {
    let extension = Path::new(path)
        .extension()
        .and_then(|extension| extension.to_str())
        .unwrap_or_default()
        .to_ascii_lowercase();
    match extension.as_str() {
        "flac" => load_flac_sample_native(path),
        "wav" => load_wav_sample_native(path),
        unsupported => Err(SynthError::new(format!(
            "Unsupported sample format {unsupported:?} for {path}; expected WAV or FLAC."
        ))),
    }
}

fn load_wav_sample_native(path: &str) -> SynthResult<SampleSource> {
    let bytes = fs::read(path)
        .map_err(|err| SynthError::new(format!("Could not load WAV sample {path}: {err}")))?;
    let wav = decode_wav_stereo(&bytes)?;
    if wav.sample_rate == 0 {
        return Err(SynthError::new(format!(
            "Unsupported WAV sample rate 0 for {path}."
        )));
    }
    let duration = wav.left.len().min(wav.right.len()) as f64 / wav.sample_rate as f64;
    Ok(SampleSource {
        left: Arc::new(wav.left),
        right: Arc::new(wav.right),
        duration,
        stereo: wav.stereo,
        sample_rate: wav.sample_rate,
    })
}

fn load_flac_sample_native(path: &str) -> SynthResult<SampleSource> {
    let mut reader = claxon::FlacReader::open(path)
        .map_err(|err| SynthError::new(format!("Could not load FLAC sample {path}: {err}")))?;
    let streaminfo = reader.streaminfo();
    let source_rate = streaminfo.sample_rate;
    let channels = streaminfo.channels as usize;
    let bits_per_sample = streaminfo.bits_per_sample as i32;
    if source_rate == 0 || !matches!(channels, 1 | 2) || bits_per_sample <= 0 {
        return Err(SynthError::new(format!(
            "Unsupported FLAC sample format for {path}; expected mono or stereo PCM data with a positive sample rate."
        )));
    }
    let denom = 2_f64.powi(bits_per_sample - 1);
    let capacity = streaminfo.samples.unwrap_or(0) as usize;
    let mut left = Vec::with_capacity(capacity);
    let mut right = Vec::with_capacity(capacity);
    let mut channel = 0usize;
    let mut pending_left = 0.0;
    for sample in reader.samples() {
        let sample = sample
            .map_err(|err| SynthError::new(format!("Could not decode FLAC sample {path}: {err}")))?
            as f64
            / denom;
        if channels == 1 {
            left.push(sample);
            right.push(sample);
            continue;
        }
        if channel == 0 {
            pending_left = sample;
            channel = 1;
        } else {
            left.push(pending_left);
            right.push(sample);
            channel = 0;
        }
    }
    if channel != 0 {
        return Err(SynthError::new(format!(
            "Malformed FLAC sample {path}; incomplete stereo frame."
        )));
    }
    let duration = left.len().min(right.len()) as f64 / source_rate as f64;
    Ok(SampleSource {
        left: Arc::new(left),
        right: Arc::new(right),
        duration,
        stereo: channels == 2,
        sample_rate: source_rate,
    })
}

#[derive(Clone, Copy, Debug)]
struct SampleMetadata {
    duration: f64,
}

fn probe_sample_file(path: &str) -> SynthResult<SampleMetadata> {
    let extension = Path::new(path)
        .extension()
        .and_then(|extension| extension.to_str())
        .unwrap_or_default()
        .to_ascii_lowercase();
    match extension.as_str() {
        "wav" => probe_wav_file(path),
        "flac" => probe_flac_file(path),
        unsupported => Err(SynthError::new(format!(
            "Unsupported sample format {unsupported:?} for {path}; expected WAV or FLAC."
        ))),
    }
}

fn probe_wav_file(path: &str) -> SynthResult<SampleMetadata> {
    let mut file = fs::File::open(path)
        .map_err(|error| SynthError::new(format!("Could not probe WAV sample {path}: {error}")))?;
    let mut header = [0_u8; 12];
    file.read_exact(&mut header).map_err(|error| {
        SynthError::new(format!("Could not read WAV header for {path}: {error}"))
    })?;
    if &header[0..4] != b"RIFF" || &header[8..12] != b"WAVE" {
        return Err(SynthError::new(format!(
            "Could not probe WAV sample {path}: invalid RIFF/WAVE header."
        )));
    }

    let mut channels = None;
    let mut sample_rate = None;
    let mut bits_per_sample = None;
    let mut data_len = None;
    loop {
        let mut chunk_header = [0_u8; 8];
        match file.read_exact(&mut chunk_header) {
            Ok(()) => {}
            Err(error) if error.kind() == std::io::ErrorKind::UnexpectedEof => break,
            Err(error) => {
                return Err(SynthError::new(format!(
                    "Could not scan WAV chunks for {path}: {error}"
                )))
            }
        }
        let chunk_len = u32::from_le_bytes([
            chunk_header[4],
            chunk_header[5],
            chunk_header[6],
            chunk_header[7],
        ]);
        match &chunk_header[0..4] {
            b"fmt " => {
                if chunk_len < 16 {
                    return Err(SynthError::new(format!(
                        "WAV sample {path} has a malformed fmt chunk."
                    )));
                }
                let mut format = [0_u8; 16];
                file.read_exact(&mut format).map_err(|error| {
                    SynthError::new(format!("Could not read WAV format for {path}: {error}"))
                })?;
                let audio_format = u16::from_le_bytes([format[0], format[1]]);
                if audio_format != 1 {
                    return Err(SynthError::new(format!(
                        "Unsupported WAV encoding {audio_format} for {path}; expected integer PCM."
                    )));
                }
                channels = Some(u16::from_le_bytes([format[2], format[3]]));
                sample_rate = Some(u32::from_le_bytes([
                    format[4], format[5], format[6], format[7],
                ]));
                bits_per_sample = Some(u16::from_le_bytes([format[14], format[15]]));
                file.seek(SeekFrom::Current(i64::from(chunk_len - 16)))
                    .map_err(|error| {
                        SynthError::new(format!(
                            "Could not skip WAV format data for {path}: {error}"
                        ))
                    })?;
            }
            b"data" => {
                data_len = Some(chunk_len as usize);
                if channels.is_some() {
                    break;
                }
                file.seek(SeekFrom::Current(i64::from(chunk_len)))
                    .map_err(|error| {
                        SynthError::new(format!(
                            "Could not skip WAV sample data for {path}: {error}"
                        ))
                    })?;
            }
            _ => {
                file.seek(SeekFrom::Current(i64::from(chunk_len)))
                    .map_err(|error| {
                        SynthError::new(format!("Could not skip WAV chunk for {path}: {error}"))
                    })?;
            }
        }
        if chunk_len % 2 != 0 {
            file.seek(SeekFrom::Current(1)).map_err(|error| {
                SynthError::new(format!(
                    "Could not skip WAV chunk padding for {path}: {error}"
                ))
            })?;
        }
    }

    let channels = channels
        .ok_or_else(|| SynthError::new(format!("WAV sample {path} is missing its fmt chunk.")))?;
    let sample_rate = sample_rate
        .ok_or_else(|| SynthError::new(format!("WAV sample {path} is missing its sample rate.")))?;
    let bits_per_sample = bits_per_sample.ok_or_else(|| {
        SynthError::new(format!("WAV sample {path} is missing its sample depth."))
    })?;
    let data_len = data_len
        .ok_or_else(|| SynthError::new(format!("WAV sample {path} is missing its data chunk.")))?;
    if sample_rate == 0 || !matches!(channels, 1 | 2) || !matches!(bits_per_sample, 8 | 16 | 32) {
        return Err(SynthError::new(format!(
            "Unsupported WAV sample format for {path}; expected mono or stereo 8/16/32-bit PCM with a positive sample rate."
        )));
    }
    let frame_bytes = usize::from(channels) * usize::from(bits_per_sample.div_ceil(8));
    Ok(SampleMetadata {
        duration: (data_len / frame_bytes) as f64 / sample_rate as f64,
    })
}

fn probe_flac_file(path: &str) -> SynthResult<SampleMetadata> {
    let reader = claxon::FlacReader::open(path)
        .map_err(|error| SynthError::new(format!("Could not probe FLAC sample {path}: {error}")))?;
    let info = reader.streaminfo();
    if info.sample_rate == 0 || !matches!(info.channels, 1 | 2) {
        return Err(SynthError::new(format!(
            "Unsupported FLAC sample format for {path}; expected mono or stereo data with a positive sample rate."
        )));
    }
    let frames = info.samples.ok_or_else(|| {
        SynthError::new(format!(
            "FLAC sample {path} does not declare its total sample count."
        ))
    })?;
    Ok(SampleMetadata {
        duration: frames as f64 / info.sample_rate as f64,
    })
}

pub(crate) struct DecodedWav {
    pub(crate) left: Vec<f64>,
    pub(crate) right: Vec<f64>,
    pub(crate) sample_rate: u32,
    pub(crate) stereo: bool,
}

pub(crate) fn decode_wav_stereo(bytes: &[u8]) -> SynthResult<DecodedWav> {
    let wav = crate::codec::parse_riff_wav(bytes).map_err(|error| match error {
        crate::codec::RiffWavError::InvalidHeader => {
            SynthError::new("Rust synth sample rendering currently supports PCM WAV bytes.")
        }
        crate::codec::RiffWavError::MalformedChunkLength => {
            SynthError::new("Malformed WAV chunk length.")
        }
        crate::codec::RiffWavError::MalformedFmtChunk => {
            SynthError::new("Malformed WAV fmt chunk.")
        }
    })?;
    let channels = wav
        .channels
        .ok_or_else(|| SynthError::new("WAV missing fmt chunk."))?;
    let sample_rate = wav
        .sample_rate
        .ok_or_else(|| SynthError::new("WAV missing sample rate."))?;
    let bits_per_sample = wav
        .bits_per_sample
        .ok_or_else(|| SynthError::new("WAV missing depth."))?;
    let data = wav
        .data
        .ok_or_else(|| SynthError::new("WAV missing data chunk."))?;
    let width = usize::from(bits_per_sample.div_ceil(8));
    if !matches!(width, 1 | 2 | 4) || !matches!(channels, 1 | 2) {
        return Err(SynthError::new(
            "Unsupported PCM WAV format; expected mono or stereo 8/16/32-bit PCM.",
        ));
    }
    let step = width * usize::from(channels);
    let mut left = Vec::with_capacity(data.len() / step);
    let mut right = Vec::with_capacity(data.len() / step);
    for frame in data.chunks_exact(step) {
        let left_sample = decode_pcm_sample(&frame[0..width]);
        left.push(left_sample);
        if channels == 1 {
            right.push(left_sample);
        } else {
            right.push(decode_pcm_sample(&frame[width..width * 2]));
        }
    }
    Ok(DecodedWav {
        left,
        right,
        sample_rate,
        stereo: channels == 2,
    })
}

pub(crate) fn decode_pcm_sample(raw: &[u8]) -> f64 {
    match raw.len() {
        1 => (f64::from(raw[0]) - 128.0) / 128.0,
        2 => f64::from(i16::from_le_bytes([raw[0], raw[1]])) / 32768.0,
        4 => f64::from(i32::from_le_bytes([raw[0], raw[1], raw[2], raw[3]])) / 2147483648.0,
        _ => 0.0,
    }
}

fn resample_source(source: &SampleSource, target_rate: u32) -> SynthResult<SampleSource> {
    if target_rate == 0 {
        return Err(SynthError::new(
            "sample target rate must be greater than zero.",
        ));
    }
    let left = resample(&source.left, source.sample_rate, target_rate);
    let right = resample(&source.right, source.sample_rate, target_rate);
    let duration = left.len().min(right.len()) as f64 / target_rate as f64;
    Ok(SampleSource {
        left: Arc::new(left),
        right: Arc::new(right),
        duration,
        stereo: source.stereo,
        sample_rate: target_rate,
    })
}

/// Sample one fractional source position with the canonical band-limited kernel.
///
/// `source_step` is the number of source frames advanced per output frame. It
/// may change between calls for playback-rate automation. The cutoff follows
/// the narrower Nyquist band, so dynamic downsampling does not select a linear
/// or otherwise reduced-quality route.
pub fn band_limited_sample(samples: &[f64], source_position: f64, source_step: f64) -> f64 {
    band_limited_sample_strided(samples, source_position, source_step, 1, 0)
}

/// Sample one channel from interleaved source frames with the canonical kernel.
pub fn band_limited_sample_strided(
    samples: &[f64],
    source_position: f64,
    source_step: f64,
    stride: usize,
    channel: usize,
) -> f64 {
    if samples.is_empty()
        || stride == 0
        || channel >= stride
        || !source_position.is_finite()
        || !source_step.is_finite()
        || source_step <= 0.0
    {
        return 0.0;
    }
    let frame_count = samples.len() / stride;
    let cutoff = source_step.recip().min(1.0) * RESAMPLER_CUTOFF_MARGIN;
    let center = source_position.floor() as isize;
    let mut value = 0.0;
    let mut weight_sum = 0.0;
    for tap in -RESAMPLER_RADIUS + 1..=RESAMPLER_RADIUS {
        let source_index = center + tap;
        if source_index < 0 || source_index >= frame_count as isize {
            continue;
        }
        let distance = source_position - source_index as f64;
        let normalized = distance / RESAMPLER_RADIUS as f64;
        if normalized.abs() >= 1.0 {
            continue;
        }
        let window = 0.42 + 0.5 * (PI * normalized).cos() + 0.08 * (2.0 * PI * normalized).cos();
        let argument = PI * distance * cutoff;
        let sinc = if argument.abs() < 1e-12 {
            1.0
        } else {
            argument.sin() / argument
        };
        let weight = cutoff * sinc * window;
        value += samples[source_index as usize * stride + channel] * weight;
        weight_sum += weight;
    }
    if weight_sum.abs() > 1e-12 {
        value / weight_sum
    } else {
        0.0
    }
}

/// Deterministic Blackman-windowed sinc conversion used for every asset-rate change.
///
/// The fixed 32-tap support gives one cross-platform quality policy rather than
/// selecting a reduced linear path.
pub(crate) fn resample(samples: &[f64], source_rate: u32, target_rate: u32) -> Vec<f64> {
    if samples.is_empty() || source_rate == 0 || target_rate == 0 {
        return Vec::new();
    }
    if source_rate == target_rate {
        return samples.to_vec();
    }
    let target_count = ((samples.len() as u128 * target_rate as u128 + source_rate as u128 / 2)
        / source_rate as u128) as usize;
    let ratio = target_rate as f64 / source_rate as f64;
    let source_step = ratio.recip();
    let mut output = Vec::with_capacity(target_count);
    for index in 0..target_count {
        output.push(band_limited_sample(
            samples,
            index as f64 * source_step,
            source_step,
        ));
    }
    output
}
