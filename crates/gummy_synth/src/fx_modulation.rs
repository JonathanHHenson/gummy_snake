use super::*;

pub(crate) fn fx_distortion(left: &[f64], right: &[f64], opts: &OptMap) -> (Vec<f64>, Vec<f64>) {
    let amount = float_opt(opts, "distort", float_opt(opts, "amount", 0.5)).clamp(0.0, 0.999);
    let k = (2.0 * amount) / (1.0 - amount).max(0.001);
    let distort = |sample: f64| sample * (1.0 + k) / (1.0 + k * sample.abs());
    (
        left.iter().map(|sample| distort(*sample)).collect(),
        right.iter().map(|sample| distort(*sample)).collect(),
    )
}

pub(crate) fn fx_pan(left: &[f64], right: &[f64], opts: &OptMap) -> (Vec<f64>, Vec<f64>) {
    let pan = float_opt(opts, "pan", 0.0).clamp(-1.0, 1.0);
    balance2_pair(left, right, pan)
}

pub(crate) fn fx_bandpass_pair(
    left: &[f64],
    right: &[f64],
    opts: &OptMap,
    sample_rate: u32,
    resonant: bool,
    normalised: bool,
) -> (Vec<f64>, Vec<f64>) {
    let centre = note_frequency(float_opt(opts, "centre", 100.0)).max(20.0);
    let public_res = float_opt(opts, "res", if resonant { 0.5 } else { 0.6 }).clamp(0.0, 0.99);
    let rq = sonic_filter_rq(public_res);
    let bandwidth = (centre * rq).max(20.0);
    let low_cut = (centre - bandwidth * 0.5).max(20.0);
    let high_cut = (centre + bandwidth * 0.5).max(low_cut + 20.0);
    let band = |samples: &[f64]| -> Vec<f64> {
        let high = highpass(samples, low_cut, sample_rate);
        let mut banded = lowpass(&high, high_cut, sample_rate);
        if resonant {
            banded = resonant_emphasis(samples, &banded, public_res);
        }
        banded
    };
    let mut out_left = band(left);
    let mut out_right = band(right);
    if normalised {
        let normalised_pair = normalise_pair(&out_left, &out_right, 1.0);
        out_left = normalised_pair.0;
        out_right = normalised_pair.1;
    }
    (out_left, out_right)
}

pub(crate) fn fx_band_eq(
    left: &[f64],
    right: &[f64],
    opts: &OptMap,
    sample_rate: u32,
) -> (Vec<f64>, Vec<f64>) {
    let freq = note_frequency(float_opt(opts, "freq", 100.0)).max(20.0);
    let public_res = float_opt(opts, "res", 0.6).clamp(0.0, 0.99);
    let db = float_opt(opts, "db", 0.6);
    let gain = 10.0_f64.powf(db / 20.0) - 1.0;
    let bandwidth = (freq * sonic_filter_rq(public_res)).max(20.0);
    let apply = |samples: &[f64]| -> Vec<f64> {
        let band = lowpass(
            &highpass(samples, (freq - bandwidth * 0.5).max(20.0), sample_rate),
            freq + bandwidth * 0.5,
            sample_rate,
        );
        samples
            .iter()
            .zip(band.iter())
            .map(|(dry, band)| dry + band * gain)
            .collect()
    };
    (apply(left), apply(right))
}

pub(crate) fn fx_tanh(left: &[f64], right: &[f64], opts: &OptMap) -> (Vec<f64>, Vec<f64>) {
    let krunch = (float_opt(opts, "krunch", 5.0).max(0.0)).max(0.0001) * 5.0;
    let gain = 1.0 + krunch / 8.0;
    let shape = |sample: f64| (sample * krunch).tanh() / krunch * gain;
    (
        left.iter().map(|sample| shape(*sample)).collect(),
        right.iter().map(|sample| shape(*sample)).collect(),
    )
}

pub(crate) fn fx_pitch_shift(left: &[f64], right: &[f64], opts: &OptMap) -> (Vec<f64>, Vec<f64>) {
    let pitch = float_opt(opts, "pitch", 0.0).clamp(-72.0, 24.0);
    let ratio = 2.0_f64.powf(pitch / 12.0);
    (
        pitch_shift_to_len(left, ratio),
        pitch_shift_to_len(right, ratio),
    )
}

