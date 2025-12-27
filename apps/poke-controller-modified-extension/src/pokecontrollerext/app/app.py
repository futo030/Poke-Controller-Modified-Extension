import logging
import tkinter as tk
import tkinter.messagebox as mb
from typing import Any

from pokecontrollerext.app.exception import AppRuntimeException
from pokecontrollerext.app.translation import t
from pokecontrollerext.singletons.app.command import (
    setup_app_command_state,
)
from pokecontrollerext.singletons.app.model import setup_app_model
from pokecontrollerext.singletons.app.settings import setup_app_settings
from pokecontrollerext.singletons.app.style import setup_style_manager
from pokecontrollerext.singletons.app.translation import setup_translation
from pokecontrollerext.singletons.runtime.app_info import get_app_info
from pokecontrollerext.singletons.runtime.papico import get_papico
from pokecontrollerext.singletons.runtime.resources import (
    get_app_resources,
)
from pokecontrollerext.singletons.runtime.runtime_info import (
    get_app_runtime_info,
)

logger = logging.getLogger(__name__)


class App(tk.Tk):
    def __init__(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)

        self._app_runtime_info = get_app_runtime_info()
        self._app_info = get_app_info()
        self._app_command_state = setup_app_command_state()

        self._papico = get_papico()
        self._papico.initialize_external_tools()
        if (settings := self._papico.load_settings().data) is None:
            raise AppRuntimeException("App settings couldn't load.")
        self._settings = setup_app_settings(settings)
        setup_app_model()

        setup_translation(
            base_dir=self._app_info.application_root / "translations",
            language=self._settings.general.language.get(),
        )

        self._resources = get_app_resources()

        self._style_manager = setup_style_manager(self)
        self._style_manager.change_theme(self._settings.general.theme.get())

        # Title
        self.title(f"{self._app_info.name}(v{self._app_info.version})")

        # Camera
        self._camera_id = self._settings.capture.camera_id
        try:
            self._resources.camera.open(camera_id=self._camera_id.get())
        except Exception as e:
            logger.warning(f"Failed to open camera: {e}")

        # Serial
        self._serial_port = self._settings.serial.port
        self._serial_baud_rate = self._settings.serial.baud_rate
        try:
            self._resources.serial.open(
                port_path=self._serial_port.get(),
                baud_rate=self._serial_baud_rate.get(),
            )
        except Exception as e:
            logger.warning(f"Failed to open serial port: {e}")

        self.protocol("WM_DELETE_WINDOW", self._on_closing)

        self._register_traces()

    def run(self) -> None:
        self.mainloop()

    def _register_traces(self) -> None:
        self._settings.general.theme.trace_add("write", self._apply_theme)

    def _apply_theme(self, *_: Any) -> None:
        self._style_manager.change_theme(self._settings.general.theme.get())

    def _on_closing(self) -> None:
        should_close = mb.askyesno(
            title=self._app_info.name,
            message=t("app.message.close_confirm"),
        )
        if not should_close:
            return

        self._papico.save_settings()
        self.destroy()
