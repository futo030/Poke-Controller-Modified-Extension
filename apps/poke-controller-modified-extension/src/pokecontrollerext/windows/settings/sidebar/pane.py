import logging
import tkinter as tk
from typing import Any, Callable

from pokecontrollerext.singletons.app.settings import get_app_settings
from pokecontrollerext.widgets.frame import Frame

logger = logging.getLogger(__name__)


class SettingsSidebarPane(Frame):
    _frame: Frame
    _current_button: tk.Button | None
    _section_buttons: dict[str, tk.Button]

    def __init__(
        self,
        master: tk.Misc,
        on_section_selected: Callable[[str, str], None],
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(master, *args, **kwargs)
        self._on_section_selected = on_section_selected

        self._settings = get_app_settings()

        self.build_ui()

    def build_ui(self) -> None:
        self._current_button: tk.Button | None = None
        self._section_buttons: dict[str, tk.Button] = {}

    def add_section(self, section_id: str, section_name: str) -> None:
        btn = tk.Button(
            self,
            text=section_name,
            relief=tk.FLAT,
            anchor=tk.W,
            padx=4,
            pady=4,
            command=lambda: self._on_section_pressed(section_id, section_name),
        )
        btn.pack(fill=tk.X, padx=5, pady=1)
        self._section_buttons[section_id] = btn

    def select_section(self, section_id: str, section_name: str) -> None:
        if self._current_button is not None:
            self._current_button.configure(fg="black", state=tk.NORMAL)
        self._current_button = self._section_buttons[section_id]
        self._current_button.configure(fg="#6e6e6e", state=tk.DISABLED)

        self._on_section_selected(section_id, section_name)

    def _on_section_pressed(self, section_id: str, section_name: str) -> None:
        self.select_section(section_id, section_name)
