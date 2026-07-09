# pyright: reportUnboundVariable=false
# pyright: reportUnsupportedDunderAll=false
# pyright: reportUndefinedVariable=false, reportPossiblyUnboundVariable=false
# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
# pyright: reportAssignmentType=false, reportCallIssue=false
# pyright: reportGeneralTypeIssues=false, reportIndexIssue=false
# pyright: reportInvalidTypeForm=false, reportOperatorIssue=false
# pyright: reportOptionalMemberAccess=false, reportOptionalSubscript=false
# pyright: reportRedeclaration=false, reportReturnType=false
def load_sound(path: str | Path) -> Sound:
    """Load a sound file for playback and byte access.

    Args:
        path: File path or package-relative asset path to an existing sound.

    Returns:
        A Sound object with playback controls and metadata.
    """
    sound_path = resolve_asset_path(path)
    if not sound_path.exists():
        raise ArgumentValidationError(f"Sound file does not exist: {sound_path!s}.")
    try:
        rust_sound = CanvasSound.from_file(sound_path)
    except BackendCapabilityError:
        raise
    except Exception as exc:
        raise ArgumentValidationError(f"Could not load sound {sound_path!s}.") from exc
    return Sound(rust_sound, path=sound_path, rust_sound=rust_sound)


async def load_sound_async(path: str | Path) -> Sound:
    """Load a sound file using the async asset-loading API.

    Args:
        path: File path or package-relative asset path to an existing sound.

    Returns:
        A Sound object with playback controls and metadata.
    """
    return load_sound(path)


class _NativeAudioPlayer:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._process: subprocess.Popen[bytes] | None = None
        self.volume = 1.0
        self.pitch = 1.0
        self.position = (0.0, 0.0, 0.0)

    def play(self) -> None:
        command = _platform_play_command(self._path)
        if command is None:
            raise BackendCapabilityError(
                "Audio playback requires an available platform player such as afplay, paplay, "
                "aplay, or ffplay."
            )
        self._process = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        _register_native_audio_player(self)

    def pause(self) -> None:
        if self._process is None:
            return
        if hasattr(signal, "SIGSTOP"):
            self._process.send_signal(signal.SIGSTOP)
        else:  # pragma: no cover - Windows-specific fallback
            self.delete()

    def seek(self, value: float) -> None:
        if value == 0:
            self.delete()

    def delete(self) -> None:
        process = self._process
        self._process = None
        _unregister_native_audio_player(self)
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=1.0)
        except subprocess.TimeoutExpired:  # pragma: no cover - process-specific failure path
            process.kill()
            with suppress(Exception):
                process.wait(timeout=1.0)


def _register_native_audio_player(player: _NativeAudioPlayer) -> None:
    global _NATIVE_PLAYER_MONITOR_STARTED
    should_start_monitor = False
    with _ACTIVE_NATIVE_PLAYERS_LOCK:
        _ACTIVE_NATIVE_PLAYERS.add(player)
        if not _NATIVE_PLAYER_MONITOR_STARTED:
            _NATIVE_PLAYER_MONITOR_STARTED = True
            should_start_monitor = True
    if should_start_monitor:
        threading.Thread(
            target=_stop_native_audio_when_main_thread_exits,
            name="gummysnake-audio-cleanup",
            daemon=True,
        ).start()


def _unregister_native_audio_player(player: _NativeAudioPlayer) -> None:
    with _ACTIVE_NATIVE_PLAYERS_LOCK:
        _ACTIVE_NATIVE_PLAYERS.discard(player)


def _stop_native_audio_when_main_thread_exits() -> None:
    main_thread = threading.main_thread()
    if threading.current_thread() is main_thread:  # pragma: no cover - defensive guard
        return
    with suppress(RuntimeError):
        main_thread.join()
    _stop_active_native_audio_players()


def _stop_active_native_audio_players() -> None:
    with _ACTIVE_NATIVE_PLAYERS_LOCK:
        players = list(_ACTIVE_NATIVE_PLAYERS)
    for player in players:
        with suppress(Exception):
            player.delete()


atexit.register(_stop_active_native_audio_players)


def _platform_play_command(path: Path) -> list[str] | None:
    if player := shutil.which("afplay"):
        return [player, str(path)]
    if player := shutil.which("paplay"):
        return [player, str(path)]
    if player := shutil.which("aplay"):
        return [player, str(path)]
    if player := shutil.which("ffplay"):
        return [player, "-nodisp", "-autoexit", "-loglevel", "quiet", str(path)]
    return None


__all__ = ["CanvasSound", "Sound", "load_sound", "load_sound_async"]
