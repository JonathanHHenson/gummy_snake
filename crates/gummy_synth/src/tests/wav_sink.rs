use crate::wav_sink::{
    riff_sizes_for_frames, StereoPcmWavSink, StereoWavSinkError, MAX_RIFF_PCM_FRAMES,
};
use crate::*;
use std::cell::RefCell;
use std::io::{self, Cursor, Seek, SeekFrom, Write};
use std::rc::Rc;

#[derive(Clone, Default)]
struct SharedCursor(Rc<RefCell<Cursor<Vec<u8>>>>);

impl SharedCursor {
    fn bytes(&self) -> Vec<u8> {
        self.0.borrow().get_ref().clone()
    }
}

impl Write for SharedCursor {
    fn write(&mut self, buffer: &[u8]) -> io::Result<usize> {
        self.0.borrow_mut().write(buffer)
    }

    fn flush(&mut self) -> io::Result<()> {
        self.0.borrow_mut().flush()
    }
}

impl Seek for SharedCursor {
    fn seek(&mut self, position: SeekFrom) -> io::Result<u64> {
        self.0.borrow_mut().seek(position)
    }
}

#[test]
fn streaming_wav_sink_patches_header_after_incremental_pcm_blocks() {
    let writer = SharedCursor::default();
    let observer = writer.clone();
    let mut sink = StereoPcmWavSink::new(writer, 48_000).expect("WAV header writes");

    assert_eq!(sink.frame_count(), 0);
    sink.write_interleaved_i16(&[1, -2])
        .expect("first PCM block writes");
    sink.write_interleaved_i16(&[i16::MIN, i16::MAX])
        .expect("second PCM block writes");
    assert_eq!(sink.frame_count(), 2);

    let before_finish = observer.bytes();
    assert_eq!(
        u32::from_le_bytes(before_finish[4..8].try_into().unwrap()),
        0
    );
    assert_eq!(
        u32::from_le_bytes(before_finish[40..44].try_into().unwrap()),
        0
    );

    sink.finish().expect("WAV header patches");
    let wav = observer.bytes();
    assert_eq!(wav.len(), 52);
    assert_eq!(&wav[0..4], b"RIFF");
    assert_eq!(u32::from_le_bytes(wav[4..8].try_into().unwrap()), 44);
    assert_eq!(&wav[8..12], b"WAVE");
    assert_eq!(&wav[12..16], b"fmt ");
    assert_eq!(u16::from_le_bytes(wav[20..22].try_into().unwrap()), 1);
    assert_eq!(u16::from_le_bytes(wav[22..24].try_into().unwrap()), 2);
    assert_eq!(u32::from_le_bytes(wav[24..28].try_into().unwrap()), 48_000);
    assert_eq!(u32::from_le_bytes(wav[28..32].try_into().unwrap()), 192_000);
    assert_eq!(u16::from_le_bytes(wav[32..34].try_into().unwrap()), 4);
    assert_eq!(u16::from_le_bytes(wav[34..36].try_into().unwrap()), 16);
    assert_eq!(&wav[36..40], b"data");
    assert_eq!(u32::from_le_bytes(wav[40..44].try_into().unwrap()), 8);
    assert_eq!(&wav[44..], &[1, 0, 254, 255, 0, 128, 255, 127]);

    let metadata = codec::parse_riff_wav(&wav).expect("patched WAV is structurally valid");
    assert_eq!(metadata.data, Some(&wav[44..]));
}

#[test]
fn streaming_wav_sink_rejects_incomplete_stereo_frames_without_writing_pcm() {
    let writer = Cursor::new(Vec::new());
    let mut sink = StereoPcmWavSink::new(writer, 8_000).expect("WAV header writes");

    let error = sink
        .write_interleaved_i16(&[123])
        .expect_err("a partial stereo frame must be rejected");
    assert!(matches!(
        error,
        StereoWavSinkError::OddInterleavedSampleCount { sample_count: 1 }
    ));
    assert_eq!(sink.frame_count(), 0);

    let wav = sink
        .finish()
        .expect("empty WAV header patches")
        .into_inner();
    assert_eq!(wav.len(), 44);
    assert_eq!(u32::from_le_bytes(wav[4..8].try_into().unwrap()), 36);
    assert_eq!(u32::from_le_bytes(wav[40..44].try_into().unwrap()), 0);
}

#[test]
fn streaming_wav_sink_enforces_riff_size_limit_before_writing() {
    let maximum = riff_sizes_for_frames(MAX_RIFF_PCM_FRAMES).expect("RIFF maximum fits");
    assert_eq!(maximum, (u32::MAX - 3, u32::MAX - 39));

    let error = riff_sizes_for_frames(MAX_RIFF_PCM_FRAMES + 1)
        .expect_err("a RIFF header cannot represent another stereo frame");
    assert!(matches!(
        error,
        StereoWavSinkError::RiffSizeOverflow {
            frames
        } if frames == MAX_RIFF_PCM_FRAMES + 1
    ));
}

#[test]
fn streaming_wav_sink_rejects_invalid_sample_rates() {
    let error = match StereoPcmWavSink::new(Cursor::new(Vec::new()), 0) {
        Ok(_) => panic!("zero is not a valid WAV sample rate"),
        Err(error) => error,
    };
    assert!(matches!(error, StereoWavSinkError::InvalidSampleRate));

    let error = match StereoPcmWavSink::new(Cursor::new(Vec::new()), u32::MAX) {
        Ok(_) => panic!("byte rate must fit the WAV header"),
        Err(error) => error,
    };
    assert!(matches!(error, StereoWavSinkError::InvalidSampleRate));
}
