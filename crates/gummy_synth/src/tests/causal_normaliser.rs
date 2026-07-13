use crate::*;

fn render_in_partitions(
    config: CausalNormaliserConfig,
    sample_rate: u32,
    left: &[f64],
    right: &[f64],
    partitions: &[usize],
) -> (Vec<f64>, Vec<f64>) {
    let mut normaliser = CausalNormaliser::new(sample_rate, config).unwrap();
    let mut out_left = Vec::new();
    let mut out_right = Vec::new();
    let mut offset = 0;
    for &partition_len in partitions {
        let end = (offset + partition_len).min(left.len());
        let (block_left, block_right) = normaliser
            .process(&left[offset..end], &right[offset..end])
            .unwrap();
        out_left.extend(block_left);
        out_right.extend(block_right);
        offset = end;
        if offset == left.len() {
            break;
        }
    }
    if offset < left.len() {
        let (block_left, block_right) = normaliser
            .process(&left[offset..], &right[offset..])
            .unwrap();
        out_left.extend(block_left);
        out_right.extend(block_right);
    }
    let (tail_left, tail_right) = normaliser.flush();
    out_left.extend(tail_left);
    out_right.extend(tail_right);
    (out_left, out_right)
}

#[test]
fn causal_normaliser_has_a_versioned_fixed_latency_contract() {
    let normaliser = CausalNormaliser::new(1_000, CausalNormaliserConfig::default()).unwrap();

    assert_eq!(
        normaliser.contract_version(),
        CAUSAL_NORMALISER_CONTRACT_VERSION
    );
    assert_eq!(normaliser.latency_frames(), 5);
    assert!(normaliser.is_idle());
}

#[test]
fn causal_normaliser_is_exactly_partition_invariant_after_finite_flush() {
    let config = CausalNormaliserConfig {
        target: 0.8,
        lookahead_seconds: 0.003,
        attack_seconds: 0.002,
        release_seconds: 0.030,
    };
    let left: Vec<f64> = (0..97)
        .map(|index| ((index as f64 * 0.37).sin() * 0.9) + if index == 52 { 0.8 } else { 0.0 })
        .collect();
    let right: Vec<f64> = (0..97)
        .map(|index| ((index as f64 * 0.23).cos() * 0.6) - if index == 17 { 0.5 } else { 0.0 })
        .collect();

    let whole = render_in_partitions(config, 1_000, &left, &right, &[left.len()]);
    let partitioned = render_in_partitions(config, 1_000, &left, &right, &[1, 7, 3, 19, 2, 31, 5]);

    assert_eq!(whole, partitioned);
    assert_eq!(whole.0.len(), left.len());
    assert_eq!(whole.1.len(), right.len());
}

#[test]
fn causal_normaliser_only_uses_its_bounded_lookahead_window() {
    let config = CausalNormaliserConfig {
        target: 0.5,
        lookahead_seconds: 0.002,
        attack_seconds: 0.0,
        release_seconds: 0.0,
    };
    let mut left_a = vec![0.25; 16];
    let mut left_b = left_a.clone();
    left_a.extend([0.0; 8]);
    left_b.extend([4.0; 8]);
    let right = vec![0.0; left_a.len()];

    let output_a = render_in_partitions(config, 1_000, &left_a, &right, &[left_a.len()]);
    let output_b = render_in_partitions(config, 1_000, &left_b, &right, &[left_b.len()]);

    assert_eq!(&output_a.0[..14], &output_b.0[..14]);
    assert_ne!(output_a.0[15], output_b.0[15]);
}

#[test]
fn causal_normaliser_links_channels_and_flushes_delayed_frames() {
    let config = CausalNormaliserConfig {
        target: 0.5,
        lookahead_seconds: 0.001,
        attack_seconds: 0.0,
        release_seconds: 0.0,
    };
    let mut normaliser = CausalNormaliser::new(1_000, config).unwrap();
    let (body_left, body_right) = normaliser.process(&[0.25, 0.0], &[1.0, 0.0]).unwrap();
    let (tail_left, tail_right) = normaliser.flush();

    assert_eq!(body_left, vec![0.125]);
    assert_eq!(body_right, vec![0.5]);
    assert_eq!(tail_left, vec![0.0]);
    assert_eq!(tail_right, vec![0.0]);
    assert!(normaliser.is_idle());
}

#[test]
fn causal_normaliser_reuses_caller_owned_block_buffers() {
    let mut normaliser = CausalNormaliser::new(1_000, CausalNormaliserConfig::default()).unwrap();
    let mut out_left = Vec::with_capacity(16);
    let mut out_right = Vec::with_capacity(16);

    normaliser
        .process_into(&[0.2; 8], &[0.1; 8], &mut out_left, &mut out_right)
        .unwrap();
    let left_capacity = out_left.capacity();
    let right_capacity = out_right.capacity();
    normaliser.flush_into(&mut out_left, &mut out_right);
    normaliser.reset();
    normaliser
        .process_into(&[0.2; 8], &[0.1; 8], &mut out_left, &mut out_right)
        .unwrap();

    assert!(out_left.capacity() >= left_capacity);
    assert!(out_right.capacity() >= right_capacity);
}

#[test]
fn causal_normaliser_rejects_invalid_config_and_planar_shape() {
    assert!(CausalNormaliser::new(
        44_100,
        CausalNormaliserConfig {
            target: 0.0,
            ..CausalNormaliserConfig::default()
        }
    )
    .is_err());

    let mut normaliser = CausalNormaliser::new(44_100, CausalNormaliserConfig::default()).unwrap();
    assert!(normaliser.process(&[0.0], &[]).is_err());
}
