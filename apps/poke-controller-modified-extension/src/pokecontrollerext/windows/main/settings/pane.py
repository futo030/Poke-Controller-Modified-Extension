import tkinter as tk
import tkinter.ttk as ttk
from typing import Any

from pokecontrollerext.widgets.frame import Frame
from pokecontrollerext.windows.main.settings.capture import (
    CameraSettings,
)
from pokecontrollerext.windows.main.settings.commands import (
    CommandsSettings,
)
from pokecontrollerext.windows.main.settings.manual_control import (
    ManualControlSettings,
)
from pokecontrollerext.windows.main.settings.notification import (
    NotificationSettings,
)
from pokecontrollerext.windows.main.settings.others import (
    OthersSettings,
)
from pokecontrollerext.windows.main.settings.serial import (
    SerialSettings,
)

CAPTURE = "capture"
SERIAL = "serial"
MANUAL_CONTROL = "manual_control"
COMMANDS = "commands"
NOTIFICATION = "notification"
OTHERS = "others"

SETTINGS: list[tuple[str, type[Frame], str]] = [
    (CAPTURE, CameraSettings, "Capture"),
    (SERIAL, SerialSettings, "Serial"),
    (MANUAL_CONTROL, ManualControlSettings, "Manual Control"),
    (COMMANDS, CommandsSettings, "Commands"),
    (NOTIFICATION, NotificationSettings, "Notification"),
    (OTHERS, OthersSettings, "Others"),
]


class SettingsPane(Frame):
    def __init__(self, master: tk.Misc, *args: Any, **kwargs: Any) -> None:
        super().__init__(master, *args, **kwargs)
        self.build_ui()

    def build_ui(self) -> None:
        # Create Notebook
        notebook = ttk.Notebook(self)

        # Create Notebook Children
        settings: dict[str, Frame] = {}
        for name, settings_class, tag_text in SETTINGS:
            settings[name] = settings_class(notebook)
            notebook.add(settings[name], text=tag_text, padding=5, sticky=tk.NSEW)

        # Layout
        notebook.pack(expand=True, fill=tk.BOTH, padx=0)
