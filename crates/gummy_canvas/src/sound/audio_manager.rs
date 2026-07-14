use std::collections::BTreeMap;
use std::sync::mpsc::{self, Receiver, Sender};
use std::sync::{Arc, Mutex, OnceLock};
use std::thread;
use std::time::{Duration, Instant};

use gummy_synth::{
    band_limited_sample, band_limited_sample_strided, BlockRenderConfig, BlockRenderStep,
    CompiledSynthProgram, PcmSink, SinkWrite, StatefulBlockRenderer, SynthError, SynthResult,
    DEFAULT_RENDER_BLOCK_FRAMES,
};
use sdl3::audio::{AudioFormat, AudioSpec, AudioStreamOwner};

pub(super) const DEVICE_SAMPLE_RATE: u32 = 48_000;
const DEVICE_CHANNELS: u16 = 2;
const LOW_WATER_FRAMES: u64 = (DEFAULT_RENDER_BLOCK_FRAMES / 2) as u64;
const HIGH_WATER_FRAMES: u64 = DEFAULT_RENDER_BLOCK_FRAMES as u64;
const MAX_VOICES: usize = 128;

#[derive(Debug)]
pub(super) struct AudioAsset {
    pub(super) left: Arc<Vec<f64>>,
    pub(super) right: Arc<Vec<f64>>,
    pub(super) sample_rate: u32,
    pub(super) duration: f64,
}

impl AudioAsset {
    pub(super) fn frame_count(&self) -> usize {
        self.left.len().min(self.right.len())
    }

    pub(super) fn decoded_bytes(&self) -> usize {
        self.left
            .capacity()
            .saturating_add(self.right.capacity())
            .saturating_mul(std::mem::size_of::<f64>())
    }
}

#[derive(Clone, Copy, Debug, Default)]
pub(crate) struct AudioManagerDiagnostics {
    pub manager_initializations: u64,
    pub device_open_count: u64,
    pub device_error_count: u64,
    pub active_voices: usize,
    pub peak_active_voices: usize,
    pub active_synth_sessions: usize,
    pub peak_active_synth_sessions: usize,
    pub mixed_blocks: u64,
    pub mixed_frames: u64,
    pub command_count: u64,
    pub queue_frames: u64,
    pub queue_min_frames: u64,
    pub queue_peak_frames: u64,
    pub queue_low_water_frames: u64,
    pub queue_high_water_frames: u64,
    pub queue_underruns: u64,
    pub asset_bytes: usize,
    pub asset_voice_starts: u64,
    pub synth_session_starts: u64,
}

fn diagnostics_state() -> &'static Mutex<AudioManagerDiagnostics> {
    static DIAGNOSTICS: OnceLock<Mutex<AudioManagerDiagnostics>> = OnceLock::new();
    DIAGNOSTICS.get_or_init(|| {
        Mutex::new(AudioManagerDiagnostics {
            queue_min_frames: u64::MAX,
            queue_low_water_frames: LOW_WATER_FRAMES,
            queue_high_water_frames: HIGH_WATER_FRAMES,
            ..AudioManagerDiagnostics::default()
        })
    })
}

pub(super) fn diagnostics() -> AudioManagerDiagnostics {
    diagnostics_state()
        .lock()
        .map(|diagnostics| {
            let mut snapshot = *diagnostics;
            if snapshot.queue_min_frames == u64::MAX {
                snapshot.queue_min_frames = 0;
            }
            snapshot
        })
        .unwrap_or_default()
}

pub(super) fn reset_diagnostics() {
    if let Ok(mut diagnostics) = diagnostics_state().lock() {
        let active_voices = diagnostics.active_voices;
        let active_synth_sessions = diagnostics.active_synth_sessions;
        let asset_bytes = diagnostics.asset_bytes;
        *diagnostics = AudioManagerDiagnostics {
            active_voices,
            active_synth_sessions,
            asset_bytes,
            queue_min_frames: u64::MAX,
            queue_low_water_frames: LOW_WATER_FRAMES,
            queue_high_water_frames: HIGH_WATER_FRAMES,
            ..AudioManagerDiagnostics::default()
        };
    }
}

#[derive(Debug)]
pub(super) struct PlaybackSnapshot {
    pub duration: f64,
    pub position: f64,
    pub playing: bool,
    pub paused: bool,
    pub looping: bool,
    pub ended_generation: u64,
    pub error: Option<String>,
    pub blocks: u64,
    pub rendered_frames: u64,
}

