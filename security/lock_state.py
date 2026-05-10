import threading
from typing import Optional, Callable


class LockState:
    """
    Security lock state manager for FRIDAY.

    When locked, all microphone-triggered actions are blocked.
    Only explicitly authorized text commands (via UI or Telegram bypass) can execute.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._locked = False
        self._muted = False
        self._on_lock_changed: Optional[Callable[[bool], None]] = None

    @property
    def locked(self) -> bool:
        return self._locked

    @locked.setter
    def locked(self, value: bool):
        with self._lock:
            changed = value != self._locked
            self._locked = value
        if changed and self._on_lock_changed:
            self._on_lock_changed(value)

    @property
    def muted(self) -> bool:
        return self._muted

    @muted.setter
    def muted(self, value: bool):
        self._muted = value

    def set_on_lock_changed(self, callback: Optional[Callable[[bool], None]]):
        self._on_lock_changed = callback

    def is_action_allowed(self, source: str = "mic") -> bool:
        """
        Check if an action is allowed given current lock state.

        Args:
            source: "mic" for voice-triggered, "text" for UI/Telegram input

        Returns:
            True if the action is allowed, False if blocked
        """
        if not self._locked:
            return True
        # When locked, only non-mic sources can execute actions
        return source != "mic"

    def check_and_log(self, source: str = "mic") -> tuple[bool, str]:
        """Check if action is allowed and return reason string."""
        if self._locked and source == "mic":
            return False, "Security lock active: microphone-triggered actions are blocked"
        return True, ""


_state: Optional[LockState] = None
_state_lock = threading.Lock()


def get_lock_state() -> LockState:
    global _state
    if _state is None:
        with _state_lock:
            if _state is None:
                _state = LockState()
    return _state
