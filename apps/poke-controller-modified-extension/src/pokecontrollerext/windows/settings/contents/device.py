import logging
import tkinter as tk
from dataclasses import fields
from typing import Any

from pokecontrollerext.singletons.app.settings import get_app_settings
from pokecontrollerext.widgets.components import ComponentBuilder
from pokecontrollerext.widgets.frame import Frame
from pokecontrollerext.widgets.labelframe import Labelframe
from pokecontrollerext.widgets.scrollable_frame import ScrollableFrame

logger = logging.getLogger(__name__)


class DeviceSettingsPane(Frame):
    _frame: Frame | Labelframe | ScrollableFrame

    def __init__(self, master: tk.Misc, *args: Any, **kwargs: Any) -> None:
        super().__init__(master, *args, **kwargs)

        self._settings = get_app_settings()

        self._touchscreen = self._settings.device.touchscreen
        self._keyboard = self._settings.device.keyboard
        self._mouse = self._settings.device.mouse
        self._pro_controller = self._settings.device.pro_controller

        self.build_ui()

    def build_ui(self) -> None:
        builder: Any = (
            ComponentBuilder(self)
            .add_scrollable_frame_row()
            # touchscreen
            .add_labelframe_row("Touchscreen")
            .add_frame_row()
            .add_label(text="Start:", width=8)
            .add_label(text="x")
            .add_spinbox(variable=self._touchscreen.sx, from_=1, to=320)
            .add_label(text="y")
            .add_spinbox(variable=self._touchscreen.sy, from_=1, to=240)
            .end()
            .add_frame_row()
            .add_label(text="End:", width=8)
            .add_label(text="x")
            .add_spinbox(variable=self._touchscreen.ex, from_=1, to=320)
            .add_label(text="y")
            .add_spinbox(variable=self._touchscreen.ey, from_=1, to=240)
            .end()
            .end()
            # keymap
            .add_labelframe_row("Keymap")
            .add_frame_row()
            .add_label(text="Enabled:", width=8)
            .add_checkbutton(self._keyboard.enabled, "")
            .end()
        )

        keymaps: list[tuple[str, Any]] = [
            ("Button", self._keyboard.keymap.button),
            ("Direction", self._keyboard.keymap.direction),
            ("D-pad", self._keyboard.keymap.dpad),
        ]
        for name, keymap in keymaps:
            builder = builder.add_labelframe_row(name)
            for field in fields(keymap):
                var = getattr(keymap, field.name)
                builder = (
                    builder.add_frame_row()
                    .add_label(text=field.name.upper(), width=12)
                    .add_entry(variable=var)
                    .end()
                )
            builder = builder.end()

        # mouse
        builder = (
            builder.add_labelframe_row("Mouse")
            .add_checkbutton(self._mouse.enabled_lclick, "left click")
            .add_checkbutton(self._mouse.enabled_rclick, "right click")
            .end()
        )
        # Pro Controller
        builder = (
            builder.add_labelframe_row("Pro-Controller")
            .add_checkbutton(self._pro_controller.enabled, "enabled")
            .add_checkbutton(self._pro_controller.enabled_record, "record")
            .end()
        )

        self._frame = builder.end().end().build()
        self._frame.pack(expand=True, fill=tk.BOTH, anchor=tk.CENTER)

    def refresh(self) -> None:
        if isinstance((frame := self._frame), ScrollableFrame):
            frame.refresh()
        super().refresh()