impl PlaybackSnapshot {
    fn new(duration: f64, looping: bool) -> Self {
        Self {
            duration,
            position: 0.0,
            playing: true,
            paused: false,
            looping,
            ended_generation: 0,
            error: None,
            blocks: 0,
            rendered_frames: 0,
        }
    }
}

pub(super) struct PlaybackHandle {
    id: u64,
    sender: Sender<ManagerCommand>,
    pub(super) state: Arc<Mutex<PlaybackSnapshot>>,
}

impl PlaybackHandle {
    pub(super) fn command(&self, update: VoiceUpdate) -> Result<(), String> {
        let (response, result) = mpsc::channel();
        self.sender
            .send(ManagerCommand::Update {
                id: self.id,
                update,
                response,
            })
            .map_err(|_| "The Gummy Snake SDL audio manager is not running.".to_owned())?;
        result.recv().map_err(|_| {
            "The Gummy Snake SDL audio manager stopped before applying a playback command."
                .to_owned()
        })?
    }
}

impl Drop for PlaybackHandle {
    fn drop(&mut self) {
        let (response, _result) = mpsc::channel();
        let _ = self.sender.send(ManagerCommand::Update {
            id: self.id,
            update: VoiceUpdate::Close,
            response,
        });
    }
}

pub(super) enum PlaybackSource {
    Asset {
        asset: Arc<AudioAsset>,
        volume: f64,
        rate: f64,
        pan: f64,
        looping: bool,
        position_seconds: f64,
    },
    Synth {
        program: CompiledSynthProgram,
        looping: bool,
    },
}

pub(super) enum VoiceUpdate {
    Pause,
    Resume,
    Stop,
    Close,
    SetLooping(bool),
    SetVolume(f64),
    SetRate(f64),
    SetPan(f64),
    Seek(f64),
}

enum ManagerCommand {
    Add {
        source: PlaybackSource,
        response: Sender<Result<PlaybackHandle, String>>,
    },
    Update {
        id: u64,
        update: VoiceUpdate,
        response: Sender<Result<(), String>>,
    },
}

struct AudioManager {
    sender: Sender<ManagerCommand>,
}

impl AudioManager {
    fn start() -> Result<Self, String> {
        let (sender, receiver) = mpsc::channel();
        let (startup_sender, startup_receiver) = mpsc::channel();
        thread::Builder::new()
            .name("gummysnake-sdl-audio".to_owned())
            .spawn(move || run_manager(receiver, startup_sender))
            .map_err(|error| {
                format!("Could not start the Gummy Snake SDL audio manager: {error}")
            })?;
        startup_receiver.recv().map_err(|_| {
            "The Gummy Snake SDL audio manager stopped during startup.".to_owned()
        })??;
        Ok(Self { sender })
    }
}

fn manager() -> Result<&'static AudioManager, String> {
    static MANAGER: OnceLock<Result<AudioManager, String>> = OnceLock::new();
    MANAGER
        .get_or_init(AudioManager::start)
        .as_ref()
        .map_err(Clone::clone)
}

pub(super) fn start_playback(source: PlaybackSource) -> Result<PlaybackHandle, String> {
    let manager = manager()?;
    let (response, result) = mpsc::channel();
    manager
        .sender
        .send(ManagerCommand::Add { source, response })
        .map_err(|_| "The Gummy Snake SDL audio manager is not running.".to_owned())?;
    result.recv().map_err(|_| {
        "The Gummy Snake SDL audio manager stopped before starting playback.".to_owned()
    })?
}

