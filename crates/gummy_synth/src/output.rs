use super::*;

pub(crate) fn output_limit_pair(
    left: &[f64],
    right: &[f64],
    sample_rate: u32,
) -> (Vec<f64>, Vec<f64>) {
    output_limit_window(left, right, 0, left.len().max(right.len()), sample_rate)
}

pub(crate) fn output_limit_prefix(
    left: &[f64],
    right: &[f64],
    len: usize,
    sample_rate: u32,
) -> (Vec<f64>, Vec<f64>) {
    output_limit_window(left, right, 0, len, sample_rate)
}

pub(crate) fn output_limit_window(
    left: &[f64],
    right: &[f64],
    start: usize,
    len: usize,
    sample_rate: u32,
) -> (Vec<f64>, Vec<f64>) {
    let process_len = start.saturating_add(len);
    let sample_rate_f64 = sample_rate.max(1) as f64;
    let lookahead_samples = (OUTPUT_LIMIT_RELEASE_SECONDS * sample_rate_f64).ceil() as usize;
    let analysis_len = process_len
        .saturating_add(lookahead_samples)
        .max(process_len);
    let release_alpha = 1.0 - (-1.0 / (OUTPUT_LIMIT_RELEASE_SECONDS * sample_rate_f64)).exp();
    let mut levels = Vec::with_capacity(analysis_len);
    for index in 0..analysis_len {
        levels.push(
            left.get(index)
                .copied()
                .unwrap_or(0.0)
                .abs()
                .max(right.get(index).copied().unwrap_or(0.0).abs()),
        );
    }

    let mut max_indices: VecDeque<usize> = VecDeque::new();
    let mut next_index = 0usize;
    let mut gain = 1.0;
    let mut out_left = Vec::with_capacity(len);
    let mut out_right = Vec::with_capacity(len);

    for index in 0..process_len {
        let window_end = index
            .saturating_add(lookahead_samples)
            .min(analysis_len.saturating_sub(1));
        while next_index <= window_end {
            while max_indices
                .back()
                .is_some_and(|candidate| levels[*candidate] <= levels[next_index])
            {
                max_indices.pop_back();
            }
            max_indices.push_back(next_index);
            next_index += 1;
        }
        while max_indices
            .front()
            .is_some_and(|candidate| *candidate < index)
        {
            max_indices.pop_front();
        }

        let peak = max_indices
            .front()
            .and_then(|candidate| levels.get(*candidate))
            .copied()
            .unwrap_or(0.0);
        let target_gain = if peak > OUTPUT_LIMIT_CEILING {
            OUTPUT_LIMIT_CEILING / peak
        } else {
            1.0
        };
        if target_gain < gain {
            gain = target_gain;
        } else {
            gain += (target_gain - gain) * release_alpha;
        }
        if index >= start {
            let left_sample = left.get(index).copied().unwrap_or(0.0);
            let right_sample = right.get(index).copied().unwrap_or(0.0);
            out_left.push((left_sample * gain).clamp(-OUTPUT_LIMIT_CEILING, OUTPUT_LIMIT_CEILING));
            out_right
                .push((right_sample * gain).clamp(-OUTPUT_LIMIT_CEILING, OUTPUT_LIMIT_CEILING));
        }
    }

    (out_left, out_right)
}

pub(crate) fn samples_to_interleaved_i16(left: &[f64], right: &[f64], frames: usize) -> Vec<i16> {
    let mut output = Vec::with_capacity(frames * 2);
    for index in 0..frames {
        for sample in [
            left.get(index).copied().unwrap_or(0.0),
            right.get(index).copied().unwrap_or(0.0),
        ] {
            output.push((sample.clamp(-1.0, 1.0) * 32767.0).round() as i16);
        }
    }
    output
}

pub(crate) fn stereo_wav_bytes(left: &[f64], right: &[f64], sample_rate: u32) -> Vec<u8> {
    let mut payload = Vec::with_capacity(44 + left.len().min(right.len()) * 4);
    let frames = left.len().min(right.len()) as u32;
    let data_len = frames * 4;
    payload.extend_from_slice(b"RIFF");
    payload.extend_from_slice(&(36 + data_len).to_le_bytes());
    payload.extend_from_slice(b"WAVE");
    payload.extend_from_slice(b"fmt ");
    payload.extend_from_slice(&16u32.to_le_bytes());
    payload.extend_from_slice(&1u16.to_le_bytes());
    payload.extend_from_slice(&2u16.to_le_bytes());
    payload.extend_from_slice(&sample_rate.to_le_bytes());
    payload.extend_from_slice(&(sample_rate * 4).to_le_bytes());
    payload.extend_from_slice(&4u16.to_le_bytes());
    payload.extend_from_slice(&16u16.to_le_bytes());
    payload.extend_from_slice(b"data");
    payload.extend_from_slice(&data_len.to_le_bytes());
    for (left_sample, right_sample) in left.iter().zip(right.iter()) {
        for sample in [*left_sample, *right_sample] {
            let clamped = sample.clamp(-1.0, 1.0);
            payload.extend_from_slice(&((clamped * 32767.0).round() as i16).to_le_bytes());
        }
    }
    payload
}
