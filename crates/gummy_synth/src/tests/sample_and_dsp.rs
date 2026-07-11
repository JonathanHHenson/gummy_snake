use crate::*;

#[test]
fn decode_pcm_sample_sign_extends_16_bit_values() {
    assert_eq!(decode_pcm_sample(&0i16.to_le_bytes()), 0.0);
    assert!(decode_pcm_sample(&(-32768i16).to_le_bytes()) <= -1.0);
    assert!(decode_pcm_sample(&32767i16.to_le_bytes()) > 0.99);
}

#[test]
fn high_rate_sample_antialias_filters_folded_treble() {
    let sample_rate = 8_000;
    let input: Vec<f64> = (0..4_000)
        .map(|index| if index % 2 == 0 { 1.0 } else { -1.0 })
        .collect();

    let (filtered_left, filtered_right) =
        anti_alias_sample_segment(input.clone(), input, 8.0, sample_rate);
    let tail_rms = (filtered_left[1_000..]
        .iter()
        .chain(filtered_right[1_000..].iter())
        .map(|sample| sample * sample)
        .sum::<f64>()
        / ((filtered_left.len() - 1_000) * 2) as f64)
        .sqrt();

    assert!(tail_rms < 0.1, "tail_rms={tail_rms}");
}

#[test]
fn high_rate_sample_output_smoothing_tames_piercing_treble() {
    let sample_rate = 44_100;
    let input: Vec<f64> = (0..4_410)
        .map(|index| (TAU * 12_000.0 * index as f64 / sample_rate as f64).sin())
        .collect();

    let (filtered_left, filtered_right) =
        smooth_high_rate_sample_output(input.clone(), input.clone(), 12.0, sample_rate);
    let input_rms =
        (input.iter().map(|sample| sample * sample).sum::<f64>() / input.len() as f64).sqrt();
    let filtered_rms = (filtered_left[1_000..]
        .iter()
        .chain(filtered_right[1_000..].iter())
        .map(|sample| sample * sample)
        .sum::<f64>()
        / ((filtered_left.len() - 1_000) * 2) as f64)
        .sqrt();

    assert!(
        filtered_rms < input_rms * 0.98,
        "filtered_rms={filtered_rms}"
    );
    assert!(
        filtered_rms > input_rms * 0.8,
        "filtered_rms={filtered_rms}"
    );
}