pub(crate) fn fx_ring_mod(
    left: &[f64],
    right: &[f64],
    opts: &OptMap,
    sample_rate: u32,
    start_time_seconds: f64,
) -> (Vec<f64>, Vec<f64>) {
    let freq = note_frequency(float_opt(opts, "freq", 30.0)).max(1.0);
    let mod_amp = float_opt(opts, "mod_amp", 1.0).max(0.0);
    let apply = |index: usize, sample: f64| {
        let elapsed = start_time_seconds + index as f64 / sample_rate as f64;
        (sample * (1.0 + mod_amp * (TAU * freq * elapsed).sin())).clamp(-1.0, 1.0)
    };
    (
        left.iter()
            .enumerate()
            .map(|(index, sample)| apply(index, *sample))
            .collect(),
        right
            .iter()
            .enumerate()
            .map(|(index, sample)| apply(index, *sample))
            .collect(),
    )
}

pub(crate) fn fx_octaver(
    left: &[f64],
    right: &[f64],
    opts: &OptMap,
    sample_rate: u32,
) -> (Vec<f64>, Vec<f64>) {
    let super_amp = float_opt(opts, "super_amp", 1.0).max(0.0);
    let sub_amp = float_opt(opts, "sub_amp", 1.0).max(0.0);
    let subsub_amp = float_opt(opts, "subsub_amp", 1.0).max(0.0);
    let apply = |samples: &[f64]| -> Vec<f64> {
        let direct = lowpass(samples, 440.0, sample_rate);
        let sub = octave_toggle(&direct, 1);
        let subsub = octave_toggle(&direct, 2);
        direct
            .iter()
            .enumerate()
            .map(|(index, sample)| {
                let super_oct = sample.abs() * 2.0;
                super_oct * super_amp
                    + sample * sub[index] * sub_amp
                    + sample * subsub[index] * subsub_amp
            })
            .collect()
    };
    (apply(left), apply(right))
}

pub(crate) fn fx_vowel(
    left: &[f64],
    right: &[f64],
    opts: &OptMap,
    sample_rate: u32,
) -> (Vec<f64>, Vec<f64>) {
    let vowel = float_opt(opts, "vowel_sound", 1.0).round().clamp(1.0, 5.0) as usize;
    let voice = float_opt(opts, "voice", 0.0).round().clamp(0.0, 4.0) as usize;
    let scale = [1.25, 1.05, 0.95, 0.82, 0.65][voice];
    let formants = match vowel {
        1 => [800.0, 1150.0, 2900.0],
        2 => [400.0, 1600.0, 2700.0],
        3 => [350.0, 1700.0, 2700.0],
        4 => [450.0, 800.0, 2830.0],
        _ => [325.0, 700.0, 2530.0],
    };
    let apply = |samples: &[f64]| -> Vec<f64> {
        let mut acc = vec![0.0; samples.len()];
        for (formant_index, formant) in formants.iter().enumerate() {
            let center: f64 = *formant * scale;
            let width = center * 0.18;
            let band = lowpass(
                &highpass(samples, (center - width).max(20.0), sample_rate),
                center + width,
                sample_rate,
            );
            let gain = [1.0, 0.65, 0.35][formant_index];
            for (index, sample) in band.iter().enumerate() {
                acc[index] += sample * gain;
            }
        }
        acc
    };
    (apply(left), apply(right))
}

pub(crate) fn fx_flanger(
    left: &[f64],
    right: &[f64],
    opts: &OptMap,
    sample_rate: u32,
    start_time_seconds: f64,
) -> (Vec<f64>, Vec<f64>) {
    let phase = float_opt(opts, "phase", 4.0).max(0.001);
    let wave = float_opt(opts, "wave", 4.0) as i32;
    let delay_ms = float_opt(opts, "delay", 5.0).max(0.0);
    let depth_ms = float_opt(opts, "depth", 5.0).max(0.0);
    let feedback = float_opt(opts, "feedback", 0.0).clamp(0.0, 0.95);
    let invert = float_opt(opts, "invert_flange", 0.0) >= 0.5;
    let apply = |samples: &[f64], stereo_invert: bool| -> Vec<f64> {
        let mut output = Vec::with_capacity(samples.len());
        let mut delayed_feedback = 0.0;
        for (index, sample) in samples.iter().enumerate() {
            let elapsed = start_time_seconds + index as f64 / sample_rate as f64;
            let mut amount = lfo_amount_from_opts(opts, wave, elapsed, phase);
            if stereo_invert {
                amount = 1.0 - amount;
            }
            let delay = (delay_ms + depth_ms * amount) / 1000.0;
            let delay_samples = (delay * sample_rate as f64).round() as usize;
            let delayed = index
                .checked_sub(delay_samples)
                .and_then(|source| samples.get(source))
                .copied()
                .unwrap_or(0.0)
                + delayed_feedback * feedback;
            delayed_feedback = delayed;
            let flange = if invert { -delayed } else { delayed };
            output.push((sample + flange) * 0.5);
        }
        output
    };
    let stereo_invert = float_opt(opts, "stereo_invert_wave", 0.0) >= 0.5;
    (apply(left, false), apply(right, stereo_invert))
}

