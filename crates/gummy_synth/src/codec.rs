//! Minimal RIFF/WAV container parsing shared by synth sample decoding and canvas.
//!
//! This module deliberately reports only container structure and `fmt `/` `data`
//! metadata. Callers retain their own supported-format policies and error mapping.

/// Structural failures while scanning a RIFF/WAV container.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum RiffWavError {
    /// The payload is not a RIFF/WAVE container.
    InvalidHeader,
    /// A chunk payload extends beyond the supplied bytes.
    MalformedChunkLength,
    /// A `fmt ` chunk is too short to contain canonical PCM metadata.
    MalformedFmtChunk,
}

/// Metadata collected from a RIFF/WAV chunk stream.
///
/// The scanner intentionally keeps optional fields: consumers decide which chunks
/// and values are required for their own operation. If a chunk occurs more than
/// once, its last value wins.
#[derive(Clone, Debug)]
pub struct RiffWavMetadata<'a> {
    pub audio_format: Option<u16>,
    pub channels: Option<u16>,
    pub sample_rate: Option<u32>,
    pub bits_per_sample: Option<u16>,
    pub data: Option<&'a [u8]>,
}

/// Scan a RIFF/WAVE chunk stream without assigning an audio-format policy.
///
/// Unknown chunks are ignored and odd-sized chunks must include their RIFF padding
/// byte. Chunk payloads and padding are bounds-checked.
pub fn parse_riff_wav(bytes: &[u8]) -> Result<RiffWavMetadata<'_>, RiffWavError> {
    if bytes.len() < 12 || &bytes[0..4] != b"RIFF" || &bytes[8..12] != b"WAVE" {
        return Err(RiffWavError::InvalidHeader);
    }

    let mut metadata = RiffWavMetadata {
        audio_format: None,
        channels: None,
        sample_rate: None,
        bits_per_sample: None,
        data: None,
    };
    let mut offset = 12usize;

    while offset.checked_add(8).is_some_and(|end| end <= bytes.len()) {
        let chunk_id = &bytes[offset..offset + 4];
        let chunk_len = u32::from_le_bytes([
            bytes[offset + 4],
            bytes[offset + 5],
            bytes[offset + 6],
            bytes[offset + 7],
        ]) as usize;
        offset += 8;
        if offset
            .checked_add(chunk_len)
            .is_none_or(|end| end > bytes.len())
        {
            return Err(RiffWavError::MalformedChunkLength);
        }

        let chunk = &bytes[offset..offset + chunk_len];
        match chunk_id {
            b"fmt " => {
                if chunk.len() < 16 {
                    return Err(RiffWavError::MalformedFmtChunk);
                }
                metadata.audio_format = Some(u16::from_le_bytes([chunk[0], chunk[1]]));
                metadata.channels = Some(u16::from_le_bytes([chunk[2], chunk[3]]));
                metadata.sample_rate =
                    Some(u32::from_le_bytes([chunk[4], chunk[5], chunk[6], chunk[7]]));
                metadata.bits_per_sample = Some(u16::from_le_bytes([chunk[14], chunk[15]]));
            }
            b"data" => metadata.data = Some(chunk),
            _ => {}
        }
        let padded_len = chunk_len + (chunk_len % 2);
        if offset
            .checked_add(padded_len)
            .is_none_or(|end| end > bytes.len())
        {
            return Err(RiffWavError::MalformedChunkLength);
        }
        offset += padded_len;
    }

    Ok(metadata)
}
