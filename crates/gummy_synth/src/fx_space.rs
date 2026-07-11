use super::*;

pub(crate) fn fx_krush_shape(left: &[f64], right: &[f64], opts: &OptMap) -> (Vec<f64>, Vec<f64>) {
    let gain = float_opt(opts, "gain", 5.0).max(0.001);
    let distort = |sample: f64| {
        let abs_sample = sample.abs();
        let squared = abs_sample * abs_sample;
        (squared + gain * abs_sample) / (squared + abs_sample * (gain - 1.0) + 1.0)
    };
    (
        left.iter().map(|sample| distort(*sample)).collect(),
        right.iter().map(|sample| distort(*sample)).collect(),
    )
}

pub(crate) fn fx_reverb(
    left: &[f64],
    right: &[f64],
    opts: &OptMap,
    sample_rate: u32,
) -> (Vec<f64>, Vec<f64>) {
    let room = float_opt(opts, "room", 0.6).clamp(0.0, 1.0);
    let damp = float_opt(opts, "damp", 0.5).clamp(0.0, 1.0);
    let internal_mix = float_opt(opts, "reverb_mix", float_opt(opts, "mix", 0.4)).clamp(0.0, 1.0);
    let width = float_opt(opts, "width", 1.0).clamp(0.0, 1.0);
    let tail_seconds = float_opt(opts, "tail", 0.7 + room * 2.4).max(0.05);
    let input_len = left.len().max(right.len());
    if input_len == 0 {
        return (Vec::new(), Vec::new());
    }
    let output_len = input_len + (tail_seconds * sample_rate as f64).ceil() as usize;
    let feedback = 0.70 + room * 0.28;
    let damp1 = damp * 0.4;
    let damp2 = 1.0 - damp1;
    let fixed_gain = 0.015;
    let wet = 0.42;
    let wet1 = wet * (width * 0.5 + 0.5);
    let wet2 = wet * ((1.0 - width) * 0.5);

    let comb_left = [1116, 1188, 1277, 1356, 1422, 1491, 1557, 1617];
    let comb_right = [1139, 1211, 1300, 1379, 1445, 1514, 1580, 1640];
    let allpass_left = [556, 441, 341, 225];
    let allpass_right = [579, 464, 364, 248];
    let mut combs_left: Vec<CombFilter> = comb_left
        .iter()
        .map(|delay| CombFilter::new(scaled_reverb_delay(*delay, sample_rate)))
        .collect();
    let mut combs_right: Vec<CombFilter> = comb_right
        .iter()
        .map(|delay| CombFilter::new(scaled_reverb_delay(*delay, sample_rate)))
        .collect();
    let mut allpasses_left: Vec<AllpassFilter> = allpass_left
        .iter()
        .map(|delay| AllpassFilter::new(scaled_reverb_delay(*delay, sample_rate), 0.5))
        .collect();
    let mut allpasses_right: Vec<AllpassFilter> = allpass_right
        .iter()
        .map(|delay| AllpassFilter::new(scaled_reverb_delay(*delay, sample_rate), 0.5))
        .collect();

    let mut out_left = Vec::with_capacity(output_len);
    let mut out_right = Vec::with_capacity(output_len);
    for index in 0..output_len {
        let input_left = left.get(index).copied().unwrap_or(0.0);
        let input_right = right.get(index).copied().unwrap_or(0.0);
        let comb_input_left = (input_left * 0.75 + input_right * 0.25) * fixed_gain;
        let comb_input_right = (input_right * 0.75 + input_left * 0.25) * fixed_gain;

        let mut wet_left = 0.0;
        for comb in &mut combs_left {
            wet_left += comb.process(comb_input_left, feedback, damp1, damp2);
        }
        let mut wet_right = 0.0;
        for comb in &mut combs_right {
            wet_right += comb.process(comb_input_right, feedback, damp1, damp2);
        }
        for allpass in &mut allpasses_left {
            wet_left = allpass.process(wet_left);
        }
        for allpass in &mut allpasses_right {
            wet_right = allpass.process(wet_right);
        }
        let stereo_wet_left = wet_left * wet1 + wet_right * wet2;
        let stereo_wet_right = wet_right * wet1 + wet_left * wet2;
        out_left.push(input_left * (1.0 - internal_mix) + stereo_wet_left * internal_mix);
        out_right.push(input_right * (1.0 - internal_mix) + stereo_wet_right * internal_mix);
    }
    (out_left, out_right)
}

struct CombFilter {
    buffer: Vec<f64>,
    index: usize,
    filter_store: f64,
}

impl CombFilter {
    fn new(size: usize) -> Self {
        Self {
            buffer: vec![0.0; size.max(1)],
            index: 0,
            filter_store: 0.0,
        }
    }