pub(crate) fn fx_slicer(
    left: &[f64],
    right: &[f64],
    opts: &OptMap,
    sample_rate: u32,
    start_time_seconds: f64,
) -> (Vec<f64>, Vec<f64>) {
    let phase = float_opt(opts, "phase", 0.25).max(0.001);
    let wave = float_opt(opts, "wave", 1.0) as i32;
    let amp_min = float_opt(opts, "amp_min", 0.0);
    let amp_max = float_opt(opts, "amp_max", 1.0);
    let smooth = float_opt(opts, "smooth", 0.0).max(0.0);
    let smooth_up = float_opt(opts, "smooth_up", 0.0).max(0.0);
    let smooth_down = float_opt(opts, "smooth_down", 0.0).max(0.0);
    let alpha_smooth = smoothing_alpha(smooth, sample_rate);
    let alpha_up = smoothing_alpha(smooth_up, sample_rate);
    let alpha_down = smoothing_alpha(smooth_down, sample_rate);
    let control_alpha = smoothing_alpha(slicer_control_block_seconds(sample_rate), sample_rate);
    let mut lag_ud_gain: Option<f64> = None;
    let mut lag_gain: Option<f64> = None;
    let mut control_gain: Option<f64> = None;

    let mut out_left = Vec::with_capacity(left.len());
    let mut out_right = Vec::with_capacity(right.len());
    for (index, (left_sample, right_sample)) in left.iter().zip(right.iter()).enumerate() {
        let elapsed = start_time_seconds + index as f64 / sample_rate as f64;
        let amount = lfo_amount_from_opts(opts, wave, elapsed, phase);
        let target_gain = amp_min + (amp_max - amp_min) * amount;
        let previous_ud = lag_ud_gain.unwrap_or(target_gain);
        let alpha_ud = if target_gain >= previous_ud {
            alpha_up
        } else {
            alpha_down
        };
        let smoothed_ud = previous_ud + (target_gain - previous_ud) * alpha_ud;
        lag_ud_gain = Some(smoothed_ud);

        let previous_lag = lag_gain.unwrap_or(smoothed_ud);
        let lagged_gain = previous_lag + (smoothed_ud - previous_lag) * alpha_smooth;
        lag_gain = Some(lagged_gain);

        let previous_control = control_gain.unwrap_or(lagged_gain);
        let gain = previous_control + (lagged_gain - previous_control) * control_alpha;
        control_gain = Some(gain);
        out_left.push(left_sample * gain);
        out_right.push(right_sample * gain);
    }
    (out_left, out_right)
}

pub(crate) fn slicer_control_block_seconds(sample_rate: u32) -> f64 {
    64.0 / sample_rate.max(1) as f64
}

pub(crate) fn fx_wobble(
    left: &[f64],
    right: &[f64],
    opts: &OptMap,
    sample_rate: u32,
    start_time_seconds: f64,
) -> (Vec<f64>, Vec<f64>) {
    let phase = float_opt(opts, "phase", 0.5).max(0.001);
    let wave = float_opt(opts, "wave", 0.0) as i32;
    let cutoff_min = float_opt(opts, "cutoff_min", 60.0);
    let cutoff_max = float_opt(opts, "cutoff_max", float_opt(opts, "cutoff", 120.0));
    let filter = float_opt(opts, "filter", 0.0).round() as i32;
    let cutoff_min_hz = note_frequency(cutoff_min).max(20.0);
    let cutoff_max_hz = note_frequency(cutoff_max)
        .max(cutoff_min_hz)
        .min(sample_rate as f64 * 0.45);
    let public_res = float_opt(opts, "res", 0.8).clamp(0.0, 0.99);
    let rq = sonic_filter_rq(public_res);
    let cutoff_at = |index: usize| {
        let elapsed = start_time_seconds + index as f64 / sample_rate as f64;
        let amount = lfo_amount_from_opts(opts, wave, elapsed, phase);
        lin_exp(amount, cutoff_min_hz, cutoff_max_hz).clamp(20.0, sample_rate as f64 * 0.45)
    };
    resonant_modulated_filter_pair(
        left,
        right,
        sample_rate,
        if filter == 1 {
            FilterKind::High
        } else {
            FilterKind::Low
        },
        rq,
        cutoff_at,
    )
}

