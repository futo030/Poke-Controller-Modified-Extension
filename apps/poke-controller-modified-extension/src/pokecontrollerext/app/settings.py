import logging
from dataclasses import dataclass, fields, is_dataclass
from tkinter import BooleanVar, DoubleVar, IntVar, StringVar, Variable
from typing import Any, Self

from pokecontrollerext.app.exception import AppSettingsException

logger = logging.getLogger(__name__)

SCHEMA: dict[str, Any] = {
    "general": {
        "version": str,
        "theme": str,
        "language": str,
    },
    "capture": {
        "camera_id": int,
        "camera_name": str,
        "fps": int,
        "size": str,
        "show_realtime": bool,
        "show_matched": bool,
        "show_guide": bool,
    },
    "serial": {
        "port": str,
        "port_name": str,
        "baud_rate": int,
        "data_format": str,
        "show_data": bool,
    },
    "device": {
        "touchscreen": {
            "sx": int,
            "sy": int,
            "ex": int,
            "ey": int,
        },
        "keyboard": {
            "enabled": bool,
            "keymap": {
                "button": {
                    "y": str,
                    "b": str,
                    "x": str,
                    "a": str,
                    "l": str,
                    "r": str,
                    "zl": str,
                    "zr": str,
                    "minus": str,
                    "plus": str,
                    "lclick": str,
                    "rclick": str,
                    "home": str,
                    "capture": str,
                },
                "direction": {
                    "up": str,
                    "right": str,
                    "down": str,
                    "left": str,
                    "up_right": str,
                    "down_right": str,
                    "down_left": str,
                    "up_left": str,
                },
                "dpad": {
                    "up": str,
                    "up_right": str,
                    "right": str,
                    "down_right": str,
                    "down": str,
                    "down_left": str,
                    "left": str,
                    "up_left": str,
                    "neutral": str,
                },
            },
        },
        "mouse": {
            "enabled_lclick": bool,
            "enabled_rclick": bool,
        },
        "pro_controller": {
            "enabled": bool,
            "enabled_record": bool,
        },
    },
    "command": {
        "shortcut": {
            "registered_commands": {
                "1": {
                    "klass": str,
                    "name": str,
                },
                "2": {
                    "klass": str,
                    "name": str,
                },
                "3": {
                    "klass": str,
                    "name": str,
                },
                "4": {
                    "klass": str,
                    "name": str,
                },
                "5": {
                    "klass": str,
                    "name": str,
                },
                "6": {
                    "klass": str,
                    "name": str,
                },
                "7": {
                    "klass": str,
                    "name": str,
                },
                "8": {
                    "klass": str,
                    "name": str,
                },
                "9": {
                    "klass": str,
                    "name": str,
                },
                "10": {
                    "klass": str,
                    "name": str,
                },
            },
        },
    },
    "notification": {
        "windows": {
            "enabled_started": bool,
            "enabled_ended": bool,
        },
        "line": {
            "enabled_started": bool,
            "enabled_ended": bool,
        },
        "discord": {
            "enabled_started": bool,
            "enabled_ended": bool,
        },
    },
    "widget": {
        "output": {
            "size_balance": float,
            "stdout": int,
            "visible_output1": bool,
            "visible_output2": bool,
        },
        "software_controller": {
            "position": str,
            "visible": bool,
        },
        "dialog": {
            "confirm_buttons_position": str,
        },
    },
}

DEFAULT: dict[str, Any] = {
    "general": {
        "version": "0.2.0",
        "theme": "default",
        "language": "en",
    },
    "capture": {
        "camera_id": 0,
        "camera_name": "",
        "fps": 45,
        "size": "640x360",
        "show_realtime": True,
        "show_matched": False,
        "show_guide": False,
    },
    "serial": {
        "port": "",
        "port_name": "",
        "baud_rate": 9600,
        "data_format": "default",
        "show_data": False,
    },
    "device": {
        "touchscreen": {
            "sx": 1,
            "sy": 1,
            "ex": 320,
            "ey": 240,
        },
        "keyboard": {
            "enabled": True,
            "keymap": {
                "button": {
                    "y": "y",
                    "b": "b",
                    "x": "x",
                    "a": "a",
                    "l": "l",
                    "r": "r",
                    "zl": "k",
                    "zr": "e",
                    "minus": "m",
                    "plus": "p",
                    "lclick": "q",
                    "rclick": "w",
                    "home": "h",
                    "capture": "c",
                },
                "direction": {
                    "up": "up",
                    "right": "right",
                    "down": "left",
                    "left": "20001",
                    "up_right": "20002",
                    "down_right": "20010",
                    "down_left": "20010",
                    "up_left": "20011",
                },
                "dpad": {
                    "up": "10000",
                    "up_right": "10001",
                    "right": "10010",
                    "down_right": "10011",
                    "down": "10100",
                    "down_left": "10101",
                    "left": "10110",
                    "up_left": "10111",
                    "neutral": "11000",
                },
            },
        },
        "mouse": {
            "enabled_lclick": True,
            "enabled_rclick": True,
        },
        "pro_controller": {
            "enabled": False,
            "enabled_record": False,
        },
    },
    "command": {
        "shortcut": {
            "registered_commands": {
                "1": {
                    "klass": "None",
                    "name": "(empty)",
                },
                "2": {
                    "klass": "None",
                    "name": "(empty)",
                },
                "3": {
                    "klass": "None",
                    "name": "(empty)",
                },
                "4": {
                    "klass": "None",
                    "name": "(empty)",
                },
                "5": {
                    "klass": "None",
                    "name": "(empty)",
                },
                "6": {
                    "klass": "None",
                    "name": "(empty)",
                },
                "7": {
                    "klass": "None",
                    "name": "(empty)",
                },
                "8": {
                    "klass": "None",
                    "name": "(empty)",
                },
                "9": {
                    "klass": "None",
                    "name": "(empty)",
                },
                "10": {
                    "klass": "None",
                    "name": "(empty)",
                },
            },
        },
    },
    "notification": {
        "windows": {
            "enabled_started": False,
            "enabled_ended": False,
        },
        "line": {
            "enabled_started": False,
            "enabled_ended": False,
        },
        "discord": {
            "enabled_started": False,
            "enabled_ended": False,
        },
    },
    "widget": {
        "output": {
            "size_balance": 20.0,
            "stdout": 1,
            "visible_output1": True,
            "visible_output2": True,
        },
        "software_controller": {
            "position": "bottom",
            "visible": True,
        },
        "dialog": {
            "confirm_buttons_position": "bottom",
        },
    },
}


