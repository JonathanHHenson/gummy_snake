use super::input::{modifiers_mask, normalize_mouse_button};
use super::InteractiveRuntime;
use crate::runtime::event::RuntimeEvent;
use sdl3::event::{Event, WindowEvent};
use std::time::Instant;

pub(super) fn push_coalesced_event(events: &mut Vec<RuntimeEvent>, event: RuntimeEvent) {
    let Some(previous) = events.last_mut() else {
        events.push(event);
        return;
    };
    let compatible_pointer_state = previous.event_type == event.event_type
        && previous.button == event.button
        && previous.modifiers == event.modifiers;
    match event.event_type {
        "mouse_moved" | "mouse_dragged" if compatible_pointer_state => {
            previous.x = event.x;
            previous.y = event.y;
            previous.dx = Some(previous.dx.unwrap_or(0.0) + event.dx.unwrap_or(0.0));
            previous.dy = Some(previous.dy.unwrap_or(0.0) + event.dy.unwrap_or(0.0));
            previous.inside_window = event.inside_window;
        }
        "mouse_wheel"
            if previous.event_type == event.event_type && previous.modifiers == event.modifiers =>
        {
            previous.x = event.x;
            previous.y = event.y;
            previous.scroll_x =
                Some(previous.scroll_x.unwrap_or(0.0) + event.scroll_x.unwrap_or(0.0));
            previous.scroll_y =
                Some(previous.scroll_y.unwrap_or(0.0) + event.scroll_y.unwrap_or(0.0));
            previous.inside_window = event.inside_window;
        }
        _ => events.push(event),
    }
}

impl InteractiveRuntime {
    pub(crate) fn pump_events(&mut self) -> Result<(), String> {
        let events: Vec<Event> = self.event_pump.poll_iter().collect();
        for event in events {
            self.handle_event(event);
        }
        Ok(())
    }

    fn handle_event(&mut self, event: Event) {
        match event {
            Event::Quit { .. } => self.close(),
            Event::Window {
                window_id,
                win_event,
                ..
            } if window_id == self.window_id => self.handle_window_event(win_event),
            Event::MouseMotion {
                window_id,
                x,
                y,
                xrel,
                yrel,
                ..
            } if window_id == self.window_id => self.push_cursor_event(x, y, xrel, yrel),
            Event::MouseButtonDown {
                window_id,
                mouse_btn,
                clicks,
                x,
                y,
                ..
            } if window_id == self.window_id => {
                let (event_x, event_y) = self.push_mouse_button("mouse_pressed", mouse_btn, x, y);
                if clicks >= 2 {
                    self.events.push(RuntimeEvent::logical_mouse(
                        "mouse_double_clicked",
                        event_x,
                        event_y,
                        0.0,
                        0.0,
                        normalize_mouse_button(mouse_btn),
                        modifiers_mask(self.modifiers),
                    ));
                }
            }
            Event::MouseButtonUp {
                window_id,
                mouse_btn,
                x,
                y,
                ..
            } if window_id == self.window_id => {
                let button = normalize_mouse_button(mouse_btn);
                let (event_x, event_y) = self.push_mouse_button("mouse_released", mouse_btn, x, y);
                self.push_click_events(button, event_x, event_y);
            }
            Event::MouseWheel {
                window_id,
                x,
                y,
                direction,
                mouse_x,
                mouse_y,
                ..
            } if window_id == self.window_id => {
                self.push_mouse_wheel(x, y, direction, mouse_x, mouse_y)
            }
            Event::KeyDown {
                window_id,
                keycode,
                scancode,
                keymod,
                repeat,
                ..
            } if window_id == self.window_id => {
                self.modifiers = keymod;
                if !repeat {
                    self.push_key_event("key_pressed", keycode, scancode);
                }
            }
            Event::KeyUp {
                window_id,
                keycode,
                scancode,
                keymod,
                ..
            } if window_id == self.window_id => {
                self.modifiers = keymod;
                self.push_key_event("key_released", keycode, scancode);
            }
            Event::TextInput {
                window_id, text, ..
            } if window_id == self.window_id && self.text_input_active && !text.is_empty() => {
                self.events.push(RuntimeEvent::key_typed(text));
            }
            Event::FingerDown {
                window_id,
                finger_id,
                x,
                y,
                pressure,
                ..
            } if window_id == self.window_id => {
                self.push_touch_event("touch_started", finger_id, x, y, "started", pressure)
            }
            Event::FingerMotion {
                window_id,
                finger_id,
                x,
                y,
                pressure,
                ..
            } if window_id == self.window_id => {
                self.push_touch_event("touch_moved", finger_id, x, y, "moved", pressure)
            }
            Event::FingerUp {
                window_id,
                finger_id,
                x,
                y,
                pressure,
                ..
            } if window_id == self.window_id => {
                self.push_touch_event("touch_ended", finger_id, x, y, "ended", pressure)
            }
            _ => {}
        }
    }

