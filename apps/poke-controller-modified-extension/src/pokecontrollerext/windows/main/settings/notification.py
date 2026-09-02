import tkinter as tk
from typing import Any, Callable

from pokecontrollerext.app.translation import t
from pokecontrollerext.singletons.app.model import get_app_model
from pokecontrollerext.singletons.app.settings import get_app_settings
from pokecontrollerext.widgets.button import Button
from pokecontrollerext.widgets.checkbutton import Checkbutton
from pokecontrollerext.widgets.frame import Frame
from pokecontrollerext.widgets.labelframe import Labelframe


class NotificationSettings(Frame):
    def __init__(self, master: tk.Misc, *args: Any, **kwargs: Any) -> None:
        super().__init__(master, *args, **kwargs)

        self._app_settings = get_app_settings()
        self._app_model = get_app_model()

        self._enabled_windows_started = (
            self._app_settings.notification.line.enabled_started
        )
        self._enabled_windows_ended = self._app_settings.notification.line.enabled_ended
        self._enabled_discord_started = (
            self._app_settings.notification.discord.enabled_started
        )
        self._enabled_discord_ended = (
            self._app_settings.notification.discord.enabled_ended
        )

        self.build_ui()

    def build_ui(self) -> None:
        desktop_notification = self._build_desktop_notification()
        discord_notification = self._build_discord_notification()

        # Layout
        desktop_notification.pack(
            expand=False,
            fill=tk.NONE,
            anchor=tk.NE,
            side=tk.LEFT,
            padx=4,
        )
        discord_notification.pack(
            expand=False,
            fill=tk.NONE,
            anchor=tk.NE,
            side=tk.LEFT,
            padx=8,
        )

    def _build_desktop_notification(self) -> Labelframe:
        return self._build_notification(
            platform="desktop",
            enabled_started=self._enabled_windows_started,
            enabled_ended=self._enabled_windows_ended,
            on_test_pressed=self._on_desktop_test_pressed,
        )

    def _build_discord_notification(self) -> Labelframe:
        return self._build_notification(
            platform="discord",
            enabled_started=self._enabled_discord_started,
            enabled_ended=self._enabled_discord_ended,
            on_test_pressed=self._on_discord_test_pressed,
        )

    def _build_notification(
        self,
        platform: str,
        enabled_started: tk.BooleanVar,
        enabled_ended: tk.BooleanVar,
        on_test_pressed: Callable[[], None],
    ) -> Labelframe:
        labelframe = Labelframe(
            self,
            text=t(f"main.settings.notification.{platform}.title"),
        )

        # Start
        enable_start_checkbutton = Checkbutton(
            labelframe,
            text=t(f"main.settings.notification.{platform}.start"),
            tooltip=t(f"main.settings.notification.{platform}.start.tooltip"),
            variable=enabled_started,
        )

        # End
        enable_end_checkbutton = Checkbutton(
            labelframe,
            text=t(f"main.settings.notification.{platform}.end"),
            tooltip=t(f"main.settings.notification.{platform}.end.tooltip"),
            variable=enabled_ended,
        )

        # Test
        test_button = Button(
            labelframe,
            text=t(f"main.settings.notification.{platform}.test"),
            tooltip=t(f"main.settings.notification.{platform}.test.tooltip"),
            command=on_test_pressed,
        )

        # Layout
        enable_start_checkbutton.pack(expand=False, fill=tk.NONE, side=tk.LEFT, padx=4)
        enable_end_checkbutton.pack(expand=False, fill=tk.NONE, side=tk.LEFT, padx=8)
        test_button.pack(expand=False, fill=tk.NONE, side=tk.LEFT, padx=4, pady=4)

        return labelframe

    def _on_desktop_test_pressed(self) -> None:
        self._app_model.notify_desktop(message="Notification Test")

    def _on_discord_test_pressed(self) -> None:
        self._app_model.notify_discord(message="Notification Test")
