import logging
import tkinter as tk
from typing import Any

from pokecontrollerext.singletons.app.model import get_app_model
from pokecontrollerext.singletons.app.settings import get_app_settings
from pokecontrollerext.widgets.combobox import Combobox
from pokecontrollerext.widgets.components import ComponentBuilder
from pokecontrollerext.widgets.frame import Frame

logger = logging.getLogger(__name__)


class SerialSettingsPane(Frame):
    _port_combobox: Combobox

    def __init__(self, master: tk.Misc, *args: Any, **kwargs: Any) -> None:
        super().__init__(master, *args, **kwargs)

        self._app_settings = get_app_settings()
        self._app_model = get_app_model()

        self._serial_ports = self._app_model.load_serial_ports()

        self._port = self._app_settings.serial.port
        self._port_name = self._app_settings.serial.port_name
        self._baud_rate = self._app_settings.serial.baud_rate
        self._data_format = self._app_settings.serial.data_format
        self._show_data = self._app_settings.serial.show_data

        self.build_ui()

    def build_ui(self) -> None:
        label_width = 16
        frame = (
            ComponentBuilder(self)
            .add_frame_row()
            .add_label(text="Port:", width=label_width)
            .add_combobox(
                variable=self._port, values=[s.path for s in self._serial_ports]
            )
            .add_button(text="Reload", command=self._on_port_reload_pressed)
            .end()
            .add_frame_row()
            .add_label(text="Port Name:", width=label_width)
            .add_label(variable=self._port_name)
            .end()
            .add_frame_row()
            .add_label(text="Baud Rate:", width=label_width)
            .add_combobox(
                variable=self._baud_rate,
                values=[str(i) for i in self._app_model.load_serial_baud_rate_list()],
            )
            .end()
            .add_frame_row()
            .add_label(text="Data Format:", width=label_width)
            .add_combobox(
                variable=self._data_format,
                values=self._app_model.load_serial_data_format_list(),
            )
            .end()
            .add_frame_row()
            .add_label(text="Show Data:", width=label_width)
            .add_checkbutton(self._show_data, "")
            .end()
            .build()
        )

        frame.pack(expand=False, fill=tk.BOTH, anchor=tk.CENTER)

    def _on_port_reload_pressed(self) -> None:
        serial_ports = [s.path for s in self._app_model.load_serial_ports()]
        self._port_combobox.configure(values=serial_ports)
