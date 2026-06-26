use std::time::Duration;

const LIVE_RESIZE_PRESENT_COOLDOWN: Duration = Duration::from_millis(80);

mod capabilities;
mod construction;
mod frames;
mod window;
