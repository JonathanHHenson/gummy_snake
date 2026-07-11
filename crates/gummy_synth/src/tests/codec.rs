use crate::*;

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

fn pcm_fmt(audio_format: u16, channels: u16, sample_rate: u32, bits_per_sample: u16) -> Vec<u8> {
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

fn decode_error(bytes: &[u8]) -> SynthError {
    match decode_wav_stereo(bytes) {
        Ok(_) => panic!("expected WAV decoding to fail"),
        Err(error) => error,
    }
}

#[test]
fn riff_wav_scanner_ignores_unknown_chunks_and_handles_odd_padding() {
    let bytes = riff(&[
        (*b"JUNK", vec![1, 2, 3]),
        (*b"fmt ", pcm_fmt(1, 2, 8_000, 16)),
        (*b"LIST", vec![4]),
        (*b"data", vec![1, 0, 2, 0]),
    ]);

    let metadata = crate::codec::parse_riff_wav(&bytes).expect("valid RIFF/WAV metadata");

    assert_eq!(metadata.audio_format, Some(1));
    assert_eq!(metadata.channels, Some(2));
    assert_eq!(metadata.sample_rate, Some(8_000));
    assert_eq!(metadata.bits_per_sample, Some(16));
    assert_eq!(metadata.data, Some(&[1, 0, 2, 0][..]));
}

#[test]
fn synth_wav_decoder_preserves_supported_pcm_widths_and_channel_order() {
    let cases = [
        (8, vec![0, 255], vec![-1.0, 127.0 / 128.0]),
        (
            16,
            [(-32768_i16).to_le_bytes(), 32767_i16.to_le_bytes()].concat(),
            vec![-1.0, 32767.0 / 32768.0],
        ),
        (
            32,
            [
                (-2147483648_i32).to_le_bytes(),
                2147483647_i32.to_le_bytes(),
            ]
            .concat(),
            vec![-1.0, 2147483647.0 / 2147483648.0],
        ),
    ];

    for (bits_per_sample, data, expected) in cases {
        let bytes = riff(&[
            (*b"fmt ", pcm_fmt(1, 1, 8_000, bits_per_sample)),
            (*b"data", data),
        ]);
        let decoded = decode_wav_stereo(&bytes).expect("supported mono PCM decodes");

        assert_eq!(decoded.sample_rate, 8_000);
        assert!(!decoded.stereo);
        assert_eq!(decoded.left.len(), expected.len());
        for ((left, right), expected) in
            decoded.left.iter().zip(&decoded.right).zip(expected.iter())
        {
            assert!((left - expected).abs() < 1e-12);
            assert!((right - expected).abs() < 1e-12);
        }
    }

    let bytes = riff(&[
        (*b"fmt ", pcm_fmt(1, 2, 8_000, 16)),
        (
            *b"data",
            [1000_i16.to_le_bytes(), (-2000_i16).to_le_bytes()].concat(),
        ),
    ]);
    let decoded = decode_wav_stereo(&bytes).expect("supported stereo PCM decodes");
    assert!(decoded.stereo);
    assert_eq!(decoded.left, vec![1000.0 / 32768.0]);
    assert_eq!(decoded.right, vec![-2000.0 / 32768.0]);
}

#[test]
fn synth_wav_decoder_preserves_format_and_frame_edge_policies() {
    let float_tagged_pcm = riff(&[
        (*b"fmt ", pcm_fmt(3, 1, 8_000, 16)),
        (*b"data", 1000_i16.to_le_bytes().to_vec()),
    ]);
    assert_eq!(
        decode_wav_stereo(&float_tagged_pcm)
            .expect("synth retains its legacy width/channel-only policy")
            .left,
        vec![1000.0 / 32768.0]
    );

    let zero_rate = riff(&[
        (*b"fmt ", pcm_fmt(1, 1, 0, 16)),
        (*b"data", 0_i16.to_le_bytes().to_vec()),
    ]);
    assert_eq!(
        decode_wav_stereo(&zero_rate)
            .expect("decoder preserves zero sample-rate metadata")
            .sample_rate,
        0
    );

    let zero_channels = riff(&[(*b"fmt ", pcm_fmt(1, 0, 8_000, 16)), (*b"data", Vec::new())]);
    assert_eq!(
        decode_error(&zero_channels).message(),
        "Unsupported PCM WAV format; expected mono or stereo 8/16/32-bit PCM."
    );

    let unsupported_depth = riff(&[
        (*b"fmt ", pcm_fmt(1, 1, 8_000, 24)),
        (*b"data", vec![0, 0, 0]),
    ]);
    assert_eq!(
        decode_error(&unsupported_depth).message(),
        "Unsupported PCM WAV format; expected mono or stereo 8/16/32-bit PCM."
    );

    let incomplete_stereo_frame = riff(&[
        (*b"fmt ", pcm_fmt(1, 2, 8_000, 16)),
        (*b"data", vec![1, 0, 2, 0, 3, 0]),
    ]);
    let decoded = decode_wav_stereo(&incomplete_stereo_frame)
        .expect("legacy decoder drops an incomplete final stereo frame");
    assert_eq!(decoded.left, vec![1.0 / 32768.0]);
    assert_eq!(decoded.right, vec![2.0 / 32768.0]);
}

#[test]
fn synth_wav_decoder_reports_structural_and_missing_chunk_errors() {
    let malformed_length = b"RIFF\0\0\0\0WAVEdata\x04\0\0\0\0\0";
    let short_fmt = riff(&[(*b"fmt ", vec![0; 15])]);
    let missing_fmt = riff(&[(*b"data", vec![0, 0])]);
    let missing_data = riff(&[(*b"fmt ", pcm_fmt(1, 1, 8_000, 16))]);

    let cases: &[(&[u8], &str)] = &[
        (
            b"not a wav",
            "Rust synth sample rendering currently supports PCM WAV bytes.",
        ),
        (malformed_length, "Malformed WAV chunk length."),
        (&short_fmt, "Malformed WAV fmt chunk."),
        (&missing_fmt, "WAV missing fmt chunk."),
        (&missing_data, "WAV missing data chunk."),
    ];
    for (bytes, expected) in cases {
        assert_eq!(decode_error(bytes).message(), *expected);
    }
}
