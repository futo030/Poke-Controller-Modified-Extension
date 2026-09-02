import tkinter as tk

from pokecontrollerext.app.exception import AppRuntimeException
from pokecontrollerext.app.style import StyleManager

_style_manager: StyleManager | None = None


def setup_style_manager(root: tk.Tk) -> StyleManager:
    global _style_manager
    _style_manager = StyleManager(root)
    return _style_manager


def get_style_manager() -> StyleManager:
    global _style_manager
    if _style_manager is None:
        raise AppRuntimeException("Style manager is not initialized.")
    return _style_manager