@dataclass(kw_only=True, frozen=True)
class GeneralSettings:
    version: StringVar
    theme: StringVar
    language: StringVar


@dataclass(kw_only=True, frozen=True)
class CaptureSettings:
    camera_id: IntVar
    camera_name: StringVar
    fps: IntVar
    size: StringVar
    show_realtime: BooleanVar
    show_matched: BooleanVar
    show_guide: BooleanVar


@dataclass(kw_only=True, frozen=True)
class SerialSettings:
    port: StringVar
    port_name: StringVar
    baud_rate: IntVar
    data_format: StringVar
    show_data: BooleanVar


@dataclass(kw_only=True, frozen=True)
class TouchscreenSettings:
    sx: IntVar
    sy: IntVar
    ex: IntVar
    ey: IntVar


@dataclass(kw_only=True, frozen=True)
class ButtonKeymapSettings:
    y: StringVar
    b: StringVar
    x: StringVar
    a: StringVar
    l: StringVar  # noqa: E741
    r: StringVar
    zl: StringVar
    zr: StringVar
    minus: StringVar
    plus: StringVar
    lclick: StringVar
    rclick: StringVar
    home: StringVar
    capture: StringVar


@dataclass(kw_only=True, frozen=True)
class DirectionKeymapSettings:
    up: StringVar
    right: StringVar
    down: StringVar
    left: StringVar
    up_right: StringVar
    down_right: StringVar
    down_left: StringVar
    up_left: StringVar


@dataclass(kw_only=True, frozen=True)
class DpadKeymapSettings:
    up: StringVar
    up_right: StringVar
    right: StringVar
    down_right: StringVar
    down: StringVar
    down_left: StringVar
    left: StringVar
    up_left: StringVar
    neutral: StringVar


@dataclass(kw_only=True, frozen=True)
class KeymapSettings:
    button: ButtonKeymapSettings
    direction: DirectionKeymapSettings
    dpad: DpadKeymapSettings

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Self:
        return cls(
            button=ButtonKeymapSettings(**d["button"]),
            direction=DirectionKeymapSettings(**d["direction"]),
            dpad=DpadKeymapSettings(**d["dpad"]),
        )


@dataclass(kw_only=True, frozen=True)
class KeyboardSettings:
    enabled: BooleanVar
    keymap: KeymapSettings

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Self:
        return cls(
            enabled=d["enabled"],
            keymap=KeymapSettings.from_dict(d["keymap"]),
        )


@dataclass(kw_only=True, frozen=True)
class MouseSettings:
    enabled_lclick: BooleanVar
    enabled_rclick: BooleanVar


@dataclass(kw_only=True, frozen=True)
class ProControllerSettings:
    enabled: BooleanVar
    enabled_record: BooleanVar


@dataclass(kw_only=True, frozen=True)
class DeviceSettings:
    touchscreen: TouchscreenSettings
    keyboard: KeyboardSettings
    mouse: MouseSettings
    pro_controller: ProControllerSettings

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Self:
        return cls(
            touchscreen=TouchscreenSettings(**d["touchscreen"]),
            keyboard=KeyboardSettings.from_dict(d["keyboard"]),
            mouse=MouseSettings(**d["mouse"]),
            pro_controller=ProControllerSettings(**d["pro_controller"]),
        )


@dataclass(kw_only=True, frozen=True)
class ShortcutCommandSettings:
    klass: StringVar
    name: StringVar


