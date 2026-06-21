mod event;
pub(crate) mod style;

#[cfg(any(target_os = "macos", target_os = "linux", target_os = "windows"))]
mod app;
#[cfg(any(target_os = "macos", target_os = "linux", target_os = "windows"))]
mod desktop;
#[cfg(any(target_os = "macos", target_os = "linux", target_os = "windows"))]
mod input;

#[cfg(not(any(target_os = "macos", target_os = "linux", target_os = "windows")))]
mod stub;

pub use event::RuntimeEvent;

#[cfg(any(target_os = "macos", target_os = "linux", target_os = "windows"))]
pub use desktop::{native_window_available, InteractiveRuntime};

#[cfg(not(any(target_os = "macos", target_os = "linux", target_os = "windows")))]
pub use stub::{native_window_available, InteractiveRuntime};
