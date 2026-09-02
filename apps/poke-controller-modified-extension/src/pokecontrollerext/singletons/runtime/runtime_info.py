from pathlib import Path

from pokecontrollerext.app.exception import AppRuntimeException
from pokecontrollerext.app.runtime_info import AppRuntimeInfo

_runtime_info: AppRuntimeInfo | None = None


def get_app_runtime_info() -> AppRuntimeInfo:
    global _runtime_info
    if _runtime_info is None:
        raise AppRuntimeException("App runtime info is not initialized.")
    return _runtime_info


def setup_runtime_info(base_dir: Path, profile: str) -> AppRuntimeInfo:
    global _runtime_info
    _runtime_info = AppRuntimeInfo(
        base_dir=base_dir,
        profile=profile,
    )
    return _runtime_info
