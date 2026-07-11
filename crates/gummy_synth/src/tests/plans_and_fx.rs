use crate::*;

#[test]
fn primitive_synth_keys_are_recognized_and_render() {
    let sample_rate = 8_000;
    for name in PRIMITIVE_SYNTH_KEYS {
        let kind = synth_kind(name);
        assert_ne!(
            kind,
            SynthKind::Unknown,
            "{name} is not mapped to a primitive synth kind"
        );
        let mut opts = OptMap::new();
        opts.insert("release".to_owned(), SynthValue::Float(0.04));
        if kind == SynthKind::Layered {
            let mut layer = OptMap::new();
            layer.insert("wave".to_owned(), SynthValue::String("sine".to_owned()));
            layer.insert("transpose".to_owned(), SynthValue::Float(0.0));
            layer.insert("amp".to_owned(), SynthValue::Float(1.0));
            layer.insert("opts".to_owned(), SynthValue::Dict(OptMap::new()));
            opts.insert(
                "layers".to_owned(),
                SynthValue::List(vec![SynthValue::Dict(layer)]),
            );
        }
        let event = EventPayload {
            node_id: 44,
            order: 0,
            kind: "play".to_owned(),
            time_seconds: 0.0,
            value: SynthValue::Float(60.0),
            opts,
            synth_name: (*name).to_owned(),
            synth_opts: OptMap::new(),
            fx_chain: Vec::new(),
            controls: Vec::new(),
        };

        let (left, right) = render_event(&event, sample_rate).expect("primitive synth renders");

        assert!(!left.is_empty(), "{name} produced no left samples");
        assert_eq!(
            left.len(),
            right.len(),
            "{name} produced mismatched stereo samples"
        );
        let peak = left
            .iter()
            .chain(right.iter())
            .map(|sample| sample.abs())
            .fold(0.0, f64::max);
        if kind == SynthKind::Silence {
            assert_eq!(peak, 0.0, "{name} should be silent");
        } else {
            assert!(peak > 1e-5, "{name} rendered silence");
        }
    }
}

#[test]
fn plan_renderer_groups_matching_fx_handles_into_shared_bus() {
    let mut synth_opts = OptMap::new();
    synth_opts.insert("release".to_owned(), SynthValue::Float(0.04));
    synth_opts.insert("amp".to_owned(), SynthValue::Float(1.0));
    let mut fx_opts = OptMap::new();
    fx_opts.insert("threshold".to_owned(), SynthValue::Float(0.05));
    fx_opts.insert("slope_above".to_owned(), SynthValue::Float(0.15));
    let event = EventPayload {
        node_id: 70,
        order: 0,
        kind: "play".to_owned(),
        time_seconds: 0.0,
        value: SynthValue::Float(48.0),
        opts: synth_opts,
        synth_name: "_saw".to_owned(),
        synth_opts: OptMap::new(),
        fx_chain: vec![FxPayload {
            id: 9,
            name: "compressor".to_owned(),
            opts: fx_opts.clone(),
        }],
        controls: Vec::new(),
    };
    let mut same_bus_second = event.clone();
    same_bus_second.node_id = 71;
    same_bus_second.value = SynthValue::Float(55.0);
    let mut separate_bus_second = same_bus_second.clone();
    separate_bus_second.fx_chain[0].id = 10;

    let shared_bus = render_plan_events(vec![event.clone(), same_bus_second], 0.08, 8_000)
        .expect("shared FX bus renders");
    let separate_buses = render_plan_events(vec![event, separate_bus_second], 0.08, 8_000)
        .expect("separate FX buses render");

    assert_ne!(shared_bus, separate_buses);
}

#[test]
fn documented_fx_keys_are_native_and_audible() {
    let sample_rate = 8_000;
    let left: Vec<f64> = (0..1_024)
        .map(|index| {
            let t = index as f64 / sample_rate as f64;
            (TAU * 180.0 * t).sin() * 0.45 + (TAU * 1_600.0 * t).sin() * 0.2
        })
        .collect();
    let right: Vec<f64> = (0..1_024)
        .map(|index| {
            let t = index as f64 / sample_rate as f64;
            (TAU * 260.0 * t).sin() * 0.35 + (TAU * 2_200.0 * t).sin() * 0.15
        })
        .collect();
    let names = [
        "bitcrusher",
        "krush",
        "reverb",
        "gverb",
        "level",
        "echo",
        "slicer",
        "panslicer",
        "wobble",
        "ixi_techno",
        "compressor",
        "whammy",
        "rlpf",
        "nrlpf",
        "rhpf",
        "nrhpf",
        "hpf",
        "nhpf",
        "lpf",
        "nlpf",
        "normaliser",
        "distortion",
        "pan",
        "bpf",
        "nbpf",
        "rbpf",
        "nrbpf",
        "band_eq",
        "tanh",
        "pitch_shift",
        "ring_mod",
        "octaver",
        "vowel",
        "flanger",
    ];

    for name in names {
        let opts = test_fx_opts(name);
        let (out_left, out_right) =
            apply_fx(name, left.clone(), right.clone(), &opts, sample_rate, 0.125);

        assert!(!out_left.is_empty(), "{name} produced no left samples");
        assert!(!out_right.is_empty(), "{name} produced no right samples");
        assert!(
            signal_changed(&left, &right, &out_left, &out_right),
            "{name} did not audibly affect the signal"
        );
    }
}

fn test_fx_opts(name: &str) -> OptMap {
    let mut opts = OptMap::new();
    match name {
        "bitcrusher" => {
            opts.insert("sample_rate".to_owned(), SynthValue::Float(1_000.0));
            opts.insert("bits".to_owned(), SynthValue::Float(4.0));
        }
        "level" => {
            opts.insert("amp".to_owned(), SynthValue::Float(0.5));
        }
        "normaliser" => {
            opts.insert("level".to_owned(), SynthValue::Float(0.25));
        }
        "pan" => {
            opts.insert("pan".to_owned(), SynthValue::Float(-0.8));
        }
        "pitch_shift" => {
            opts.insert("pitch".to_owned(), SynthValue::Float(7.0));
        }
        "band_eq" => {
            opts.insert("db".to_owned(), SynthValue::Float(-9.0));
        }
        "ring_mod" => {
            opts.insert("mod_amp".to_owned(), SynthValue::Float(0.8));
        }
        "flanger" => {
            opts.insert("feedback".to_owned(), SynthValue::Float(0.25));
        }
        "compressor" => {
            opts.insert("threshold".to_owned(), SynthValue::Float(0.05));
            opts.insert("slope_above".to_owned(), SynthValue::Float(0.25));
        }
        _ => {}
    }
    opts
}

fn signal_changed(left: &[f64], right: &[f64], out_left: &[f64], out_right: &[f64]) -> bool {
    if out_left.len() != left.len() || out_right.len() != right.len() {
        return true;
    }
    let left_delta = left
        .iter()
        .zip(out_left.iter())
        .map(|(before, after)| (before - after).abs())
        .sum::<f64>();
    let right_delta = right
        .iter()
        .zip(out_right.iter())
        .map(|(before, after)| (before - after).abs())
        .sum::<f64>();
    (left_delta + right_delta) / (left.len() + right.len()) as f64 > 1e-5
}
