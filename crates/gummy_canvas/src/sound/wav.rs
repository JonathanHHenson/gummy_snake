use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

pub(super) struct PcmS16Wav {
    pub(super) samples: Vec<i16>,
    pub(super) sample_rate: u32,
    pub(super) channels: u16,
    pub(super) duration: f64,
}

impl PcmS16Wav {
    pub(super) fn into_audio_asset(self) -> super::audio_manager::AudioAsset {
        let frame_count = self.samples.len() / usize::from(self.channels);
        let mut left = Vec::with_capacity(frame_count);
        let mut right = Vec::with_capacity(frame_count);
        for frame in self.samples.chunks_exact(usize::from(self.channels)) {
            let left_sample = f64::from(frame[0]) / 32768.0;
            left.push(left_sample);
            right.push(if self.channels == 1 {
                left_sample
            } else {
                f64::from(frame[1]) / 32768.0
            });
        }
        super::audio_manager::AudioAsset {
            left: std::sync::Arc::new(left),
            right: std::sync::Arc::new(right),
            sample_rate: self.sample_rate,
            duration: self.duration,
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum PlaybackWavError {
    InvalidHeader,
    MalformedChunkLength,
    MalformedFmtChunk,
    MissingFmt,
    UnsupportedAudioFormat,
    MissingChannels,
    ZeroChannels,
    MissingSampleRate,
    ZeroSampleRate,
    MissingBitDepth,
    UnsupportedBitDepth,
    MissingData,
    UnalignedSampleData,
}

impl PlaybackWavError {
    fn message(self) -> &'static str {
        match self {
            Self::InvalidHeader => {
                "SDL3 synth playback requires PCM WAV bytes produced by the Rust synth renderer."
            }
            Self::MalformedChunkLength => "Could not play synth WAV bytes: malformed chunk length.",
            Self::MalformedFmtChunk => "Could not play synth WAV bytes: malformed fmt chunk.",
            Self::MissingFmt => "Could not play synth WAV bytes: missing fmt chunk.",
            Self::UnsupportedAudioFormat => {
                "SDL3 synth playback requires uncompressed PCM WAV bytes."
            }
            Self::MissingChannels => "Could not play synth WAV bytes: missing channel count.",
            Self::ZeroChannels => {
                "Could not play synth WAV bytes: channel count must be greater than zero."
            }
            Self::MissingSampleRate => "Could not play synth WAV bytes: missing sample rate.",
            Self::ZeroSampleRate => {
                "Could not play synth WAV bytes: sample rate must be greater than zero."
            }
            Self::MissingBitDepth => "Could not play synth WAV bytes: missing bit depth.",
            Self::UnsupportedBitDepth => "SDL3 synth playback requires 16-bit PCM WAV bytes.",
            Self::MissingData => "Could not play synth WAV bytes: missing data chunk.",
            Self::UnalignedSampleData => {
                "Could not play synth WAV bytes: sample data length is not aligned to 16-bit samples."
            }
        }
    }
}

impl From<gummy_synth::codec::RiffWavError> for PlaybackWavError {
    fn from(error: gummy_synth::codec::RiffWavError) -> Self {
        match error {
            gummy_synth::codec::RiffWavError::InvalidHeader => Self::InvalidHeader,
            gummy_synth::codec::RiffWavError::MalformedChunkLength => Self::MalformedChunkLength,
            gummy_synth::codec::RiffWavError::MalformedFmtChunk => Self::MalformedFmtChunk,
        }
    }
}

pub(super) fn parse_pcm_s16_wav(bytes: &[u8]) -> PyResult<PcmS16Wav> {
    parse_pcm_s16_wav_core(bytes).map_err(|error| PyValueError::new_err(error.message()))
}

fn parse_pcm_s16_wav_core(bytes: &[u8]) -> Result<PcmS16Wav, PlaybackWavError> {
    let wav = gummy_synth::codec::parse_riff_wav(bytes).map_err(PlaybackWavError::from)?;
    let audio_format = wav.audio_format.ok_or(PlaybackWavError::MissingFmt)?;
    if audio_format != 1 {
        return Err(PlaybackWavError::UnsupportedAudioFormat);
    }
    let channels = wav.channels.ok_or(PlaybackWavError::MissingChannels)?;
    if channels == 0 {
        return Err(PlaybackWavError::ZeroChannels);
    }
    let sample_rate = wav.sample_rate.ok_or(PlaybackWavError::MissingSampleRate)?;
    if sample_rate == 0 {
        return Err(PlaybackWavError::ZeroSampleRate);
    }
    let bits_per_sample = wav
        .bits_per_sample
        .ok_or(PlaybackWavError::MissingBitDepth)?;
    if bits_per_sample != 16 {
        return Err(PlaybackWavError::UnsupportedBitDepth);
    }
    let data = wav.data.ok_or(PlaybackWavError::MissingData)?;
    if data.len() % 2 != 0 {
        return Err(PlaybackWavError::UnalignedSampleData);
    }
    let samples: Vec<i16> = data
        .chunks_exact(2)
        .map(|chunk| i16::from_le_bytes([chunk[0], chunk[1]]))
        .collect();
    let duration = samples.len() as f64 / f64::from(channels) / sample_rate as f64;
    Ok(PcmS16Wav {
        samples,
        sample_rate,
        channels,
        duration,
    })
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum DurationWavError {
    MalformedChunkLength,
    MalformedFmtChunk,
}

impl DurationWavError {
    fn message(self) -> &'static str {
        match self {
            Self::MalformedChunkLength => "Could not load WAV sound: malformed chunk length.",
            Self::MalformedFmtChunk => "Could not load WAV sound: malformed fmt chunk.",
        }
    }
}

pub(super) fn wav_duration_seconds(bytes: &[u8]) -> PyResult<Option<f64>> {
    wav_duration_seconds_core(bytes).map_err(|error| PyValueError::new_err(error.message()))
}

fn wav_duration_seconds_core(bytes: &[u8]) -> Result<Option<f64>, DurationWavError> {
    let wav = match gummy_synth::codec::parse_riff_wav(bytes) {
        Ok(wav) => wav,
        Err(gummy_synth::codec::RiffWavError::InvalidHeader) => return Ok(None),
        Err(gummy_synth::codec::RiffWavError::MalformedChunkLength) => {
            return Err(DurationWavError::MalformedChunkLength);
        }
        Err(gummy_synth::codec::RiffWavError::MalformedFmtChunk) => {
            return Err(DurationWavError::MalformedFmtChunk);
        }
    };

    let Some(channels) = wav.channels else {
        return Ok(None);
    };
    let Some(sample_rate) = wav.sample_rate else {
        return Ok(None);
    };
    let Some(bits_per_sample) = wav.bits_per_sample else {
        return Ok(None);
    };
    let Some(data) = wav.data else {
        return Ok(None);
    };
    let bytes_per_sample = u32::from(bits_per_sample).div_ceil(8);
    let frame_bytes = u32::from(channels).saturating_mul(bytes_per_sample);
    if sample_rate == 0 || frame_bytes == 0 {
        return Ok(None);
    }
    Ok(Some(
        data.len() as f64 / frame_bytes as f64 / sample_rate as f64,
    ))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn riff(chunks: &[([u8; 4], Vec<u8>)]) -> Vec<u8> {
        let mut bytes = b"RIFF\0\0\0\0WAVE".to_vec();
        for (id, chunk) in chunks {
            bytes.extend_from_slice(id);
            bytes.extend_from_slice(&(chunk.len() as u32).to_le_bytes());
            bytes.extend_from_slice(chunk);
            if chunk.len() % 2 != 0 {
                bytes.push(0);
            }
        }
        bytes
    }

    fn pcm_fmt(
        audio_format: u16,
        channels: u16,
        sample_rate: u32,
        bits_per_sample: u16,
    ) -> Vec<u8> {
        let bytes_per_sample = u32::from(bits_per_sample).div_ceil(8);
        let block_align = u32::from(channels).saturating_mul(bytes_per_sample) as u16;
        let byte_rate = sample_rate.saturating_mul(u32::from(block_align));
        let mut fmt = Vec::with_capacity(16);
        fmt.extend_from_slice(&audio_format.to_le_bytes());
        fmt.extend_from_slice(&channels.to_le_bytes());
        fmt.extend_from_slice(&sample_rate.to_le_bytes());
        fmt.extend_from_slice(&byte_rate.to_le_bytes());
        fmt.extend_from_slice(&block_align.to_le_bytes());
        fmt.extend_from_slice(&bits_per_sample.to_le_bytes());
        fmt
    }

    fn playback_error(bytes: &[u8]) -> PlaybackWavError {
        match parse_pcm_s16_wav_core(bytes) {
            Ok(_) => panic!("expected playback WAV parsing to fail"),
            Err(error) => error,
        }
    }

    fn duration_error(bytes: &[u8]) -> DurationWavError {
        match wav_duration_seconds_core(bytes) {
            Ok(_) => panic!("expected WAV duration probing to fail"),
            Err(error) => error,
        }
    }

    #[test]
    fn playback_parser_keeps_pcm_s16_contract_and_legacy_error_messages() {
        let valid = riff(&[
            (*b"JUNK", vec![1, 2, 3]),
            (*b"fmt ", pcm_fmt(1, 2, 8_000, 16)),
            (
                *b"data",
                [1000_i16.to_le_bytes(), (-2000_i16).to_le_bytes()].concat(),
            ),
        ]);
        let wav = parse_pcm_s16_wav_core(&valid).expect("16-bit PCM WAV parses");
        assert_eq!(wav.samples, vec![1000, -2000]);
        assert_eq!(wav.sample_rate, 8_000);
        assert_eq!(wav.channels, 2);
        assert!((wav.duration - 1.0 / 8_000.0).abs() < f64::EPSILON);

        let malformed_length = b"RIFF\0\0\0\0WAVEdata\x04\0\0\0\0\0";
        let short_fmt = riff(&[(*b"fmt ", vec![0; 15])]);
        let missing_fmt = riff(&[(*b"data", vec![0, 0])]);
        let zero_channels = riff(&[(*b"fmt ", pcm_fmt(1, 0, 8_000, 16)), (*b"data", Vec::new())]);
        let zero_rate = riff(&[(*b"fmt ", pcm_fmt(1, 1, 0, 16)), (*b"data", Vec::new())]);
        let float_format = riff(&[(*b"fmt ", pcm_fmt(3, 1, 8_000, 16)), (*b"data", vec![0, 0])]);
        let unsupported_depth = riff(&[(*b"fmt ", pcm_fmt(1, 1, 8_000, 8)), (*b"data", vec![0])]);
        let odd_sample_bytes = riff(&[
            (*b"fmt ", pcm_fmt(1, 1, 8_000, 16)),
            (*b"data", vec![0, 0, 1]),
        ]);

        let cases: &[(&[u8], &str)] = &[
            (
                b"not a wav",
                "SDL3 synth playback requires PCM WAV bytes produced by the Rust synth renderer.",
            ),
            (malformed_length, "Could not play synth WAV bytes: malformed chunk length."),
            (short_fmt.as_slice(), "Could not play synth WAV bytes: malformed fmt chunk."),
            (missing_fmt.as_slice(), "Could not play synth WAV bytes: missing fmt chunk."),
            (
                zero_channels.as_slice(),
                "Could not play synth WAV bytes: channel count must be greater than zero.",
            ),
            (
                zero_rate.as_slice(),
                "Could not play synth WAV bytes: sample rate must be greater than zero.",
            ),
            (
                float_format.as_slice(),
                "SDL3 synth playback requires uncompressed PCM WAV bytes.",
            ),
            (
                unsupported_depth.as_slice(),
                "SDL3 synth playback requires 16-bit PCM WAV bytes.",
            ),
            (
                odd_sample_bytes.as_slice(),
                "Could not play synth WAV bytes: sample data length is not aligned to 16-bit samples.",
            ),
        ];
        for (bytes, expected) in cases {
            assert_eq!(playback_error(bytes).message(), *expected);
        }
    }

    #[test]
    fn duration_probe_retains_its_permissive_metadata_policy() {
        assert_eq!(
            wav_duration_seconds_core(b"not a wav").expect("non-WAV is not an error"),
            None
        );

        let unknown_and_padded = riff(&[
            (*b"JUNK", vec![1]),
            (*b"fmt ", pcm_fmt(3, 2, 8_000, 16)),
            (*b"data", vec![0; 16]),
        ]);
        assert_eq!(
            wav_duration_seconds_core(&unknown_and_padded).expect("metadata duration is available"),
            Some(16.0 / 4.0 / 8_000.0)
        );

        let zero_rate = riff(&[(*b"fmt ", pcm_fmt(1, 1, 0, 16)), (*b"data", vec![0, 0])]);
        let zero_channels = riff(&[(*b"fmt ", pcm_fmt(1, 0, 8_000, 16)), (*b"data", vec![0, 0])]);
        let missing_data = riff(&[(*b"fmt ", pcm_fmt(1, 1, 8_000, 16))]);
        assert_eq!(
            wav_duration_seconds_core(&zero_rate).expect("zero rate remains no duration"),
            None
        );
        assert_eq!(
            wav_duration_seconds_core(&zero_channels).expect("zero channels remains no duration"),
            None
        );
        assert_eq!(
            wav_duration_seconds_core(&missing_data).expect("missing data remains no duration"),
            None
        );

        let malformed_length = b"RIFF\0\0\0\0WAVEdata\x04\0\0\0\0\0";
        let short_fmt = riff(&[(*b"fmt ", vec![0; 15])]);
        assert_eq!(
            duration_error(malformed_length).message(),
            "Could not load WAV sound: malformed chunk length."
        );
        assert_eq!(
            duration_error(&short_fmt).message(),
            "Could not load WAV sound: malformed fmt chunk."
        );
    }
}
