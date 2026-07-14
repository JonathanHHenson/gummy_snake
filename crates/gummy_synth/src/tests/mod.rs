mod block_contract;
mod causal_normaliser;
mod codec;
mod compiled_program;
mod effects;
mod executor;
mod plans_and_fx;
mod playback_and_output;
mod sample_and_dsp;
mod samples_and_output;
mod stateful_block_renderer;
mod voices;
mod wav_sink;

fn max_abs_pair(left: &[f64], right: &[f64]) -> f64 {
    left.iter()
        .chain(right.iter())
        .map(|sample| sample.abs())
        .fold(0.0, f64::max)
}

fn average_abs_delta(samples: &[f64]) -> f64 {
    if samples.len() < 2 {
        return 0.0;
    }
    samples
        .windows(2)
        .map(|pair| (pair[1] - pair[0]).abs())
        .sum::<f64>()
        / (samples.len() - 1) as f64
}
