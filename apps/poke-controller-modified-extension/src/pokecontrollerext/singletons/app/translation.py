from pathlib import Path

from pokecontroller.utils import platform
from pokecontroller.utils.translation import Translation

from pokecontrollerext.app.exception import AppRuntimeException

_translation: Translation | None = None


def setup_translation(base_dir: Path, language: str) -> None:
    global _translation
    _translation = Translation(base_dir, platform.get_name(), language)


def get_translation() -> Translation:
    global _translation
    if _translation is None:
        raise AppRuntimeException("Translation is not initialized.")
    return _translation
