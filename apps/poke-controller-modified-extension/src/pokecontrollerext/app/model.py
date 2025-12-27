import datetime
import logging
import subprocess
import threading
import tkinter as tk
from pathlib import Path

from pokecontroller.core.camera import CameraDetector, CameraInfo
from pokecontroller.core.controller.switch import SwitchControllerState
from pokecontroller.core.image import RawImage, write
from pokecontroller.core.notification import DiscordConfig, DiscordNotifier
from pokecontroller.core.notification.desktop import DesktopNotifier
from pokecontroller.core.serial import SerialPort, get_serial_ports
from pokecontroller.utils import platform
from pokecontroller.utils.datetime import format_datetime

from pokecontrollerext.singletons.app.settings import get_app_settings
from pokecontrollerext.singletons.runtime.app_info import get_app_info
from pokecontrollerext.singletons.runtime.papico import get_papico
from pokecontrollerext.singletons.runtime.resources import (
    get_app_resources,
)
from pokecontrollerext.singletons.runtime.runtime_info import (
    get_app_runtime_info,
)

if not platform.is_macos():
    from pokecontroller.core.controller.switch.keyboard import SwitchKeyboard
    from pokecontroller.core.controller.switch.pro_controller import SwitchProController
    from pokecontroller.core.controller.switch.serializers.leonardo import (
        SwitchControllerStateSerializer,
    )

logger = logging.getLogger(__name__)


class SwitchProControllerRecorder:
    def __init__(self, base_dir: Path, should_record: tk.BooleanVar) -> None:
        self._file_path = (
            base_dir / "Controller_Log" / f"controller_log_{format_datetime()}.txt"
        )
        self._log: list[str] = []
        self._should_record = should_record

    def record(self, state: SwitchControllerState) -> None:
        if not self._should_record.get():
            if self._log:
                self.write()
            return

        today = datetime.datetime.today()
        serialized = SwitchControllerStateSerializer.serialize(state)
        self._log.append(f"{today},{serialized}\n")
        if len(self._log) >= 100:
            self.write()

    def write(self) -> None:
        with open(self._file_path, "a", encoding="utf-8") as f:
            f.writelines(self._log)
        self._log.clear()


class AppModel:
    """アプリケーションのモデルクラス。
    色々な場所から呼び出される汎用的なアプリケーションのロジックや、複雑なロジックはここに集約したい。
    """

    def __init__(self) -> None:
        self._runtime_info = get_app_runtime_info()
        self._app_resources = get_app_resources()
        self._app_info = get_app_info()
        self._app_settings = get_app_settings()
        self._papico = get_papico()

        app_name = self._app_info.name
        app_version = self._app_info.version
        base_dir = self._runtime_info.base_dir
        profile = self._runtime_info.profile

        try:
            self._discord_notifier: DiscordNotifier | None = DiscordNotifier(
                config=DiscordConfig(
                    path=base_dir / "profiles" / profile / "discord_token.ini"
                )
            )
        except Exception:
            self._discord_notifier = None

        self._desktop_notifier = DesktopNotifier(
            title=f"{app_name} ver. {app_version}(profile: {profile})"
        )

        if platform.is_macos():
            self._keyboard = None
        else:
            serial = self._app_resources.serial
            keymap = self._app_settings.to_dict()["device"]["keyboard"]["keymap"]
            self._keyboard = SwitchKeyboard(serial, keymap)

        if platform.is_macos():
            self._pro_controller = None
        else:
            serial = self._app_resources.serial
            recorder = SwitchProControllerRecorder(
                base_dir=base_dir,
                should_record=self._app_settings.device.pro_controller.enabled_record,
            )
            self._pro_controller = SwitchProController(serial, recorder)

    def load_camera_list(self) -> list[CameraInfo]:
        return CameraDetector(max_cameras=20).detect()

    def load_camera_size_list(self) -> list[str]:
        return [f"{320 * i}x{180 * i}" for i in range(1, 7)]

    def connect_camera(self) -> None:
        camera = self._app_resources.camera
        camera_id = self._app_settings.capture.camera_id.get()
        camera.open(camera_id=camera_id)

    def save_screencapture(self) -> None:
        capture_dir = self._runtime_info.base_dir / "Captures"
        file = capture_dir / f"{format_datetime()}.png"

        if not capture_dir.exists():
            capture_dir.mkdir(parents=True)

        camera = self._app_resources.camera
        if (frame := camera.frame) is not None:
            write(frame, str(file), ())

    def open_screencapture_directory_window(self) -> None:
        capture_dir = self._runtime_info.base_dir / "Captures"
        self.open_dir(capture_dir)

    def load_serial_ports(self) -> list[SerialPort]:
        return get_serial_ports()

    def load_serial_baud_rate_list(self) -> list[int]:
        return [4800, 9600, 115200]

    def load_serial_data_format_list(self) -> list[str]:
        return ["Default", "Qingpi", "3DS Controller"]

    def connect_serial_port(self) -> None:
        serial = self._app_resources.serial
        port = self._app_settings.serial.port.get()
        baud_rate = self._app_settings.serial.baud_rate.get()
        serial.open(port_path=port, baud_rate=baud_rate)

    def disconnect_serial_port(self) -> None:
        serial = self._app_resources.serial
        serial.close()

    def notify_desktop(self, message: str) -> None:
        self._desktop_notifier.notify(message=message)

    def notify_discord(
        self,
        message: str | None = None,
        image: RawImage | None = None,
    ) -> None:
        if (notifier := self._discord_notifier) is None:
            return
        notifier.notify(message=message, image=image)

    def open_dir(self, dir_path: Path) -> None:
        if not dir_path.exists() or not dir_path.is_dir():
            logger.warning(f"Directory not found: {dir_path}")

        if platform.is_windows():
            program = ["explorer"]
        else:
            program = ["open"]
        program.append(str(dir_path))
        subprocess.run(program)

    def start_keyboard(self) -> None:
        if (keyboard := self._keyboard) is None:
            return
        keyboard.start()

    def stop_keyboard(self) -> None:
        if (keyboard := self._keyboard) is None:
            return
        keyboard.stop()

    def start_pro_controller(self) -> None:
        if (pro_controller := self._pro_controller) is None:
            return
        threading.Thread(target=pro_controller.start_loop).start()

    def stop_pro_controller(self) -> None:
        if (pro_controller := self._pro_controller) is None:
            return
        pro_controller.stop()