fn run_manager(receiver: Receiver<ManagerCommand>, startup: Sender<Result<(), String>>) {
    let result = open_audio_stream();
    let (sdl, stream) = match result {
        Ok(value) => value,
        Err(error) => {
            if let Ok(mut diagnostics) = diagnostics_state().lock() {
                diagnostics.device_error_count += 1;
            }
            let _ = startup.send(Err(error));
            return;
        }
    };
    if let Ok(mut diagnostics) = diagnostics_state().lock() {
        diagnostics.manager_initializations += 1;
        diagnostics.device_open_count += 1;
    }
    let _sdl = sdl;
    if let Err(error) = stream.resume() {
        let message = format!("Failed to start the Gummy Snake SDL audio stream: {error}");
        if let Ok(mut diagnostics) = diagnostics_state().lock() {
            diagnostics.device_error_count += 1;
        }
        let _ = startup.send(Err(message));
        return;
    }
    let _ = startup.send(Ok(()));

    let mut voices = BTreeMap::<u64, Voice>::new();
    let mut next_id = 1_u64;
    loop {
        while let Ok(command) = receiver.try_recv() {
            apply_command(command, &mut voices, &mut next_id);
        }

        if voices.is_empty() {
            match receiver.recv_timeout(Duration::from_millis(10)) {
                Ok(command) => apply_command(command, &mut voices, &mut next_id),
                Err(mpsc::RecvTimeoutError::Timeout) => {}
                Err(mpsc::RecvTimeoutError::Disconnected) => break,
            }
            continue;
        }

        let queued_frames = match queued_stereo_frames(&stream) {
            Ok(value) => value,
            Err(error) => {
                fail_all_voices(&mut voices, error);
                if let Ok(mut diagnostics) = diagnostics_state().lock() {
                    diagnostics.device_error_count += 1;
                }
                break;
            }
        };
        observe_queue(queued_frames, !voices.is_empty());
        if queued_frames <= LOW_WATER_FRAMES {
            while queued_stereo_frames(&stream).unwrap_or(HIGH_WATER_FRAMES) < HIGH_WATER_FRAMES
                && !voices.is_empty()
            {
                let block = mix_block(&mut voices, DEFAULT_RENDER_BLOCK_FRAMES);
                if block.is_empty() {
                    break;
                }
                if let Err(error) = stream.put_data_i16(&block) {
                    fail_all_voices(
                        &mut voices,
                        format!("Failed to queue mixed SDL3 audio: {error}"),
                    );
                    if let Ok(mut diagnostics) = diagnostics_state().lock() {
                        diagnostics.device_error_count += 1;
                    }
                    break;
                }
            }
        } else {
            thread::sleep(Duration::from_millis(2));
        }
    }
    let _ = stream.pause();
    let _ = stream.clear();
}

fn open_audio_stream() -> Result<(sdl3::Sdl, AudioStreamOwner), String> {
    let sdl = sdl3::init().map_err(|error| {
        format!(
            "Native audio is unavailable because SDL3 could not initialize: {error}. Rebuild the Gummy Snake canvas runtime with SDL3 audio support."
        )
    })?;
    let audio = sdl.audio().map_err(|error| {
        format!("Native audio is unavailable because the SDL3 audio subsystem could not initialize: {error}.")
    })?;
    let spec = AudioSpec {
        freq: Some(DEVICE_SAMPLE_RATE as i32),
        channels: Some(i32::from(DEVICE_CHANNELS)),
        format: Some(AudioFormat::s16_sys()),
    };
    let device = audio.open_playback_device(&spec).map_err(|error| {
        format!(
            "Native audio is unavailable because SDL3 could not open a playback device at {DEVICE_SAMPLE_RATE} Hz stereo 16-bit PCM: {error}."
        )
    })?;
    let stream = device.open_device_stream(Some(&spec)).map_err(|error| {
        format!("Native audio is unavailable because SDL3 could not open the shared playback stream: {error}.")
    })?;
    Ok((sdl, stream))
}

fn apply_command(command: ManagerCommand, voices: &mut BTreeMap<u64, Voice>, next_id: &mut u64) {
    if let Ok(mut diagnostics) = diagnostics_state().lock() {
        diagnostics.command_count += 1;
    }
    match command {
        ManagerCommand::Add { source, response } => {
            if voices.len() >= MAX_VOICES {
                let _ = response.send(Err(format!(
                    "Native audio voice limit {MAX_VOICES} was reached; stop or close an existing Sound before starting another."
                )));
                return;
            }
            let id = *next_id;
            *next_id = next_id.wrapping_add(1).max(1);
            match Voice::new(source) {
                Ok((voice, handle_state)) => {
                    let sender = manager()
                        .map(|manager| manager.sender.clone())
                        .expect("audio manager exists while its worker applies commands");
                    let handle = PlaybackHandle {
                        id,
                        sender,
                        state: handle_state,
                    };
                    observe_voice_added(&voice);
                    voices.insert(id, voice);
                    let _ = response.send(Ok(handle));
                }
                Err(error) => {
                    let _ = response.send(Err(error));
                }
            }
        }
        ManagerCommand::Update {
            id,
            update,
            response,
        } => {
            let result = if matches!(update, VoiceUpdate::Stop | VoiceUpdate::Close) {
                if let Some(mut voice) = voices.remove(&id) {
                    voice.stop(false);
                    observe_voice_removed(&voice);
                }
                Ok(())
            } else if let Some(voice) = voices.get_mut(&id) {
                voice.update(update)
            } else {
                Err("This native audio playback handle is closed.".to_owned())
            };
            let _ = response.send(result);
        }
    }
}

