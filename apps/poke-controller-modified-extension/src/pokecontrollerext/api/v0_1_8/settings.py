import configparser
import logging
from typing import Protocol

from pokecontrollerext.papico import Papico
from pokecontrollerext.singletons.app.settings import get_app_settings
from pokecontrollerext.singletons.runtime.papico import get_papico

logger = logging.getLogger(__name__)


class Value[T](Protocol):
    def get(self) -> T: ...

    def set(self, value: T) -> None: ...


class ComPortValue:
    def __init__(self, backing_field: Value[str]) -> None:
        self._backing_field = backing_field

    def get(self) -> int | str:
        if (bfv := self._backing_field.get()).isdigit():
            return int(bfv)
        return bfv

    def set(self, value: int | str) -> None:
        if isinstance(value, int):
            self._backing_field.set(str(value))
        else:
            self._backing_field.set(value)


class FpsValue:
    def __init__(self, backing_field: Value[int]) -> None:
        self._backing_field = backing_field

    def get(self) -> str:
        return str(self._backing_field.get())

    def set(self, value: str) -> None:
        self._backing_field.set(int(value))


class CommandClassDict(dict[str, str]):
    def __init__(self, backing_fields: dict[str, Value[str]]) -> None:
        super().__init__()
        self._backing_fields = backing_fields

    def __getitem__(self, key: str) -> str:
        return self._backing_fields[key].get()

    def __setitem__(self, key: str, value: str) -> None:
        self._backing_fields[key].set(value)

    def __contains__(self, key: object) -> bool:
        return key in self._backing_fields or str(key) in self._backing_fields

    def __missing__(self, key: str | int) -> str:
        if isinstance(key, str):
            return "None"
        if isinstance(key, int) and 1 <= key <= 10:
            return self[str(key)]
        return "None"


