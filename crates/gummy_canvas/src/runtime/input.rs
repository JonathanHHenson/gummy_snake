use winit::event::{Force, MouseButton, TouchPhase};
use winit::keyboard::{Key, ModifiersState, NamedKey};

pub(super) fn touch_phase_name(phase: TouchPhase) -> &'static str {
    match phase {
        TouchPhase::Started => "started",
        TouchPhase::Moved => "moved",
        TouchPhase::Ended => "ended",
        TouchPhase::Cancelled => "cancelled",
    }
}

pub(super) fn touch_pressure(force: Force) -> f64 {
    match force {
        Force::Calibrated {
            force,
            max_possible_force,
            ..
        } => {
            if max_possible_force > 0.0 {
                (force / max_possible_force).clamp(0.0, 1.0)
            } else {
                force.max(0.0)
            }
        }
        Force::Normalized(value) => value.clamp(0.0, 1.0),
    }
}

pub(super) fn normalize_mouse_button(button: MouseButton) -> Option<String> {
    match button {
        MouseButton::Left => Some("left".to_string()),
        MouseButton::Middle => Some("center".to_string()),
        MouseButton::Right => Some("right".to_string()),
        MouseButton::Back => Some("4".to_string()),
        MouseButton::Forward => Some("5".to_string()),
        MouseButton::Other(value) => Some(value.to_string()),
    }
}

pub(super) fn normalize_key(key: &Key) -> Option<String> {
    match key {
        Key::Character(text) => Some(text.to_string()),
        Key::Named(named) => Some(named_key_name(*named).to_string()),
        _ => None,
    }
}

pub(super) fn normalize_code(key: &Key) -> Option<String> {
    match key {
        Key::Named(named) => Some(named_key_code(*named).to_string()),
        _ => None,
    }
}

fn named_key_name(named: NamedKey) -> &'static str {
    match named {
        NamedKey::Space => " ",
        NamedKey::Enter => "Enter",
        NamedKey::Tab => "Tab",
        NamedKey::Backspace => "Backspace",
        NamedKey::Escape => "Escape",
        NamedKey::Shift => "Shift",
        NamedKey::Control => "Control",
        NamedKey::Alt => "Alt",
        NamedKey::ArrowUp => "ArrowUp",
        NamedKey::ArrowDown => "ArrowDown",
        NamedKey::ArrowLeft => "ArrowLeft",
        NamedKey::ArrowRight => "ArrowRight",
        _ => "",
    }
}

fn named_key_code(named: NamedKey) -> &'static str {
    match named {
        NamedKey::Enter => "Enter",
        NamedKey::Tab => "Tab",
        NamedKey::Backspace => "Backspace",
        NamedKey::Escape => "Escape",
        NamedKey::Shift => "Shift",
        NamedKey::Control => "Control",
        NamedKey::Alt => "Alt",
        NamedKey::ArrowUp => "ArrowUp",
        NamedKey::ArrowDown => "ArrowDown",
        NamedKey::ArrowLeft => "ArrowLeft",
        NamedKey::ArrowRight => "ArrowRight",
        _ => "",
    }
}

pub(super) fn modifiers_mask(modifiers: ModifiersState) -> u32 {
    let mut value = 0_u32;
    if modifiers.shift_key() {
        value |= 1;
    }
    if modifiers.control_key() {
        value |= 2;
    }
    if modifiers.alt_key() {
        value |= 4;
    }
    if modifiers.super_key() {
        value |= 8;
    }
    value
}
