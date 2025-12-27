from pokecontrollerext.app.exception import AppRuntimeException
from pokecontrollerext.command.state import AppCommandState

_app_command_state: AppCommandState | None = None


def setup_app_command_state() -> AppCommandState:
    global _app_command_state
    _app_command_state = AppCommandState()
    return _app_command_state


def get_app_command_state() -> AppCommandState:
    global _app_command_state
    if _app_command_state is None:
        raise AppRuntimeException("App command state is not initialized.")
    return _app_command_state