fn observe_voice_added(voice: &Voice) {
    if let Ok(mut diagnostics) = diagnostics_state().lock() {
        diagnostics.active_voices += 1;
        diagnostics.peak_active_voices = diagnostics
            .peak_active_voices
            .max(diagnostics.active_voices);
        match &voice.source {
            VoiceSource::Asset(asset) => {
                diagnostics.asset_voice_starts += 1;
                diagnostics.asset_bytes = diagnostics
                    .asset_bytes
                    .saturating_add(asset.asset.decoded_bytes());
            }
            VoiceSource::Synth(_) => {
                diagnostics.synth_session_starts += 1;
                diagnostics.active_synth_sessions += 1;
                diagnostics.peak_active_synth_sessions = diagnostics
                    .peak_active_synth_sessions
                    .max(diagnostics.active_synth_sessions);
            }
        }
    }
}

fn observe_voice_removed(voice: &Voice) {
    if let Ok(mut diagnostics) = diagnostics_state().lock() {
        diagnostics.active_voices = diagnostics.active_voices.saturating_sub(1);
        match &voice.source {
            VoiceSource::Asset(asset) => {
                diagnostics.asset_bytes = diagnostics
                    .asset_bytes
                    .saturating_sub(asset.asset.decoded_bytes());
            }
            VoiceSource::Synth(_) => {
                diagnostics.active_synth_sessions =
                    diagnostics.active_synth_sessions.saturating_sub(1);
            }
        }
    }
}

fn observe_queue(frames: u64, active: bool) {
    if let Ok(mut diagnostics) = diagnostics_state().lock() {
        diagnostics.queue_frames = frames;
        diagnostics.queue_min_frames = diagnostics.queue_min_frames.min(frames);
        diagnostics.queue_peak_frames = diagnostics.queue_peak_frames.max(frames);
        if active && frames == 0 && diagnostics.mixed_blocks > 0 {
            diagnostics.queue_underruns += 1;
        }
    }
}

fn mix_block(voices: &mut BTreeMap<u64, Voice>, frames: usize) -> Vec<i16> {
    let started = Instant::now();
    let mut left = vec![0.0; frames];
    let mut right = vec![0.0; frames];
    let mut ended = Vec::new();
    for (&id, voice) in voices.iter_mut() {
        if voice.mix_into(&mut left, &mut right).is_err() || voice.is_terminal() {
            ended.push(id);
        }
    }
    for id in ended {
        if let Some(voice) = voices.remove(&id) {
            observe_voice_removed(&voice);
        }
    }
    if voices.is_empty() && left.iter().all(|sample| sample.abs() <= f64::EPSILON) {
        return Vec::new();
    }
    let mut output = Vec::with_capacity(frames * 2);
    for (left, right) in left.into_iter().zip(right) {
        output.push(float_to_i16(left));
        output.push(float_to_i16(right));
    }
    if let Ok(mut diagnostics) = diagnostics_state().lock() {
        diagnostics.mixed_blocks += 1;
        diagnostics.mixed_frames += frames as u64;
        let _ = started;
    }
    output
}

fn float_to_i16(value: f64) -> i16 {
    (value.clamp(-1.0, 1.0) * i16::MAX as f64).round() as i16
}

fn queued_stereo_frames(stream: &AudioStreamOwner) -> Result<u64, String> {
    let queued_bytes = stream
        .queued_bytes()
        .map_err(|error| format!("Failed to query the shared SDL3 audio queue: {error}"))?;
    let queued_bytes = u64::try_from(queued_bytes.max(0))
        .map_err(|_| "SDL3 returned an invalid shared audio queue size.".to_owned())?;
    Ok(queued_bytes / (std::mem::size_of::<i16>() as u64 * u64::from(DEVICE_CHANNELS)))
}

