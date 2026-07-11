use super::*;

#[derive(Clone, Debug)]
pub(crate) struct SampleSource {
    pub(crate) left: Arc<Vec<f64>>,
    pub(crate) right: Arc<Vec<f64>>,
    pub(crate) duration: f64,
    pub(crate) stereo: bool,
}

impl SampleSource {
    pub(crate) fn len(&self) -> usize {
        self.left.len().min(self.right.len())
    }
}

pub(crate) type SampleCache = HashMap<(String, u32), Arc<SampleSource>>;

pub(crate) fn sample_cache() -> &'static Mutex<SampleCache> {
    static SAMPLE_CACHE: OnceLock<Mutex<SampleCache>> = OnceLock::new();
    SAMPLE_CACHE.get_or_init(|| Mutex::new(HashMap::new()))
}

/// Return a sample duration using the synth renderer's existing sample lookup and decoder.
pub fn sample_duration(value: &SynthValue) -> SynthResult<f64> {
    sample_source(value, 44_100).map(|source| source.duration)
}

pub(crate) fn sample_source(value: &SynthValue, sample_rate: u32) -> SynthResult<SampleSource> {
    let sample_name = match value {
        SynthValue::List(values) => values.first(),
        other => Some(other),
    }
    .ok_or_else(|| SynthError::new("sample event does not specify a sample name."))?;
    if let SynthValue::String(path) = sample_name {
        if fs::metadata(path).is_ok() {
            return cached_sample_file(path, sample_rate);
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
        return cached_sample_file(path.to_string_lossy().as_ref(), sample_rate);
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
    let cache_key = (sample_cache_key(path), sample_rate);
    if let Some(source) = sample_cache()
        .lock()
        .map_err(|_| SynthError::new("synth sample cache lock was poisoned."))?
        .get(&cache_key)
        .cloned()
    {
        return Ok((*source).clone());
    }

    let source = Arc::new(load_sample_file(path, sample_rate)?);
    let mut cache = sample_cache()
        .lock()
        .map_err(|_| SynthError::new("synth sample cache lock was poisoned."))?;
    Ok((**cache
        .entry(cache_key)
        .or_insert_with(|| Arc::clone(&source)))
    .clone())
}

pub(crate) fn sample_cache_key(path: &str) -> String {
    fs::canonicalize(path)
        .unwrap_or_else(|_| PathBuf::from(path))
        .to_string_lossy()
        .into_owned()
}

pub(crate) fn load_sample_file(path: &str, sample_rate: u32) -> SynthResult<SampleSource> {
    let extension = Path::new(path)
        .extension()
        .and_then(|extension| extension.to_str())
        .unwrap_or_default()
        .to_ascii_lowercase();
    if extension == "flac" {
        return load_flac_sample(path, sample_rate);
    }
    load_wav_sample(path, sample_rate)
}

pub(crate) fn load_wav_sample(path: &str, sample_rate: u32) -> SynthResult<SampleSource> {
    let bytes = fs::read(path)
        .map_err(|err| SynthError::new(format!("Could not load WAV sample {path}: {err}")))?;
    let wav = decode_wav_stereo(&bytes)?;
    let left = if wav.sample_rate == sample_rate {
        wav.left
    } else {
        resample(&wav.left, wav.sample_rate, sample_rate)
    };
    let right = if wav.sample_rate == sample_rate {
        wav.right
    } else {
        resample(&wav.right, wav.sample_rate, sample_rate)
    };
    let duration = left.len().min(right.len()) as f64 / sample_rate as f64;
    Ok(SampleSource {
        left: Arc::new(left),
        right: Arc::new(right),
        duration,
        stereo: wav.stereo,
    })
}

pub(crate) fn load_flac_sample(path: &str, sample_rate: u32) -> SynthResult<SampleSource> {
    let mut reader = claxon::FlacReader::open(path)
        .map_err(|err| SynthError::new(format!("Could not load FLAC sample {path}: {err}")))?;
    let streaminfo = reader.streaminfo();
    let source_rate = streaminfo.sample_rate;
    let channels = streaminfo.channels as usize;
    let bits_per_sample = streaminfo.bits_per_sample as i32;
    if !matches!(channels, 1 | 2) || bits_per_sample <= 0 {
        return Err(SynthError::new(format!(
            "Unsupported FLAC sample format for {path}; expected mono or stereo PCM data."
        )));
    }
    let denom = 2_f64.powi(bits_per_sample - 1);
    let mut left = Vec::new();
    let mut right = Vec::new();
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
    let left = if source_rate == sample_rate {
        left
    } else {
        resample(&left, source_rate, sample_rate)
    };
    let right = if source_rate == sample_rate {
        right
    } else {
        resample(&right, source_rate, sample_rate)
    };
    let duration = left.len().min(right.len()) as f64 / sample_rate as f64;
    Ok(SampleSource {
        left: Arc::new(left),
        right: Arc::new(right),
        duration,
        stereo: channels == 2,
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

pub(crate) fn resample(samples: &[f64], source_rate: u32, target_rate: u32) -> Vec<f64> {
    if samples.is_empty() || source_rate == target_rate {
        return samples.to_vec();
    }
    let target_count = samples.len() * target_rate as usize / source_rate as usize;
    let mut output = Vec::with_capacity(target_count);
    for index in 0..target_count {
        let source_pos = index as f64 * source_rate as f64 / target_rate as f64;
        let low = source_pos.floor() as usize;
        let high = (low + 1).min(samples.len() - 1);
        let frac = source_pos - low as f64;
        output.push(samples[low] * (1.0 - frac) + samples[high] * frac);
    }
    output
}
