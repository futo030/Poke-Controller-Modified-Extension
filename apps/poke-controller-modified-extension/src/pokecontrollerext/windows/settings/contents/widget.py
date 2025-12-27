import logging
import tkinter as tk
from typing import Any

from pokecontrollerext.widgets.frame import Frame

logger = logging.getLogger(__name__)


class WidgetSettingsPane(Frame):
    _current_version: tk.StringVar

    def __init__(self, master: tk.Misc, *args: Any, **kwargs: Any) -> None:
        super().__init__(master, *args, **kwargs)
        self.build_ui()

    def build_ui(self) -> None:
        pass
