import logging
import tkinter as tk
from typing import Any

from pokecontrollerext.app.translation import t
from pokecontrollerext.singletons.app.command import get_app_command_state
from pokecontrollerext.singletons.app.model import get_app_model
from pokecontrollerext.singletons.runtime.papico import get_papico
from pokecontrollerext.singletons.runtime.resources import (
    get_app_resources,
)
from pokecontrollerext.singletons.runtime.runtime_info import (
    get_app_runtime_info,
)
from pokecontrollerext.singletons.widget.catalog import (
    get_app_widget_catalog,
)
from pokecontrollerext.widgets.button import Button
from pokecontrollerext.widgets.frame import Frame
from pokecontrollerext.windows.controller import ControllerWindow

logger = logging.getLogger(__name__)

START = "start"
CONTROLLER = "controller"
CLEAR_OUTPUTS = "clear_outputs"
CAPTURE = "capture"
OPEN_CAPTURE_DIR = "open_capture_dir"
NOTIFY_DISCORD = "notify_discord"

BUTTONS = [
    START,
    CONTROLLER,
    CLEAR_OUTPUTS,
    CAPTURE,
    OPEN_CAPTURE_DIR,
    NOTIFY_DISCORD,
]


class Buttons(Frame):
    _buttons: dict[str, Button]

    def __init__(self, master: tk.Misc, *args: Any, **kwargs: Any) -> None:
        super().__init__(master, *args, **kwargs)
        self._open_dir_button_image: tk.PhotoImage = tk.PhotoImage(
            file="./assets/icons8-OpenDir-16.png"
        )
        self._papico = get_papico()
        self._runtime_info = get_app_runtime_info()
        self._app_model = get_app_model()
        self._command_state = get_app_command_state()
        self._app_resources = get_app_resources()
        self._widget_catalog = get_app_widget_catalog()

        self.build_ui()

        self._register_traces()

    def build_ui(self) -> None:
        # Create Buttons
        self._buttons: dict[str, Button] = {
            button: Button(self, command=command, **kwargs)  # type: ignore[arg-type]
            for button, command, kwargs in [
                (
                    START,
                    self._on_start_pressed,
                    {
                        "text": t("main.capture.start"),
                        "tooltip": t("main.capture.start.tooltip"),
                    },
                ),
                (
                    CONTROLLER,
                    self._on_controller_pressed,
                    {
                        "text": t("main.capture.controller"),
                        "tooltip": t("main.capture.controller.tooltip"),
                    },
                ),
                (
                    CLEAR_OUTPUTS,
                    self._on_clear_outputs_pressed,
                    {
                        "text": t("main.capture.clear_outputs"),
                        "tooltip": t("main.capture.clear_outputs.tooltip"),
                    },
                ),
                (
                    CAPTURE,
                    self._on_capture_pressed,
                    {
                        "text": t("main.capture.capture"),
                        "tooltip": t("main.capture.capture.tooltip"),
                    },
                ),
                (
                    OPEN_CAPTURE_DIR,
                    self._on_open_dir_pressed,
                    {
                        "image": self._open_dir_button_image,
                        "tooltip": t("main.capture.open_capture_dir.tooltip"),
                        "padding": 1,
                    },
                ),
                (
                    NOTIFY_DISCORD,
                    self._on_notify_discord_pressed,
                    {
                        "text": t("main.capture.discord"),
                        "tooltip": t("main.capture.discord.tooltip"),
                    },
                ),
            ]
        }

        # Layout
        for button in BUTTONS:
            self._buttons[button].pack(
                expand=True, anchor=tk.CENTER, side=tk.LEFT, padx=4
            )

    def _on_start_pressed(self) -> None:
        selected_command_info = get_app_command_state().selected_command_info
        if selected_command_info is not None:
            self._papico.start_command(selected_command_info)

    def _on_stop_pressed(self) -> None:
        self._papico.stop_command()

    def _on_controller_pressed(self) -> None:
        self._widget_catalog.window.open_controller(self, ControllerWindow)

    def _on_clear_outputs_pressed(self) -> None:
        self._widget_catalog.outputs.clear_all()

    def _on_capture_pressed(self) -> None:
        self._app_model.save_screencapture()

    def _on_open_dir_pressed(self) -> None:
        self._app_model.open_screencapture_directory_window()

    def _on_notify_discord_pressed(self) -> None:
        self._app_model.notify_discord(image=self._app_resources.camera.frame)

    def _on_running_changed(self, *_: str) -> None:
        if self._command_state.is_running.get():
            self._buttons[START].configure(
                text=t("main.capture.stop"),
                tooltip=t("main.capture.stop.tooltip"),
                command=self._on_stop_pressed,
            )
            self.update_idletasks()

    def _on_stopped_changed(self, *_: str) -> None:
        if self._command_state.is_stopped.get():
            self._buttons[START].configure(
                text=t("main.capture.start"),
                tooltip=t("main.capture.start.tooltip"),
                command=self._on_start_pressed,
            )
            self.update_idletasks()

    def _register_traces(self) -> None:
        self.register_trace(
            "write",
            self._command_state.is_running,
            self._on_running_changed,
        )
        self.register_trace(
            "write",
            self._command_state.is_stopped,
            self._on_stopped_changed,
        )