fn fail_all_voices(voices: &mut BTreeMap<u64, Voice>, error: String) {
    for voice in voices.values_mut() {
        voice.fail(error.clone());
    }
    let failed = std::mem::take(voices);
    for voice in failed.values() {
        observe_voice_removed(voice);
    }
}

struct Voice {
    source: VoiceSource,
    state: Arc<Mutex<PlaybackSnapshot>>,
    volume: f64,
    rate: f64,
    pan: f64,
    paused: bool,
    terminal: bool,
}

impl Voice {
    fn new(source: PlaybackSource) -> Result<(Self, Arc<Mutex<PlaybackSnapshot>>), String> {
        let (source, duration, volume, rate, pan, looping, position) = match source {
            PlaybackSource::Asset {
                asset,
                volume,
                rate,
                pan,
                looping,
                position_seconds,
            } => {
                let duration = asset.duration;
                let mut voice = AssetVoice::new(asset);
                voice.looping = looping;
                voice.position = position_seconds * voice.asset.sample_rate as f64;
                (
                    VoiceSource::Asset(voice),
                    duration,
                    volume,
                    rate,
                    pan,
                    looping,
                    position_seconds,
                )
            }
            PlaybackSource::Synth { program, looping } => {
                let duration = program.duration_seconds();
                let voice = SynthVoice::new(program, looping)?;
                (
                    VoiceSource::Synth(voice),
                    duration,
                    1.0,
                    1.0,
                    0.0,
                    looping,
                    0.0,
                )
            }
        };
        validate_volume(volume)?;
        validate_rate(rate)?;
        validate_pan(pan)?;
        validate_seek(position, duration)?;
        let mut snapshot = PlaybackSnapshot::new(duration, looping);
        snapshot.position = position;
        let state = Arc::new(Mutex::new(snapshot));
        Ok((
            Self {
                source,
                state: Arc::clone(&state),
                volume,
                rate,
                pan,
                paused: false,
                terminal: false,
            },
            state,
        ))
    }

    fn update(&mut self, update: VoiceUpdate) -> Result<(), String> {
        match update {
            VoiceUpdate::Pause => {
                self.paused = true;
                self.with_state(|state| {
                    state.playing = false;
                    state.paused = true;
                });
            }
            VoiceUpdate::Resume => {
                self.paused = false;
                self.with_state(|state| {
                    state.playing = true;
                    state.paused = false;
                });
            }
            VoiceUpdate::Stop => self.stop(false),
            VoiceUpdate::Close => unreachable!("close is handled before voice lookup"),
            VoiceUpdate::SetLooping(value) => {
                self.source.set_looping(value)?;
                self.with_state(|state| state.looping = value);
            }
            VoiceUpdate::SetVolume(value) => {
                validate_volume(value)?;
                self.volume = value;
            }
            VoiceUpdate::SetRate(value) => {
                validate_rate(value)?;
                self.rate = value;
            }
            VoiceUpdate::SetPan(value) => {
                validate_pan(value)?;
                self.pan = value;
            }
            VoiceUpdate::Seek(seconds) => {
                let duration = self
                    .state
                    .lock()
                    .map_err(|_| "Native audio playback state lock was poisoned.".to_owned())?
                    .duration;
                validate_seek(seconds, duration)?;
                self.source.seek(seconds)?;
                self.terminal = false;
                self.with_state(|state| {
                    state.position = seconds;
                    state.playing = !self.paused;
                    state.paused = self.paused;
                });
            }
        }
        Ok(())
    }

    fn mix_into(&mut self, left: &mut [f64], right: &mut [f64]) -> Result<(), String> {
        if self.paused || self.terminal {
            return Ok(());
        }
        let left_gain = self.volume * (1.0 - self.pan.max(0.0));
        let right_gain = self.volume * (1.0 + self.pan.min(0.0));
        let mut rendered = 0_u64;
        for (left_out, right_out) in left.iter_mut().zip(right) {
            match self.source.next_frame(self.rate)? {
                Some((source_left, source_right, position)) => {
                    *left_out += source_left * left_gain;
                    *right_out += source_right * right_gain;
                    rendered += 1;
                    self.with_state(|state| state.position = position);
                }
                None => {
                    self.stop(true);
                    break;
                }
            }
        }
        self.with_state(|state| {
            if rendered > 0 {
                state.blocks += 1;
                state.rendered_frames += rendered;
            }
        });
        Ok(())
    }

