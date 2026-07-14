//! Incremental RIFF/WAV output for canonical stereo 16-bit PCM blocks.
//!
//! This owns only its fixed 44-byte header and reusable block-sized encoding
//! scratch, then writes each supplied interleaved block to its `Write + Seek` target.
//! It is an internal foundation: current public render APIs still use their
//! established byte-returning path until they are explicitly routed through a
//! block renderer and this sink.

use super::*;
use std::fmt;
use std::io::{self, Seek, SeekFrom, Write};

const WAV_HEADER_BYTES: u64 = 44;
const PCM_FRAME_BYTES: u64 = 4;
const RIFF_HEADER_BYTES_BEFORE_DATA: u64 = 36;
const PCM_CHANNELS: u16 = 2;
const PCM_BITS_PER_SAMPLE: u16 = 16;
const PCM_BLOCK_ALIGN: u16 = 4;

/// The greatest number of stereo 16-bit PCM frames representable by a RIFF WAV
/// header with this fixed 44-byte layout.
#[cfg(test)]
pub(crate) const MAX_RIFF_PCM_FRAMES: u64 =
    (u32::MAX as u64 - RIFF_HEADER_BYTES_BEFORE_DATA) / PCM_FRAME_BYTES;

#[derive(Debug)]
pub(crate) enum StereoWavSinkError {
    Io(io::Error),
    InvalidSampleRate,
    OddInterleavedSampleCount {
        sample_count: usize,
    },
    FrameCountOverflow {
        current_frames: u64,
        appended_frames: u64,
    },
    RiffSizeOverflow {
        frames: u64,
    },
    StreamPositionOverflow,
    Finished,
    Failed,
    NotFinished,
}

impl fmt::Display for StereoWavSinkError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Io(error) => write!(formatter, "streaming WAV I/O failed: {error}"),
            Self::InvalidSampleRate => write!(formatter, "WAV sample rate must be greater than zero"),
            Self::OddInterleavedSampleCount { sample_count } => write!(
                formatter,
                "stereo PCM requires an even interleaved sample count; got {sample_count}"
            ),
            Self::FrameCountOverflow {
                current_frames,
                appended_frames,
            } => write!(
                formatter,
                "WAV frame count overflow after {current_frames} existing and {appended_frames} appended frames"
            ),
            Self::RiffSizeOverflow { frames } => write!(
                formatter,
                "{frames} stereo PCM frames exceed the RIFF WAV 32-bit size limit"
            ),
            Self::StreamPositionOverflow => {
                write!(formatter, "WAV header position cannot be represented by the stream")
            }
            Self::Finished => write!(formatter, "WAV sink has already been finished"),
            Self::Failed => write!(
                formatter,
                "WAV sink cannot continue after an earlier stream I/O failure"
            ),
            Self::NotFinished => write!(formatter, "WAV sink has not been finished"),
        }
    }
}

impl std::error::Error for StereoWavSinkError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            Self::Io(error) => Some(error),
            _ => None,
        }
    }
}