    fn process(&mut self, input: f64, feedback: f64, damp1: f64, damp2: f64) -> f64 {
        let output = self.buffer[self.index];
        self.filter_store = output * damp2 + self.filter_store * damp1;
        self.buffer[self.index] = input + self.filter_store * feedback;
        self.index = (self.index + 1) % self.buffer.len();
        output
    }
}

struct AllpassFilter {
    buffer: Vec<f64>,
    index: usize,
    feedback: f64,
}

impl AllpassFilter {
    fn new(size: usize, feedback: f64) -> Self {
        Self {
            buffer: vec![0.0; size.max(1)],
            index: 0,
            feedback,
        }
    }

    fn process(&mut self, input: f64) -> f64 {
        let buffered = self.buffer[self.index];
        let output = buffered - input;
        self.buffer[self.index] = input + buffered * self.feedback;
        self.index = (self.index + 1) % self.buffer.len();
        output
    }
}

pub(crate) fn scaled_reverb_delay(delay_at_44k: usize, sample_rate: u32) -> usize {
    ((delay_at_44k as f64 * sample_rate as f64 / 44_100.0).round() as usize).max(1)
}

pub(crate) fn fx_echo(
    left: &[f64],
    right: &[f64],
    opts: &OptMap,
    sample_rate: u32,
) -> (Vec<f64>, Vec<f64>) {
    let max_phase = float_opt(opts, "max_phase", 2.0).max(0.001);
    let phase = float_opt(opts, "phase", 0.25).clamp(0.001, max_phase);
    let decay = float_opt(opts, "decay", 2.0).max(0.0);
    let delay_samples = ((phase * sample_rate as f64).round() as usize).max(1);
    let repeats = if decay <= 0.0 {
        0
    } else {
        (decay / phase).ceil().max(1.0) as usize
    };
    let output_len = left.len().max(right.len()) + delay_samples * repeats;
    let feedback = if decay <= 0.0 {
        0.0
    } else {
        0.001_f64.powf(phase / decay).clamp(-0.999, 0.999)
    };
    let mut out_left = vec![0.0; output_len];
    let mut out_right = vec![0.0; output_len];
    for index in 0..output_len {
        let delayed_left = if index >= delay_samples {
            out_left[index - delay_samples] * feedback
        } else {
            0.0
        };
        let delayed_right = if index >= delay_samples {
            out_right[index - delay_samples] * feedback
        } else {
            0.0
        };
        out_left[index] = left.get(index).copied().unwrap_or(0.0) + delayed_left;
        out_right[index] = right.get(index).copied().unwrap_or(0.0) + delayed_right;
    }
    (out_left, out_right)
}

pub(crate) fn fx_gverb(
    left: &[f64],
    right: &[f64],
    opts: &OptMap,
    sample_rate: u32,
) -> (Vec<f64>, Vec<f64>) {
    let room = (float_opt(opts, "room", 10.0) / 10.0).clamp(0.0, 2.0);
    let release = float_opt(opts, "release", 3.0).max(0.05);
    let spread = float_opt(opts, "spread", 0.5).clamp(0.0, 1.0);
    let dry = float_opt(opts, "dry", 1.0).max(0.0);
    let ref_level = float_opt(opts, "ref_level", 0.7).max(0.0);
    let tail_level = float_opt(opts, "tail_level", 0.5).max(0.0);
    let delays = [0.019, 0.043, 0.083, 0.149, 0.211, 0.293];
    let extra = (release * sample_rate as f64) as usize;
    let mut out_left = scale_samples(left, dry);
    let mut out_right = scale_samples(right, dry);
    out_left.resize(out_left.len() + extra, 0.0);
    out_right.resize(out_right.len() + extra, 0.0);
    for (delay_index, delay) in delays.iter().enumerate() {
        let offset = ((*delay * (1.0 + room)) * sample_rate as f64) as usize;
        let gain = (ref_level * 0.24 + tail_level * 0.2) * 0.68_f64.powi(delay_index as i32);
        for (index, (left_sample, right_sample)) in left.iter().zip(right.iter()).enumerate() {
            let target = index + offset;
            if target >= out_left.len() {
                break;
            }
            let cross_l = left_sample * (1.0 - spread) + right_sample * spread;
            let cross_r = right_sample * (1.0 - spread) + left_sample * spread;
            out_left[target] += cross_l * gain;
            out_right[target] += cross_r * gain;
        }
    }
    let damp = float_opt(opts, "damp", 0.5).clamp(0.0, 1.0);
    if damp > 0.0 {
        let cutoff = 12_000.0 * (1.0 - damp) + 1_200.0 * damp;
        out_left = lowpass(&out_left, cutoff, sample_rate);
        out_right = lowpass(&out_right, cutoff, sample_rate);
    }
    (out_left, out_right)
}

