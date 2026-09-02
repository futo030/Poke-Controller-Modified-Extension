import tkinter as tk
from typing import Any, Callable

from pokecontrollerext.widgets.button import Button
from pokecontrollerext.widgets.frame import Frame


class SettingsButtonsPane(Frame):
    _apply_button: Button
    _has_changes: tk.BooleanVar
    _on_apply_pressed: Callable[[], None]

    def __init__(
        self,
        master: tk.Misc,
        has_changes: tk.BooleanVar,
        on_ok_pressed: Callable[[], None],
        on_apply_pressed: Callable[[], None],
        on_cancel_pressed: Callable[[], None],
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(master, *args, **kwargs)
        self._has_changes = has_changes
        self._on_ok_pressed = on_ok_pressed
        self._on_apply_pressed = on_apply_pressed
        self._on_cancel_pressed = on_cancel_pressed
        self._register_hooks()
        self.build_ui()

    def build_ui(self) -> None:
        frame = Frame(self)
        ok_button = Button(frame, text="OK", command=self._on_ok_pressed)
        self._apply_button = Button(
            frame,
            text="Apply",
            state=tk.NORMAL if self._has_changes.get() else tk.DISABLED,
            command=self._on_apply_pressed,
        )
        cancel_button = Button(frame, text="Cancel", command=self._on_cancel_pressed)

        # Layout
        ok_button.pack(side=tk.RIGHT, padx=(4, 0))
        self._apply_button.pack(side=tk.RIGHT, padx=4)
        cancel_button.pack(side=tk.RIGHT, padx=4)
        frame.pack(expand=True, fill=tk.X, padx=16, pady=8)

    def _register_hooks(self) -> None:
        self._has_changes.trace_add("write", self._on_has_changes_changed)

    def _on_has_changes_changed(self, *_: Any) -> None:
        if self._has_changes.get():
            self._apply_button.configure(state=tk.NORMAL)
        else:
            self._apply_button.configure(state=tk.DISABLED)