@dataclass(kw_only=True, frozen=True)
class ShortcutSettings:
    registered_commands: dict[str, ShortcutCommandSettings]

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Self:
        return cls(
            registered_commands={
                k: ShortcutCommandSettings(**v)
                for k, v in d["registered_commands"].items()
            },
        )


@dataclass(kw_only=True, frozen=True)
class CommandSettings:
    shortcut: ShortcutSettings

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Self:
        return cls(
            shortcut=ShortcutSettings.from_dict(d["shortcut"]),
        )


@dataclass(kw_only=True, frozen=True)
class WindowsNotificationSettings:
    enabled_started: BooleanVar
    enabled_ended: BooleanVar


@dataclass(kw_only=True, frozen=True)
class LineNotificationSettings:
    enabled_started: BooleanVar
    enabled_ended: BooleanVar


@dataclass(kw_only=True, frozen=True)
class DiscordNotificationSettings:
    enabled_started: BooleanVar
    enabled_ended: BooleanVar


@dataclass(kw_only=True, frozen=True)
class NotificationSettings:
    windows: WindowsNotificationSettings
    line: LineNotificationSettings
    discord: DiscordNotificationSettings

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Self:
        return cls(
            windows=WindowsNotificationSettings(**d["windows"]),
            line=LineNotificationSettings(**d["line"]),
            discord=DiscordNotificationSettings(**d["discord"]),
        )


@dataclass(kw_only=True, frozen=True)
class OutputSettings:
    size_balance: DoubleVar
    stdout: IntVar
    visible_output1: BooleanVar
    visible_output2: BooleanVar


@dataclass(kw_only=True, frozen=True)
class SoftwareControllerSettings:
    position: StringVar
    visible: BooleanVar


@dataclass(kw_only=True, frozen=True)
class DialogSettings:
    confirm_buttons_position: StringVar


@dataclass(kw_only=True, frozen=True)
class WidgetSettings:
    output: OutputSettings
    software_controller: SoftwareControllerSettings
    dialog: DialogSettings

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Self:
        return cls(
            output=OutputSettings(**d["output"]),
            software_controller=SoftwareControllerSettings(**d["software_controller"]),
            dialog=DialogSettings(**d["dialog"]),
        )


@dataclass(kw_only=True, frozen=True)
class PokemonHomeSettings:
    season: IntVar
    single_or_double: StringVar


@dataclass(kw_only=True, frozen=True)
class AppSettings:
    """アプリケーションの設定値を保持するクラス"""

    general: GeneralSettings
    capture: CaptureSettings
    serial: SerialSettings
    device: DeviceSettings
    command: CommandSettings
    notification: NotificationSettings
    widget: WidgetSettings

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Self:
        return cls(
            general=GeneralSettings(**d["general"]),
            capture=CaptureSettings(**d["capture"]),
            serial=SerialSettings(**d["serial"]),
            device=DeviceSettings.from_dict(d["device"]),
            command=CommandSettings.from_dict(d["command"]),
            notification=NotificationSettings.from_dict(d["notification"]),
            widget=WidgetSettings.from_dict(d["widget"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return settings_to_dict(self)

    def apply_dict(self, d: dict[str, Any]) -> None:
        def apply(current: Any, new: Any) -> None:
            if isinstance(current, Variable):
                if current.get() != new:
                    current.set(new)
                return

            if isinstance(current, dict):
                for k, v in current.items():
                    if k in new:
                        apply(v, new[k])
                return

            if not is_dataclass(current):
                raise AppSettingsException(
                    f"unsupported type: {current}({type(current)})"
                )

            for field in fields(current):
                k, v = field.name, getattr(current, field.name)
                if k in new:
                    apply(v, new[k])

        apply(self, d)

    def has_diff(self, d: dict[str, Any]) -> bool:
        def diff(current: Any, new: Any) -> bool:
            if isinstance(current, Variable):
                return current.get() != new  # type: ignore[no-any-return]

            if isinstance(current, dict):
                for k, v in current.items():
                    if k in new:
                        if diff(v, new[k]):
                            return True
                return False

            if not is_dataclass(current):
                raise AppSettingsException(
                    f"unsupported type: {current}({type(current)})"
                )

            for field in fields(current):
                k, v = field.name, getattr(current, field.name)
                if k in new:
                    if diff(v, new[k]):
                        return True
            return False

        return diff(self, d)


def settings_to_dict(settings: AppSettings) -> dict[str, Any]:
    def convert(s: Any) -> Any:
        if isinstance(s, Variable):
            return s.get()

        if isinstance(s, dict):
            return {k: convert(v) for k, v in s.items()}

        if not is_dataclass(s):
            raise AppSettingsException(f"unsupported type: {s}({type(s)})")

        result: dict[str, Any] = {}
        for field in fields(s):
            k, v = field.name, getattr(s, field.name)
            if isinstance(v, Variable):
                result[k] = v.get()
            else:
                result[k] = convert(v)
        return result

    return convert(settings)  # type: ignore[no-any-return]