    fn stop(&mut self, natural: bool) {
        if self.terminal {
            return;
        }
        self.terminal = true;
        self.with_state(|state| {
            state.playing = false;
            state.paused = false;
            if natural {
                state.ended_generation = state.ended_generation.wrapping_add(1).max(1);
            } else {
                state.position = 0.0;
            }
        });
    }

    fn fail(&mut self, error: String) {
        self.terminal = true;
        self.with_state(|state| {
            state.playing = false;
            state.paused = false;
            state.error = Some(error);
        });
    }

    fn is_terminal(&self) -> bool {
        self.terminal
    }

    fn with_state(&self, update: impl FnOnce(&mut PlaybackSnapshot)) {
        if let Ok(mut state) = self.state.lock() {
            update(&mut state);
        }
    }
}

fn validate_volume(value: f64) -> Result<(), String> {
    if value.is_finite() && value >= 0.0 {
        Ok(())
    } else {
        Err("Native audio volume must be finite and non-negative.".to_owned())
    }
}

fn validate_rate(value: f64) -> Result<(), String> {
    if value.is_finite() && value > 0.0 {
        Ok(())
    } else {
        Err("Native audio playback rate must be finite and greater than zero.".to_owned())
    }
}

fn validate_pan(value: f64) -> Result<(), String> {
    if value.is_finite() && (-1.0..=1.0).contains(&value) {
        Ok(())
    } else {
        Err("Native audio pan must be finite and between -1 and 1.".to_owned())
    }
}

fn validate_seek(seconds: f64, duration: f64) -> Result<(), String> {
    if seconds.is_finite() && (0.0..=duration).contains(&seconds) {
        Ok(())
    } else {
        Err(format!(
            "Native audio seek time must be finite and between 0 and {duration} seconds."
        ))
    }
}

enum VoiceSource {
    Asset(AssetVoice),
    Synth(SynthVoice),
}

impl VoiceSource {
    fn next_frame(&mut self, rate: f64) -> Result<Option<(f64, f64, f64)>, String> {
        match self {
            Self::Asset(voice) => Ok(voice.next_frame(rate)),
            Self::Synth(voice) => voice.next_frame(rate),
        }
    }

    fn set_looping(&mut self, looping: bool) -> Result<(), String> {
        match self {
            Self::Asset(voice) => {
                voice.looping = looping;
                Ok(())
            }
            Self::Synth(voice) => {
                voice.looping = looping;
                Ok(())
            }
        }
    }

    fn seek(&mut self, seconds: f64) -> Result<(), String> {
        match self {
            Self::Asset(voice) => {
                voice.position = seconds * voice.asset.sample_rate as f64;
                Ok(())
            }
            Self::Synth(voice) => voice.seek(seconds),
        }
    }
}

struct AssetVoice {
    asset: Arc<AudioAsset>,
    position: f64,
    looping: bool,
}

impl AssetVoice {
    fn new(asset: Arc<AudioAsset>) -> Self {
        Self {
            asset,
            position: 0.0,
            looping: false,
        }
    }

    fn next_frame(&mut self, rate: f64) -> Option<(f64, f64, f64)> {
        let frame_count = self.asset.frame_count();
        if frame_count == 0 {
            return None;
        }
        if self.position >= frame_count as f64 {
            if self.looping {
                self.position %= frame_count as f64;
            } else {
                return None;
            }
        }
        let source_step = self.asset.sample_rate as f64 * rate / DEVICE_SAMPLE_RATE as f64;
        let left = band_limited_sample(&self.asset.left, self.position, source_step);
        let right = band_limited_sample(&self.asset.right, self.position, source_step);
        self.position += source_step;
        let position_seconds = self.position / self.asset.sample_rate as f64;
        Some((left, right, position_seconds))
    }
}

struct SynthVoice {
    program: CompiledSynthProgram,
    renderer: StatefulBlockRenderer,
    pcm: Vec<f64>,
    position: f64,
    consumed_frames: usize,
    finished: bool,
    looping: bool,
    played_seconds: f64,
}

impl SynthVoice {
    fn new(program: CompiledSynthProgram, looping: bool) -> Result<Self, String> {
        let renderer = StatefulBlockRenderer::new(program.clone(), BlockRenderConfig::default())
            .map_err(|error| {
                format!("Could not create the native synth playback session: {error}")
            })?;
        Ok(Self {
            program,
            renderer,
            pcm: Vec::new(),
            position: 0.0,
            consumed_frames: 0,
            finished: false,
            looping,
            played_seconds: 0.0,
        })
    }

