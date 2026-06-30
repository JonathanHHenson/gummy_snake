use std::time::{Duration, Instant};

#[derive(Debug, Clone, PartialEq)]
pub struct BenchmarkSample {
    pub name: String,
    pub iterations: u64,
    pub elapsed: Duration,
}

impl BenchmarkSample {
    pub fn per_second(&self) -> f64 {
        self.iterations as f64 / self.elapsed.as_secs_f64().max(1e-9)
    }
}

pub fn time_iterations(
    name: impl Into<String>,
    iterations: u64,
    mut f: impl FnMut(),
) -> BenchmarkSample {
    let start = Instant::now();
    for _ in 0..iterations {
        f();
    }
    BenchmarkSample {
        name: name.into(),
        iterations,
        elapsed: start.elapsed(),
    }
}