/// Checked RIFF and `data` chunk sizes for a number of stereo PCM frames.
pub(crate) fn riff_sizes_for_frames(frames: u64) -> Result<(u32, u32), StereoWavSinkError> {
    let data_bytes = frames
        .checked_mul(PCM_FRAME_BYTES)
        .ok_or(StereoWavSinkError::RiffSizeOverflow { frames })?;
    let riff_size = RIFF_HEADER_BYTES_BEFORE_DATA
        .checked_add(data_bytes)
        .ok_or(StereoWavSinkError::RiffSizeOverflow { frames })?;
    let riff_size =
        u32::try_from(riff_size).map_err(|_| StereoWavSinkError::RiffSizeOverflow { frames })?;
    let data_bytes =
        u32::try_from(data_bytes).map_err(|_| StereoWavSinkError::RiffSizeOverflow { frames })?;
    Ok((riff_size, data_bytes))
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum SinkState {
    Open,
    Finished,
    Failed,
}

/// A streaming RIFF WAV sink for interleaved stereo 16-bit PCM.
///
/// The sink writes its fixed PCM header at construction, writes each complete
/// frame block directly to the target, and patches the RIFF and `data` sizes in
/// [`finish`](Self::finish). The caller retains ownership of each PCM block;
/// this sink retains only reusable block-sized encoding scratch and never builds
/// a whole WAV payload or creates a temporary file.
pub(crate) struct StereoPcmWavSink<W> {
    writer: W,
    block_bytes: Vec<u8>,
    header_start: u64,
    data_end: u64,
    frames: u64,
    state: SinkState,
}

impl<W: Write + Seek> StereoPcmWavSink<W> {
    pub(crate) fn new(mut writer: W, sample_rate: u32) -> Result<Self, StereoWavSinkError> {
        if sample_rate == 0 {
            return Err(StereoWavSinkError::InvalidSampleRate);
        }
        let bytes_per_second = sample_rate
            .checked_mul(u32::from(PCM_BLOCK_ALIGN))
            .ok_or(StereoWavSinkError::InvalidSampleRate)?;
        let header_start = writer.stream_position().map_err(StereoWavSinkError::Io)?;
        let data_end = header_start
            .checked_add(WAV_HEADER_BYTES)
            .ok_or(StereoWavSinkError::StreamPositionOverflow)?;
        writer
            .write_all(&wav_header(sample_rate, bytes_per_second, 0, 0))
            .map_err(StereoWavSinkError::Io)?;

        Ok(Self {
            writer,
            block_bytes: Vec::new(),
            header_start,
            data_end,
            frames: 0,
            state: SinkState::Open,
        })
    }

    #[cfg(test)]
    pub(crate) fn frame_count(&self) -> u64 {
        self.frames
    }

    /// Append only complete little-endian stereo frames.
    pub(crate) fn write_interleaved_i16(
        &mut self,
        samples: &[i16],
    ) -> Result<(), StereoWavSinkError> {
        self.require_open()?;
        if !samples.len().is_multiple_of(usize::from(PCM_CHANNELS)) {
            return Err(StereoWavSinkError::OddInterleavedSampleCount {
                sample_count: samples.len(),
            });
        }
        let appended_frames =
            u64::try_from(samples.len() / usize::from(PCM_CHANNELS)).map_err(|_| {
                StereoWavSinkError::FrameCountOverflow {
                    current_frames: self.frames,
                    appended_frames: u64::MAX,
                }
            })?;
        let next_frames = self.frames.checked_add(appended_frames).ok_or(
            StereoWavSinkError::FrameCountOverflow {
                current_frames: self.frames,
                appended_frames,
            },
        )?;
        riff_sizes_for_frames(next_frames)?;
        let appended_bytes = appended_frames.checked_mul(PCM_FRAME_BYTES).ok_or(
            StereoWavSinkError::RiffSizeOverflow {
                frames: next_frames,
            },
        )?;
        let next_data_end = self
            .data_end
            .checked_add(appended_bytes)
            .ok_or(StereoWavSinkError::StreamPositionOverflow)?;

        self.block_bytes.clear();
        self.block_bytes.reserve(std::mem::size_of_val(samples));
        for sample in samples {
            self.block_bytes.extend_from_slice(&sample.to_le_bytes());
        }
        if let Err(error) = self.writer.write_all(&self.block_bytes) {
            self.state = SinkState::Failed;
            return Err(StereoWavSinkError::Io(error));
        }
        self.frames = next_frames;
        self.data_end = next_data_end;
        Ok(())
    }

    /// Patch the placeholder RIFF and `data` sizes, flush, and return the writer.
    #[cfg(test)]
    pub(crate) fn finish(mut self) -> Result<W, StereoWavSinkError> {
        self.patch_header()?;
        Ok(self.writer)
    }

    /// Return a writer already finalized through the `PcmSink` contract.
    pub(crate) fn into_finished_writer(self) -> Result<W, StereoWavSinkError> {
        match self.state {
            SinkState::Finished => Ok(self.writer),
            SinkState::Open => Err(StereoWavSinkError::NotFinished),
            SinkState::Failed => Err(StereoWavSinkError::Failed),
        }
    }

    fn require_open(&self) -> Result<(), StereoWavSinkError> {
        match self.state {
            SinkState::Open => Ok(()),
            SinkState::Finished => Err(StereoWavSinkError::Finished),
            SinkState::Failed => Err(StereoWavSinkError::Failed),
        }
    }

    fn patch_header(&mut self) -> Result<(), StereoWavSinkError> {
        self.require_open()?;
        let (riff_size, data_size) = riff_sizes_for_frames(self.frames)?;
        let riff_size_offset = self
            .header_start
            .checked_add(4)
            .ok_or(StereoWavSinkError::StreamPositionOverflow)?;
        let data_size_offset = self
            .header_start
            .checked_add(40)
            .ok_or(StereoWavSinkError::StreamPositionOverflow)?;
        let result = (|| -> io::Result<()> {
            self.writer.seek(SeekFrom::Start(riff_size_offset))?;
            self.writer.write_all(&riff_size.to_le_bytes())?;
            self.writer.seek(SeekFrom::Start(data_size_offset))?;
            self.writer.write_all(&data_size.to_le_bytes())?;
            self.writer.seek(SeekFrom::Start(self.data_end))?;
            self.writer.flush()
        })();
        if let Err(error) = result {
            self.state = SinkState::Failed;
            return Err(StereoWavSinkError::Io(error));
        }
        self.state = SinkState::Finished;
        Ok(())
    }
}

impl<W: Write + Seek> PcmSink for StereoPcmWavSink<W> {
    fn write_interleaved_i16(&mut self, samples: &[i16]) -> SynthResult<SinkWrite> {
        StereoPcmWavSink::write_interleaved_i16(self, samples)
            .map_err(|error| SynthError::new(error.to_string()))?;
        Ok(SinkWrite::Accepted)
    }

    fn finish(&mut self) -> SynthResult<()> {
        self.patch_header()
            .map_err(|error| SynthError::new(error.to_string()))
    }
}

fn wav_header(sample_rate: u32, bytes_per_second: u32, riff_size: u32, data_size: u32) -> [u8; 44] {
    let mut header = [0; WAV_HEADER_BYTES as usize];
    header[0..4].copy_from_slice(b"RIFF");
    header[4..8].copy_from_slice(&riff_size.to_le_bytes());
    header[8..12].copy_from_slice(b"WAVE");
    header[12..16].copy_from_slice(b"fmt ");
    header[16..20].copy_from_slice(&16u32.to_le_bytes());
    header[20..22].copy_from_slice(&1u16.to_le_bytes());
    header[22..24].copy_from_slice(&PCM_CHANNELS.to_le_bytes());
    header[24..28].copy_from_slice(&sample_rate.to_le_bytes());
    header[28..32].copy_from_slice(&bytes_per_second.to_le_bytes());
    header[32..34].copy_from_slice(&PCM_BLOCK_ALIGN.to_le_bytes());
    header[34..36].copy_from_slice(&PCM_BITS_PER_SAMPLE.to_le_bytes());
    header[36..40].copy_from_slice(b"data");
    header[40..44].copy_from_slice(&data_size.to_le_bytes());
    header
}