pub(crate) fn resonant_modulated_filter_pair(
    left: &[f64],
    right: &[f64],
    sample_rate: u32,
    kind: FilterKind,
    rq: f64,
    mut cutoff_at: impl FnMut(usize) -> f64,
) -> (Vec<f64>, Vec<f64>) {
    let mut left_state = BiquadState::default();
    let mut right_state = BiquadState::default();
    let mut out_left = Vec::with_capacity(left.len());
    let mut out_right = Vec::with_capacity(right.len());
    let output_gain = resonant_output_gain(rq);
    for (index, (left_sample, right_sample)) in left.iter().zip(right.iter()).enumerate() {
        let coeffs = BiquadCoefficients::resonant_filter(kind, cutoff_at(index), sample_rate, rq);
        out_left.push(left_state.process(*left_sample, coeffs) * output_gain);
        out_right.push(right_state.process(*right_sample, coeffs) * output_gain);
    }
    (out_left, out_right)
}

#[derive(Clone, Copy, Default)]
pub(crate) struct BiquadState {
    z1: f64,
    z2: f64,
}

impl BiquadState {
    pub(crate) fn process(&mut self, input: f64, coeffs: BiquadCoefficients) -> f64 {
        let output = coeffs.b0 * input + self.z1;
        self.z1 = coeffs.b1 * input - coeffs.a1 * output + self.z2;
        self.z2 = coeffs.b2 * input - coeffs.a2 * output;
        output
    }
}

#[derive(Clone, Copy)]
pub(crate) struct BiquadCoefficients {
    b0: f64,
    b1: f64,
    b2: f64,
    a1: f64,
    a2: f64,
}

impl BiquadCoefficients {
    pub(crate) fn resonant_filter(
        kind: FilterKind,
        cutoff_hz: f64,
        sample_rate: u32,
        rq: f64,
    ) -> Self {
        let q = (1.0 / rq.clamp(0.001, 1.0)).clamp(0.5, 20.0);
        Self::filter(kind, cutoff_hz, sample_rate, q)
    }

    pub(crate) fn filter(kind: FilterKind, cutoff_hz: f64, sample_rate: u32, q: f64) -> Self {
        let nyquist = sample_rate as f64 * 0.5;
        let cutoff = cutoff_hz.clamp(20.0, nyquist * 0.9);
        let q = q.clamp(0.1, 20.0);
        let omega = TAU * cutoff / sample_rate as f64;
        let sin_omega = omega.sin();
        let cos_omega = omega.cos();
        let alpha = sin_omega / (2.0 * q);
        let (b0, b1, b2) = match kind {
            FilterKind::Low => (
                (1.0 - cos_omega) * 0.5,
                1.0 - cos_omega,
                (1.0 - cos_omega) * 0.5,
            ),
            FilterKind::High => (
                (1.0 + cos_omega) * 0.5,
                -(1.0 + cos_omega),
                (1.0 + cos_omega) * 0.5,
            ),
        };
        let a0 = 1.0 + alpha;
        let a1 = -2.0 * cos_omega;
        let a2 = 1.0 - alpha;
        Self {
            b0: b0 / a0,
            b1: b1 / a0,
            b2: b2 / a0,
            a1: a1 / a0,
            a2: a2 / a0,
        }
    }
}

pub(crate) fn lin_exp(amount: f64, min_hz: f64, max_hz: f64) -> f64 {
    let amount = amount.clamp(0.0, 1.0);
    if min_hz <= 0.0 || max_hz <= min_hz {
        return min_hz.max(0.0);
    }
    min_hz * (max_hz / min_hz).powf(amount)
}