class GuiSettings:
    SETTING_PATH: str

    _papico: Papico

    camera_id: Value[int]
    com_port: Value[int | str]
    com_port_name: Value[str]
    baud_rate: Value[int]
    fps: Value[str]
    show_size: Value[str]
    is_show_realtime: Value[bool]
    is_show_value: Value[bool]
    is_show_guide: Value[bool]
    is_show_serial: Value[bool]
    is_use_keyboard: Value[bool]
    serial_data_format_name: Value[str]
    command_class_dict: dict[str, str]
    command_name_dict: dict[str, Value[str]]
    is_win_notification_start: Value[bool]
    is_win_notification_end: Value[bool]
    is_line_notification_start: Value[bool]
    is_line_notification_end: Value[bool]
    is_discord_notification_start: Value[bool]
    is_discord_notification_end: Value[bool]

    def __init__(self) -> None:
        self._papico = get_papico()
        GuiSettings.SETTING_PATH = str(self._papico.settings_path)
        self._app_settings = get_app_settings()
        self._assign_settings()

        self.setting = configparser.ConfigParser()
        self.setting.optionxform = str  # type: ignore[method-assign, assignment]
        self._assign_setting_config()

    @property
    def touchscreen_start_x(self) -> int:
        return self._app_settings.device.touchscreen.sx.get()

    @touchscreen_start_x.setter
    def touchscreen_start_x(self, value: int) -> None:
        self._app_settings.device.touchscreen.sx.set(value)

    @property
    def touchscreen_start_y(self) -> int:
        return self._app_settings.device.touchscreen.sy.get()

    @touchscreen_start_y.setter
    def touchscreen_start_y(self, value: int) -> None:
        self._app_settings.device.touchscreen.sy.set(value)

    @property
    def touchscreen_end_x(self) -> int:
        return self._app_settings.device.touchscreen.ex.get()

    @touchscreen_end_x.setter
    def touchscreen_end_x(self, value: int) -> None:
        self._app_settings.device.touchscreen.ex.set(value)

    @property
    def touchscreen_end_y(self) -> int:
        return self._app_settings.device.touchscreen.ey.get()

    @touchscreen_end_y.setter
    def touchscreen_end_y(self, value: int) -> None:
        self._app_settings.device.touchscreen.ey.set(value)

    @property
    def area_size(self) -> str:
        return str(int(self._app_settings.widget.output.size_balance.get()))

    @area_size.setter
    def area_size(self, value: str) -> None:
        self._app_settings.widget.output.size_balance.set(float(value))

    @property
    def stdout_destination(self) -> str:
        return str(self._app_settings.widget.output.stdout.get())

    @stdout_destination.setter
    def stdout_destination(self, value: str) -> None:
        self._app_settings.widget.output.stdout.set(int(value))

    @property
    def right_frame_widget_mode(self) -> str:
        visible_output_1 = self._app_settings.widget.output.visible_output1.get()
        visible_output_2 = self._app_settings.widget.output.visible_output2.get()
        visible_software_controller = (
            self._app_settings.widget.software_controller.visible.get()
        )
        visibles: list[str] = []
        if visible_output_1:
            visibles.append("Output#1")
        if visible_output_2:
            visibles.append("Output#2")
        if visible_software_controller:
            visibles.append("Software-Controller")
        if len(visibles) == 3:
            return "ALL (default)"
        if len(visibles) == 2:
            return f"{visibles[0]} + {visibles[1]}"
        if len(visibles) == 1:
            return f"{visibles[0]} Only"
        return "None"

    @right_frame_widget_mode.setter
    def right_frame_widget_mode(self, value: str) -> None:
        visible_output1 = self._app_settings.widget.output.visible_output1
        visible_output2 = self._app_settings.widget.output.visible_output2
        visible_software_controller = (
            self._app_settings.widget.software_controller.visible
        )

        if value == "ALL (default)":
            visible_output1.set(True)
            visible_output2.set(True)
            visible_software_controller.set(True)
            return
        if value == "None":
            visible_output1.set(False)
            visible_output2.set(False)
            visible_software_controller.set(False)
            return

        if "Output#1" in value:
            visible_output1.set(True)
        else:
            visible_output1.set(False)
        if "Output#2" in value:
            visible_output2.set(True)
        else:
            visible_output2.set(False)
        if "Software-Controller" in value:
            visible_software_controller.set(True)
        else:
            visible_software_controller.set(False)

    @property
    def pos_software_controller(self) -> str:
        position = self._app_settings.widget.software_controller.position.get()
        if position == "top":
            return "1"
        return "2"

    @pos_software_controller.setter
    def pos_software_controller(self, value: str) -> None:
        position = self._app_settings.widget.software_controller.position
        if value == "1":
            position.set("top")
        else:
            position.set("bottom")

    @property
    def pos_dialogue_buttons(self) -> str:
        position = self._app_settings.widget.dialog.confirm_buttons_position.get()
        if position == "top":
            return "1"
        if position == "bottom":
            return "2"
        return "3"

    @pos_dialogue_buttons.setter
    def pos_dialogue_buttons(self, value: str) -> None:
        position = self._app_settings.widget.dialog.confirm_buttons_position
        if value == "1":
            position.set("top")
        elif value == "2":
            position.set("bottom")
        else:
            position.set("both")

    def load(self) -> None:
        self._papico.reload_settings()
        self._assign_setting_config()

    def generate(self) -> None:
        self._papico.save_settings()

    def save(self, path: str | None = None) -> None:
        self._papico.save_settings()

    def _assign_settings(self) -> None:
        self.camera_id = self._app_settings.capture.camera_id
        self.fps = FpsValue(self._app_settings.capture.fps)
        self.show_size = self._app_settings.capture.size
        self.is_show_realtime = self._app_settings.capture.show_realtime
        self.is_show_value = self._app_settings.capture.show_matched
        self.is_show_guide = self._app_settings.capture.show_guide
        self.com_port = ComPortValue(self._app_settings.serial.port)
        self.port_name = self._app_settings.serial.port_name
        self.baud_rate = self._app_settings.serial.baud_rate
        self.is_show_serial = self._app_settings.serial.show_data
        self.serial_data_format_name = self._app_settings.serial.data_format
        self.is_use_keyboard = self._app_settings.device.keyboard.enabled
        self.is_win_notification_end = (
            self._app_settings.notification.windows.enabled_started
        )
        self.is_win_notification_start = (
            self._app_settings.notification.windows.enabled_ended
        )
        self.is_line_notification_end = (
            self._app_settings.notification.line.enabled_started
        )
        self.is_line_notification_start = (
            self._app_settings.notification.line.enabled_ended
        )
        self.is_discord_notification_end = (
            self._app_settings.notification.discord.enabled_started
        )
        self.is_discord_notification_start = (
            self._app_settings.notification.discord.enabled_ended
        )

        command_class_dict: dict[str, Value[str]] = {}
        self.command_name_dict = {}
        shortcuts = self._app_settings.command.shortcut.registered_commands
        for k, v in shortcuts.items():
            command_class_dict[k] = v.klass
            self.command_name_dict[k] = v.name
        self.command_class_dict = CommandClassDict(command_class_dict)

    def _assign_setting_config(self) -> None:
        self._assign_general_setting()
        self._assign_shortcut_setting()
        self._assign_notification_setting()
        self._assign_output_setting()

    def _assign_general_setting(self) -> None:
        self.setting["General Setting"] = {
            "camera_id": str(self.camera_id.get()),
            "com_port": str(self.com_port.get()),
            "com_port_name": self.com_port_name.get(),
            "baud_rate": str(self.baud_rate.get()),
            "fps": self.fps.get(),
            "show_size": self.show_size.get(),
            "is_show_realtime": str(self.is_show_realtime.get()),
            "is_show_value": str(self.is_show_value.get()),
            "is_show_guide": str(self.is_show_guide.get()),
            "is_show_serial": str(self.is_show_serial.get()),
            "is_use_keyboard": str(self.is_use_keyboard.get()),
            "serial_data_format_name": self.serial_data_format_name.get(),
            "touchscreen_start_x": str(self.touchscreen_start_x),
            "touchscreen_start_y": str(self.touchscreen_start_y),
            "touchscreen_end_x": str(self.touchscreen_end_x),
            "touchscreen_end_y": str(self.touchscreen_end_y),
        }

    def _assign_shortcut_setting(self) -> None:
        shortcut_setting = {}
        for i in range(1, 11):
            key = str(i)
            shortcut_setting[f"command_class_{i}"] = self.command_class_dict[key]
            shortcut_setting[f"command_name_{i}"] = self.command_name_dict[key].get()
        self.setting["Shortcut"] = shortcut_setting

    def _assign_notification_setting(self) -> None:
        self.setting["Notification"] = {
            "is_win_notification_start": str(self.is_win_notification_start.get()),
            "is_win_notification_end": str(self.is_win_notification_end.get()),
            "is_line_notification_start": str(self.is_line_notification_start.get()),
            "is_line_notification_end": str(self.is_line_notification_end.get()),
            "is_discord_notification_start": str(
                self.is_discord_notification_start.get()
            ),
            "is_discord_notification_end": str(self.is_discord_notification_end.get()),
        }

    def _assign_output_setting(self) -> None:
        self.setting["Output"] = {
            "area_size": self.area_size,
            "stdout_destination": self.stdout_destination,
            "widget_mode": self.right_frame_widget_mode,
            "software_controller_position": self.pos_software_controller,
            "dialogue_buttons_position": self.pos_dialogue_buttons,
        }