    fn next_frame(&mut self, rate: f64) -> Result<Option<(f64, f64, f64)>, String> {
        self.ensure_source_frames()?;
        let available_frames = self.pcm.len() / 2;
        if self.position >= available_frames as f64 {
            if self.finished && self.looping {
                self.restart()?;
                self.ensure_source_frames()?;
            }
            if self.position >= self.pcm.len() as f64 / 2.0 {
                return Ok(None);
            }
        }
        let source_step = self.program.sample_rate() as f64 * rate / DEVICE_SAMPLE_RATE as f64;
        let left = band_limited_interleaved(&self.pcm, self.position, source_step, 0);
        let right = band_limited_interleaved(&self.pcm, self.position, source_step, 1);
        self.position += source_step;
        self.played_seconds += 1.0 / DEVICE_SAMPLE_RATE as f64;
        self.compact();
        Ok(Some((left, right, self.played_seconds)))
    }

    fn ensure_source_frames(&mut self) -> Result<(), String> {
        while !self.finished && self.position + 32.0 >= self.pcm.len() as f64 / 2.0 {
            let mut sink = AppendPcmSink {
                samples: &mut self.pcm,
            };
            match self
                .renderer
                .step(&mut sink)
                .map_err(|error| format!("Native synth playback block render failed: {error}"))?
            {
                BlockRenderStep::Produced { .. } => {}
                BlockRenderStep::Finished => self.finished = true,
            }
        }
        Ok(())
    }

    fn compact(&mut self) {
        let whole_frames = self.position.floor() as usize;
        if whole_frames < DEFAULT_RENDER_BLOCK_FRAMES * 4 {
            return;
        }
        let remove_frames = whole_frames.saturating_sub(32);
        self.pcm.drain(..remove_frames * 2);
        self.position -= remove_frames as f64;
        self.consumed_frames = self.consumed_frames.saturating_add(remove_frames);
    }

    fn restart(&mut self) -> Result<(), String> {
        self.renderer =
            StatefulBlockRenderer::new(self.program.clone(), BlockRenderConfig::default())
                .map_err(|error| {
                    format!("Could not restart the native rolling synth session: {error}")
                })?;
        self.pcm.clear();
        self.position = 0.0;
        self.consumed_frames = 0;
        self.finished = false;
        Ok(())
    }

    fn seek(&mut self, seconds: f64) -> Result<(), String> {
        self.restart()?;
        let target = seconds * self.program.sample_rate() as f64;
        while self.consumed_frames as f64 + self.pcm.len() as f64 / 2.0 <= target && !self.finished
        {
            let before = self.pcm.len();
            let mut sink = AppendPcmSink {
                samples: &mut self.pcm,
            };
            match self
                .renderer
                .step(&mut sink)
                .map_err(|error| format!("Native synth seek render failed: {error}"))?
            {
                BlockRenderStep::Produced { .. } => {}
                BlockRenderStep::Finished => self.finished = true,
            }
            if self.pcm.len() == before && !self.finished {
                return Err("Native synth seek made no render progress.".to_owned());
            }
            if self.pcm.len() / 2 > DEFAULT_RENDER_BLOCK_FRAMES * 8 {
                let remove_frames = self.pcm.len() / 2 - 32;
                self.pcm.drain(..remove_frames * 2);
                self.consumed_frames += remove_frames;
            }
        }
        self.position = (target - self.consumed_frames as f64).max(0.0);
        self.played_seconds = seconds;
        Ok(())
    }
}

struct AppendPcmSink<'a> {
    samples: &'a mut Vec<f64>,
}

impl PcmSink for AppendPcmSink<'_> {
    fn write_interleaved_i16(&mut self, samples: &[i16]) -> SynthResult<SinkWrite> {
        if !samples.len().is_multiple_of(2) {
            return Err(SynthError::new(
                "native synth mixer received an incomplete stereo PCM frame.",
            ));
        }
        self.samples
            .extend(samples.iter().map(|sample| f64::from(*sample) / 32768.0));
        Ok(SinkWrite::Accepted)
    }
}

