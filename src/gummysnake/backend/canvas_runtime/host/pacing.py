"""Frame pacing diagnostics for the Rust canvas backend."""

from __future__ import annotations


def _pacing_float(value: object) -> float:
    return float(value) if isinstance(value, int | float) else 0.0


def _pacing_int(value: object) -> int:
    return int(value) if isinstance(value, int | float) else 0


class CanvasBackendPacingMixin:
    _frame_pacing_enabled: bool
    _frame_pacing: dict[str, float | int | bool | None]
    _last_present_time: float | None

    def enable_frame_pacing_diagnostics(self, enabled: bool = True, *, reset: bool = True) -> None:
        """Enable frame pacing diagnostics.
        
        Args:
            enabled: The enabled value. Expected type: `bool`. Defaults to `True`.
            reset: The reset value. Expected type: `bool`. Defaults to `True`.
        
        Returns:
            None.
        """
        self._frame_pacing_enabled = bool(enabled)
        if reset:
            self.reset_frame_pacing_diagnostics()

    def reset_frame_pacing_diagnostics(self) -> None:
        """Reset frame pacing diagnostics.
        
        Args:
            None.
        
        Returns:
            None.
        """
        enabled = self._frame_pacing_enabled
        self._frame_pacing = {
            "enabled": enabled,
            "frames": 0,
            "event_polls": 0,
            "draw_duration_ms_total": 0.0,
            "present_duration_ms_total": 0.0,
            "event_poll_duration_ms_total": 0.0,
            "frame_interval_ms_total": 0.0,
            "max_draw_duration_ms": 0.0,
            "max_present_duration_ms": 0.0,
            "max_event_poll_duration_ms": 0.0,
            "max_frame_interval_ms": 0.0,
            "last_draw_duration_ms": None,
            "last_present_duration_ms": None,
            "last_event_poll_duration_ms": None,
            "last_frame_interval_ms": None,
        }
        self._last_present_time = None

    def frame_pacing_diagnostics(self) -> dict[str, float | int | bool | None]:
        """Frame pacing diagnostics.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `dict[str, float | int | bool | None]`.
        """
        report = dict(self._frame_pacing)
        frames = _pacing_int(report.get("frames"))
        event_polls = _pacing_int(report.get("event_polls"))
        report["mean_draw_duration_ms"] = (
            _pacing_float(report.get("draw_duration_ms_total")) / frames if frames else 0.0
        )
        report["mean_present_duration_ms"] = (
            _pacing_float(report.get("present_duration_ms_total")) / frames if frames else 0.0
        )
        report["mean_frame_interval_ms"] = (
            _pacing_float(report.get("frame_interval_ms_total")) / max(1, frames - 1)
            if frames > 1
            else 0.0
        )
        report["mean_event_poll_duration_ms"] = (
            _pacing_float(report.get("event_poll_duration_ms_total")) / event_polls
            if event_polls
            else 0.0
        )
        return report

    def _record_pacing_duration(self, kind: str, duration_ms: float) -> None:
        if not self._frame_pacing_enabled:
            return
        total_key = f"{kind}_duration_ms_total"
        max_key = f"max_{kind}_duration_ms"
        last_key = f"last_{kind}_duration_ms"
        self._frame_pacing[total_key] = _pacing_float(self._frame_pacing[total_key]) + duration_ms
        self._frame_pacing[max_key] = max(_pacing_float(self._frame_pacing[max_key]), duration_ms)
        self._frame_pacing[last_key] = duration_ms

    def _record_present_interval(self, now: float) -> None:
        if not self._frame_pacing_enabled:
            return
        self._frame_pacing["frames"] = _pacing_int(self._frame_pacing["frames"]) + 1
        if self._last_present_time is not None:
            interval_ms = (now - self._last_present_time) * 1000.0
            self._frame_pacing["frame_interval_ms_total"] = (
                _pacing_float(self._frame_pacing["frame_interval_ms_total"]) + interval_ms
            )
            self._frame_pacing["max_frame_interval_ms"] = max(
                _pacing_float(self._frame_pacing["max_frame_interval_ms"]), interval_ms
            )
            self._frame_pacing["last_frame_interval_ms"] = interval_ms
        self._last_present_time = now
