import logging
import tkinter as tk
from typing import Any

from pokecontrollerext.singletons.app.settings import get_app_settings
from pokecontrollerext.singletons.app.style import get_style_manager
from pokecontrollerext.singletons.runtime.app_info import get_app_info
from pokecontrollerext.widgets.components import ComponentBuilder
from pokecontrollerext.widgets.frame import Frame

logger = logging.getLogger(__name__)


class GeneralSettingsPane(Frame):
    _current_version: tk.StringVar

    def __init__(self, master: tk.Misc, *args: Any, **kwargs: Any) -> None:
        super().__init__(master, *args, **kwargs)

        self._app_info = get_app_info()
        self._app_settings = get_app_settings()
        self._current_version = self._app_settings.general.version
        self._latest_settings_version = self._app_info.latest_settings_version

        self._style_manager = get_style_manager()
        self._theme = self._app_settings.general.theme
        self._language = self._app_settings.general.language

        self.build_ui()

    def build_ui(self) -> None:
        label_width = 8
        frame = (
            ComponentBuilder(self)
            .add_frame_row()
            .add_label(text="Version:", width=label_width)
            .add_label(variable=self._current_version)
            .end()
            .add_frame_row()
            .add_label(text="Theme:", width=label_width)
            .add_combobox(self._theme, values=list(self._style_manager.get_themes()))
            .end()
            .add_frame_row()
            .add_label(text="Language:", width=label_width)
            .add_combobox(self._language, values=["ja", "en"])
            .end()
            .build()
        )
        frame.pack(fill=tk.BOTH, anchor=tk.CENTER)