fn band_limited_interleaved(
    samples: &[f64],
    source_position: f64,
    source_step: f64,
    channel: usize,
) -> f64 {
    band_limited_sample_strided(samples, source_position, source_step, 2, channel)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn asset(samples: &[f64], sample_rate: u32) -> Arc<AudioAsset> {
        Arc::new(AudioAsset {
            left: Arc::new(samples.to_vec()),
            right: Arc::new(samples.to_vec()),
            sample_rate,
            duration: samples.len() as f64 / sample_rate as f64,
        })
    }

    #[test]
    fn asset_voice_controls_advance_at_exact_mixer_frames() {
        let source = asset(&[0.0, 0.5, 1.0, 0.5, 0.0], DEVICE_SAMPLE_RATE);
        let (mut voice, state) = Voice::new(PlaybackSource::Asset {
            asset: source,
            volume: 1.0,
            rate: 1.0,
            pan: 0.0,
            looping: false,
            position_seconds: 0.0,
        })
        .unwrap();
        voice.volume = 0.5;
        voice.pan = -1.0;
        let mut left = [0.0; 3];
        let mut right = [0.0; 3];

        voice.mix_into(&mut left, &mut right).unwrap();

        assert!(left.iter().any(|sample| *sample != 0.0));
        assert!(right.iter().all(|sample| sample.abs() <= f64::EPSILON));
        assert_eq!(state.lock().unwrap().rendered_frames, 3);
    }

    #[test]
    fn asset_voice_looping_and_seek_keep_independent_state() {
        let source = asset(&[0.25, -0.25], DEVICE_SAMPLE_RATE);
        let source_config = |asset| PlaybackSource::Asset {
            asset,
            volume: 1.0,
            rate: 1.0,
            pan: 0.0,
            looping: false,
            position_seconds: 0.0,
        };
        let (mut first, _) = Voice::new(source_config(Arc::clone(&source))).unwrap();
        let (mut second, _) = Voice::new(source_config(source)).unwrap();
        first.update(VoiceUpdate::SetLooping(true)).unwrap();
        second
            .update(VoiceUpdate::Seek(1.0 / DEVICE_SAMPLE_RATE as f64))
            .unwrap();
        let mut first_left = [0.0; 4];
        let mut first_right = [0.0; 4];
        let mut second_left = [0.0; 1];
        let mut second_right = [0.0; 1];

        first.mix_into(&mut first_left, &mut first_right).unwrap();
        second
            .mix_into(&mut second_left, &mut second_right)
            .unwrap();

        assert!(!first.is_terminal());
        assert_ne!(first_left[0], second_left[0]);
    }

    #[test]
    fn stop_and_close_are_idempotent_after_voice_removal() {
        let mut voices = BTreeMap::new();
        let mut next_id = 2;
        for update in [VoiceUpdate::Stop, VoiceUpdate::Close] {
            let (response, result) = mpsc::channel();
            apply_command(
                ManagerCommand::Update {
                    id: 1,
                    update,
                    response,
                },
                &mut voices,
                &mut next_id,
            );
            assert_eq!(result.recv().unwrap(), Ok(()));
        }
    }

    #[test]
    fn native_voice_boundary_rejects_invalid_controls() {
        let source = asset(&[0.25, -0.25], DEVICE_SAMPLE_RATE);
        for (volume, rate, pan, position) in [
            (f64::NAN, 1.0, 0.0, 0.0),
            (1.0, 0.0, 0.0, 0.0),
            (1.0, 1.0, 1.1, 0.0),
            (1.0, 1.0, 0.0, 1.0),
        ] {
            let result = Voice::new(PlaybackSource::Asset {
                asset: Arc::clone(&source),
                volume,
                rate,
                pan,
                looping: false,
                position_seconds: position,
            });
            assert!(result.is_err());
        }

        let (mut voice, _) = Voice::new(PlaybackSource::Asset {
            asset: source,
            volume: 1.0,
            rate: 1.0,
            pan: 0.0,
            looping: false,
            position_seconds: 0.0,
        })
        .unwrap();
        assert!(voice.update(VoiceUpdate::SetVolume(f64::INFINITY)).is_err());
        assert!(voice.update(VoiceUpdate::SetRate(-1.0)).is_err());
        assert!(voice.update(VoiceUpdate::SetPan(f64::NAN)).is_err());
        assert!(voice.update(VoiceUpdate::Seek(1.0)).is_err());
    }
}
