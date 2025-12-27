import tkinter as tk
from typing import Any

from pokecontrollerext.app.translation import t
from pokecontrollerext.singletons.app.model import get_app_model
from pokecontrollerext.singletons.app.settings import get_app_settings
from pokecontrollerext.widgets.button import Button
from pokecontrollerext.widgets.checkbutton import Checkbutton
from pokecontrollerext.widgets.combobox import Combobox
from pokecontrollerext.widgets.frame import Frame
from pokecontrollerext.widgets.label import Label
from pokecontrollerext.widgets.labelframe import Labelframe
from pokecontrollerext.widgets.separator import Separator


class SerialSettings(Frame):
    def __init__(self, master: tk.Misc, *args: Any, **kwargs: Any) -> None:
        super().__init__(master, *args, **kwargs)

        self._app_settings = get_app_settings()
        self._app_model = get_app_model()

        self._port_list: list[str] = self._load_serial_ports()
        self._baud_rate_list: list[int] = self._load_serial_baud_rate_list()
        self._data_format_list: list[str] = self._load_serial_data_format_list()

        self._port = self._app_settings.serial.port
        self._baud_rate = self._app_settings.serial.baud_rate
        self._data_format = self._app_settings.serial.data_format
        self._show_data = self._app_settings.serial.show_data

        self.build_ui()

    def build_ui(self) -> None:
        # Create Labelframes
        serial_settings = self._build_serial_settings()
        data_settings = self._build_data_settings()

        # Layout
        serial_settings.pack(expand=False, fill=tk.X, anchor=tk.N, pady=4)
        data_settings.pack(expand=False, fill=tk.X, anchor=tk.N, pady=4)

    def _build_serial_settings(self) -> Labelframe:
        labelframe = Labelframe(self, text="Port Settings")

        # Port
        port_label = Label(
            labelframe,
            text=t("main.settings.serial.port.port.label"),
            tooltip=t("main.settings.serial.port.port.label.tooltip"),
        )
        port_entry = Combobox(
            labelframe,
            tooltip=t("main.settings.serial.port.port.combobox.tooltip"),
            width=5,
            textvariable=self._port,
            values=self._port_list,
        )
        if self._port.get() not in self._port_list:
            port_entry.current(0)

        # Baud Rate
        baud_rate_label = Label(
            labelframe,
            text=t("main.settings.serial.port.baud_rate.label"),
            tooltip=t("main.settings.serial.port.baud_rate.label.tooltip"),
        )
        baud_rate_combobox = Combobox(
            labelframe,
            tooltip=t("main.settings.serial.port.baud_rate.combobox.tooltip"),
            width=6,
            justify=tk.RIGHT,
            textvariable=self._baud_rate,
            values=[str(i) for i in self._baud_rate_list],
        )

        # Reconnect Button
        reconnect_button = Button(
            labelframe,
            text=t("main.settings.serial.port.reload"),
            tooltip=t("main.settings.serial.port.reload.tooltip"),
            command=self._on_reconnect_pressed,
        )

        # Disconnect Button
        disconnect_button = Button(
            labelframe,
            text=t("main.settings.serial.port.disconnect"),
            tooltip=t("main.settings.serial.port.disconnect.tooltip"),
            command=self._on_disconnect_pressed,
        )

        # Layout
        port_label.pack(expand=False, side=tk.LEFT, padx=4)
        port_entry.pack(expand=True, fill=tk.X, side=tk.LEFT)
        Separator(master=labelframe, orient=tk.VERTICAL).pack(
            expand=False, fill=tk.Y, side=tk.LEFT, padx=5, pady=8
        )
        baud_rate_label.pack(expand=False, side=tk.LEFT)
        baud_rate_combobox.pack(expand=False, fill=tk.X, side=tk.LEFT)
        Separator(master=labelframe, orient=tk.VERTICAL).pack(
            expand=False, fill=tk.Y, side=tk.LEFT, padx=5, pady=8
        )
        reconnect_button.pack(expand=False, fill=tk.X, side=tk.LEFT, padx=4, pady=4)
        disconnect_button.pack(expand=False, fill=tk.X, side=tk.LEFT, padx=4, pady=4)

        return labelframe

    def _build_data_settings(self) -> Labelframe:
        labelframe = Labelframe(self, text="Data")

        # Data Format
        data_format_label = Label(
            labelframe,
            text=t("main.settings.serial.data.format.label"),
            anchor=tk.CENTER,
        )
        data_format_combobox = Combobox(
            labelframe,
            state=tk.NORMAL,
            textvariable=self._data_format,
            values=self._data_format_list,
        )

        # Show Serial
        show_serial_checkbutton = Checkbutton(
            labelframe,
            text=t("main.settings.serial.data.show_data"),
            tooltip=t("main.settings.serial.data.show_data.tooltip"),
            variable=self._show_data,
        )

        # Layout
        data_format_label.pack(expand=False, side=tk.LEFT, padx=4, pady=(0, 4))
        data_format_combobox.pack(expand=False, side=tk.LEFT, padx=4, pady=(0, 4))
        show_serial_checkbutton.pack(expand=False, side=tk.LEFT, padx=4, pady=(0, 4))

        return labelframe

    def _load_serial_ports(self) -> list[str]:
        return [port.path for port in self._app_model.load_serial_ports()]

    def _load_serial_baud_rate_list(self) -> list[int]:
        return self._app_model.load_serial_baud_rate_list()

    def _load_serial_data_format_list(self) -> list[str]:
        return self._app_model.load_serial_data_format_list()

    def _on_reconnect_pressed(self) -> None:
        self._app_model.connect_serial_port()

    def _on_disconnect_pressed(self) -> None:
        self._app_model.disconnect_serial_port()
