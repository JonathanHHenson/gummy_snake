# pyright: reportUnboundVariable=false
# pyright: reportUnsupportedDunderAll=false
# pyright: reportUndefinedVariable=false, reportPossiblyUnboundVariable=false
# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
# pyright: reportAssignmentType=false, reportCallIssue=false
# pyright: reportGeneralTypeIssues=false, reportIndexIssue=false
# pyright: reportInvalidTypeForm=false, reportOperatorIssue=false
# pyright: reportOptionalMemberAccess=false, reportOptionalSubscript=false
# pyright: reportRedeclaration=false, reportReturnType=false
class Sound:
    """Loaded sound asset with simple playback controls.

    Loading is backend-neutral and does not require an audio device. Playback is
    delegated to a small platform player when one is available; otherwise
    ``play()`` raises ``BackendCapabilityError`` while metadata and controls
    remain usable for sketches and tests.
    """

    def __init__(
        self,
        source: object,
        *,
        path: Path,
        rust_sound: CanvasSound | None = None,
        player_factory: Any | None = None,
    ) -> None:
        """Create a playable sound wrapper around asset bytes or a generated source."""
        self._source = source
        self._rust_sound = rust_sound
        self._path = path
        self._player_factory = player_factory or _NativeAudioPlayer
        self._player: Any | None = None
        self._temporary_playback_path: Path | None = None
        self._volume = 1.0
        self._rate = 1.0
        self._pan = 0.0
        self._loop = False
        self._position = 0.0
        self._is_playing = False
        self._ended_callbacks: list[Callable[[Sound], object]] = []

    @property
    def path(self) -> Path:
        """Path used to create this sound."""

        return self._path

    @property
    def duration(self) -> float | None:
        """Sound duration in seconds, if known."""

        if self._rust_sound is not None:
            return self._rust_sound.duration
        duration = getattr(self._source, "duration", None)
        return None if duration is None else float(duration)

    @property
    def byte_len(self) -> int | None:
        """Number of encoded audio bytes, if bytes are available."""

        if self._rust_sound is None:
            return None
        return self._rust_sound.byte_len

    def to_bytes(self) -> bytes:
        """Return the encoded sound bytes.

        Returns:
            Audio file bytes for this sound.
        """

        if self._rust_sound is not None:
            return self._rust_sound.to_bytes()
        to_bytes = getattr(self._source, "to_bytes", None)
        if callable(to_bytes):
            return bytes(cast(_ByteSourceCallback, to_bytes)())
        raise BackendCapabilityError("Sound bytes are unavailable for this sound source.")

    def play(self) -> None:
        """Start playback from the current sound source."""

        self.stop()
        player = self._create_player()
        self._queue_source(player)
        self._apply_controls(player)
        try:
            player.play()
        except BackendCapabilityError:
            self._dispose_player(player)
            raise
        except Exception as exc:  # pragma: no cover - backend-specific failure path
            self._dispose_player(player)
            raise BackendCapabilityError(
                f"Audio playback is unavailable on this system. Could not play {self._path!s}."
            ) from exc
        self._player = player
        self._is_playing = True

    def loop(self) -> None:
        """Enable looping and start playback."""

        self.looping(True)
        self.play()

    def no_loop(self) -> None:
        """Disable looping for future playback."""

        self.looping(False)

    def looping(self, value: bool | None = None) -> bool:
        """Get or set whether the sound repeats when it reaches the end.

        Args:
            value: Optional new looping flag.

        Returns:
            The current looping flag.
        """

        if value is not None:
            self._loop = bool(value)
            if self._player is not None and hasattr(self._player, "loop"):
                self._player.loop = self._loop
        return self._loop

    def pause(self) -> None:
        """Pause playback if a player is active."""

        if self._player is None:
            return
        pause = getattr(self._player, "pause", None)
        if callable(pause):
            pause()
        self._is_playing = False

    def stop(self) -> None:
        """Stop playback, seek back to the start, and release the player."""

        player = self._player
        if player is None:
            return
        pause = getattr(player, "pause", None)
        if callable(pause):
            pause()
        seek = getattr(player, "seek", None)
        if callable(seek):
            seek(0.0)
        self._position = 0.0
        self._is_playing = False
        self._dispose_player(player)
        self._player = None

    def close(self) -> None:
        """Stop playback and release any temporary playback resources."""

        self.stop()

    def volume(self, value: float | None = None) -> float:
        """Get or set playback volume.

        Args:
            value: Optional non-negative volume value, where ``1.0`` is normal volume.

        Returns:
            The current volume value.
        """

        if value is not None:
            if value < 0:
                raise ArgumentValidationError("Sound.volume() cannot be negative.")
            self._volume = float(value)
            if self._player is not None:
                self._player.volume = self._volume
        return self._volume

    def rate(self, value: float | None = None) -> float:
        """Get or set playback speed.

        Args:
            value: Optional positive speed multiplier, where ``1.0`` is normal speed.

        Returns:
            The current speed multiplier.
        """

        if value is not None:
            if value <= 0:
                raise ArgumentValidationError("Sound.rate() must be positive.")
            self._rate = float(value)
            if self._player is not None:
                self._player.pitch = self._rate
        return self._rate

    def pan(self, value: float | None = None) -> float:
        """Get or set stereo pan.

        Args:
            value: Optional pan value from ``-1.0`` for left to ``1.0`` for right.

        Returns:
            The current pan value.
        """

        if value is not None:
            if not -1.0 <= value <= 1.0:
                raise ArgumentValidationError("Sound.pan() must be between -1 and 1.")
            self._pan = float(value)
            if self._player is not None:
                self._player.position = (self._pan, 0.0, 0.0)
        return self._pan

    def seek(self, seconds: float) -> None:
        """Move playback to a time in the sound.

        Args:
            seconds: Non-negative time position in seconds.
        """

        if seconds < 0:
            raise ArgumentValidationError("Sound.seek() cannot be negative.")
        self._position = float(seconds)
        if self._player is not None:
            seek = getattr(self._player, "seek", None)
            if callable(seek):
                seek(self._position)

    def time(self) -> float:
        """Return the current playback position in seconds."""

        if self._player is not None:
            time = getattr(self._player, "time", None)
            if callable(time):
                return float(cast(Any, time)())
            get_time = getattr(self._player, "get_time", None)
            if callable(get_time):
                return float(cast(Any, get_time)())
        return self._position

    def is_playing(self) -> bool:
        """Return whether this sound is currently playing."""

        return self._is_playing

    def is_paused(self) -> bool:
        """Return whether this sound has an active player that is paused."""

        return self._player is not None and not self._is_playing

    def on_ended(self, callback: Callable[[Sound], object]) -> Callable[[Sound], object]:
        """Register a callback to run when playback ends.

        Args:
            callback: Function that accepts this ``Sound`` instance.

        Returns:
            The same callback, so the method can be used like a decorator.
        """

        if not callable(callback):
            raise ArgumentValidationError("Sound.on_ended() requires a callable.")
        self._ended_callbacks.append(callback)
        return callback

    def _notify_ended(self) -> None:
        self._is_playing = False
        for callback in tuple(self._ended_callbacks):
            callback(self)

    def _create_player(self) -> Any:
        playback_path = self._materialize_playback_path()
        try:
            return self._player_factory(playback_path)
        except Exception as exc:  # pragma: no cover - backend-specific failure path
            self._remove_temporary_playback_file()
            raise BackendCapabilityError(
                "Audio playback is unavailable on this system. Could not create a sound player."
            ) from exc

    def _materialize_playback_path(self) -> Path:
        if self._rust_sound is not None:
            return self._path
        to_bytes = getattr(self._source, "to_bytes", None)
        if not callable(to_bytes):
            return self._path
        suffix = self._path.suffix or ".wav"
        with tempfile.NamedTemporaryFile(
            prefix="gummysnake-sound-", suffix=suffix, delete=False
        ) as file:
            file.write(bytes(cast(_ByteSourceCallback, to_bytes)()))
            temporary_path = Path(file.name)
        self._temporary_playback_path = temporary_path
        return temporary_path

    def _queue_source(self, player: Any) -> None:
        queue = getattr(player, "queue", None)
        if callable(queue):
            queue(self._source)

    def _apply_controls(self, player: Any) -> None:
        if hasattr(player, "volume"):
            player.volume = self._volume
        if hasattr(player, "pitch"):
            player.pitch = self._rate
        if hasattr(player, "position"):
            player.position = (self._pan, 0.0, 0.0)
        if hasattr(player, "loop"):
            player.loop = self._loop

    def _dispose_player(self, player: Any) -> None:
        delete = getattr(player, "delete", None)
        if callable(delete):
            delete()
        self._remove_temporary_playback_file()

    def _remove_temporary_playback_file(self) -> None:
        temporary_path = self._temporary_playback_path
        self._temporary_playback_path = None
        if temporary_path is None:
            return
        with suppress(OSError):
            temporary_path.unlink(missing_ok=True)