pub(crate) fn fx_panslicer(
    left: &[f64],
    right: &[f64],
    opts: &OptMap,
    sample_rate: u32,
    start_time_seconds: f64,
) -> (Vec<f64>, Vec<f64>) {
    let phase = float_opt(opts, "phase", 0.25).max(0.001);
    let wave = float_opt(opts, "wave", 1.0) as i32;
    let pan_min = float_opt(opts, "pan_min", -1.0).clamp(-1.0, 1.0);
    let pan_max = float_opt(opts, "pan_max", 1.0).clamp(-1.0, 1.0);
    let mut out_left = Vec::with_capacity(left.len());
    let mut out_right = Vec::with_capacity(right.len());
    let mut previous_pan = 0.0;
    for (index, (left_sample, right_sample)) in left.iter().zip(right.iter()).enumerate() {
        let elapsed = start_time_seconds + index as f64 / sample_rate as f64;
        let amount = lfo_amount_from_opts(opts, wave, elapsed, phase);
        let target_pan = pan_min + (pan_max - pan_min) * amount;
        previous_pan = smooth_modulated_value(previous_pan, target_pan, opts, sample_rate);
        let (balanced_left, balanced_right) =
            balance2_sample(*left_sample, *right_sample, previous_pan);
        out_left.push(balanced_left);
        out_right.push(balanced_right);
    }
    (out_left, out_right)
}

pub(crate) fn fx_ixi_techno(
    left: &[f64],
    right: &[f64],
    opts: &OptMap,
    sample_rate: u32,
    start_time_seconds: f64,
) -> (Vec<f64>, Vec<f64>) {
    let mut local = opts.clone();
    local
        .entry("wave".to_owned())
        .or_insert(SynthValue::Float(3.0));
    local
        .entry("phase".to_owned())
        .or_insert(SynthValue::Float(4.0));
    local
        .entry("cutoff_min".to_owned())
        .or_insert(SynthValue::Float(60.0));
    local
        .entry("cutoff_max".to_owned())
        .or_insert(SynthValue::Float(120.0));
    fx_wobble(left, right, &local, sample_rate, start_time_seconds)
}

pub(crate) fn fx_compressor(
    left: &[f64],
    right: &[f64],
    opts: &OptMap,
    sample_rate: u32,
) -> (Vec<f64>, Vec<f64>) {
    let threshold = float_opt(opts, "threshold", 0.2).max(0.0001);
    let slope_above = float_opt(opts, "slope_above", 0.5);
    let slope_below = float_opt(opts, "slope_below", 1.0);
    let clamp_time = float_opt(opts, "clamp_time", 0.01).max(0.0);
    let relax_time = float_opt(opts, "relax_time", 0.01).max(0.0);
    let attack_alpha = smoothing_alpha(clamp_time, sample_rate);
    let release_alpha = smoothing_alpha(relax_time, sample_rate);
    let mut gain = 1.0;
    let mut out_left = Vec::with_capacity(left.len());
    let mut out_right = Vec::with_capacity(right.len());
    for (left_sample, right_sample) in left.iter().zip(right.iter()) {
        let level = left_sample.abs().max(right_sample.abs()).max(1e-9);
        let target_level = if level > threshold {
            threshold + (level - threshold) * slope_above
        } else {
            threshold * (level / threshold).powf(slope_below)
        };
        let target_gain = (target_level / level).clamp(0.0, 16.0);
        let alpha = if target_gain < gain {
            attack_alpha
        } else {
            release_alpha
        };
        gain += (target_gain - gain) * alpha;
        out_left.push(left_sample * gain);
        out_right.push(right_sample * gain);
    }
    (out_left, out_right)
}

pub(crate) fn fx_whammy(left: &[f64], right: &[f64], opts: &OptMap) -> (Vec<f64>, Vec<f64>) {
    let transpose = float_opt(opts, "transpose", 12.0);
    let ratio = 2.0_f64.powf(transpose / 12.0);
    (
        pitch_shift_to_len(left, ratio),
        pitch_shift_to_len(right, ratio),
    )
}

pub(crate) fn fx_filter_pair(
    left: &[f64],
    right: &[f64],
    opts: &OptMap,
    sample_rate: u32,
    kind: FilterKind,
    resonant: bool,
    normalised: bool,
) -> (Vec<f64>, Vec<f64>) {
    let cutoff = note_frequency(float_opt(opts, "cutoff", 100.0)).max(20.0);
    let res = if resonant {
        float_opt(opts, "res", 0.5).clamp(0.0, 0.99)
    } else {
        0.0
    };
    let mut out_left = filter_samples(left, cutoff, sample_rate, kind, res);
    let mut out_right = filter_samples(right, cutoff, sample_rate, kind, res);
    if normalised {
        let normalised_pair = normalise_pair(&out_left, &out_right, 1.0);
        out_left = normalised_pair.0;
        out_right = normalised_pair.1;
    }
    (out_left, out_right)
}

pub(crate) fn fx_normaliser(left: &[f64], right: &[f64], opts: &OptMap) -> (Vec<f64>, Vec<f64>) {
    normalise_pair(left, right, float_opt(opts, "level", 1.0).max(0.0))
}