    fn handle_window_event(&mut self, event: WindowEvent) {
        match event {
            WindowEvent::CloseRequested => self.close(),
            WindowEvent::Resized(_, _)
            | WindowEvent::PixelSizeChanged(_, _)
            | WindowEvent::DisplayChanged(_) => self.handle_resize(),
            WindowEvent::FocusLost => {
                self.release_pointer_lock();
                self.set_mouse_inside_window(false);
            }
            WindowEvent::MouseEnter => self.set_mouse_inside_window(true),
            WindowEvent::MouseLeave if !self.pointer_locked => {
                self.cursor_position = None;
                self.set_mouse_inside_window(false);
            }
            WindowEvent::MouseLeave => {}
            _ => {}
        }
    }

    fn handle_resize(&mut self) {
        self.refresh_window_metrics(false);
        self.last_resize_at = Some(Instant::now());
        self.events.retain(|event| event.event_type != "resized");
        self.events.push(RuntimeEvent::resized(
            self.logical_width,
            self.logical_height,
            self.pixel_density,
        ));
    }

    fn set_mouse_inside_window(&mut self, inside_window: bool) {
        self.mouse_inside_window = inside_window;
        self.events
            .push(RuntimeEvent::mouse_window_state(inside_window));
    }

    pub(super) fn drain_events(&mut self) -> Vec<RuntimeEvent> {
        std::mem::take(&mut self.events)
    }

    pub(super) fn drain_events_except_resize(&mut self) -> Vec<RuntimeEvent> {
        let mut drained = Vec::new();
        let mut retained = Vec::new();
        for event in self.events.drain(..) {
            if event.event_type == "resized" {
                retained.push(event);
            } else {
                drained.push(event);
            }
        }
        self.events = retained;
        drained
    }
}

#[cfg(test)]
mod tests {
    use super::push_coalesced_event;
    use crate::runtime::event::RuntimeEvent;

    #[test]
    fn adjacent_motion_events_keep_latest_position_and_accumulate_delta() {
        let mut events = Vec::new();
        push_coalesced_event(
            &mut events,
            RuntimeEvent::logical_mouse("mouse_moved", 2.0, 3.0, 2.0, 3.0, None, 0),
        );
        push_coalesced_event(
            &mut events,
            RuntimeEvent::logical_mouse("mouse_moved", 7.0, 8.0, 5.0, 5.0, None, 0),
        );

        assert_eq!(events.len(), 1);
        assert_eq!(events[0].x, Some(7.0));
        assert_eq!(events[0].y, Some(8.0));
        assert_eq!(events[0].dx, Some(7.0));
        assert_eq!(events[0].dy, Some(8.0));
    }

    #[test]
    fn discrete_events_are_barriers_for_motion_coalescing() {
        let mut events = Vec::new();
        push_coalesced_event(
            &mut events,
            RuntimeEvent::logical_mouse("mouse_moved", 2.0, 3.0, 2.0, 3.0, None, 0),
        );
        push_coalesced_event(
            &mut events,
            RuntimeEvent::key("key_pressed", Some("a".to_string()), None, 0),
        );
        push_coalesced_event(
            &mut events,
            RuntimeEvent::logical_mouse("mouse_moved", 7.0, 8.0, 5.0, 5.0, None, 0),
        );

        assert_eq!(
            events
                .iter()
                .map(|event| event.event_type)
                .collect::<Vec<_>>(),
            vec!["mouse_moved", "key_pressed", "mouse_moved"]
        );
    }

    #[test]
    fn adjacent_wheel_events_accumulate_scroll_at_latest_position() {
        let mut events = Vec::new();
        push_coalesced_event(
            &mut events,
            RuntimeEvent::logical_mouse_wheel(2.0, 3.0, 1.0, -2.0, 0),
        );
        push_coalesced_event(
            &mut events,
            RuntimeEvent::logical_mouse_wheel(4.0, 5.0, 3.0, 4.0, 0),
        );

        assert_eq!(events.len(), 1);
        assert_eq!(events[0].x, Some(4.0));
        assert_eq!(events[0].y, Some(5.0));
        assert_eq!(events[0].scroll_x, Some(4.0));
        assert_eq!(events[0].scroll_y, Some(2.0));
    }
}
