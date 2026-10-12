#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Serial タブ: シリアルポートの選択と接続、送るデータの形式
"""
from __future__ import annotations

import tkinter as tk
import platform
import tkinter.ttk as ttk
from services.serial_service import port_number
from Commands.transport import transport_names


class SerialPanelMixin:
    """
    Serial タブ: シリアルポートの選択と接続、送るデータの形式
    (PokeControllerApp に取り込んで使う。部品や設定は self の属性として、ほかのファイルと共有する)
    """

    def _buildSerialTab(self) -> None:
        """
        Serial タブの部品を作る(起動時に1回だけ呼ぶ)
        """
        self.serial_f = ttk.Frame(self.controller_nb)
        # Connection(接続) と Data(送るデータ) の2つの枠に分ける
        self.serial_f.columnconfigure(0, weight=1)
        self.settings_lf = ttk.Labelframe(self.serial_f)
        self.serial_device_name_label = ttk.Label(self.settings_lf)
        self.serial_device_name_label.configure(text="Device:")
        self.serial_device_name_label.grid(column="0", padx=(8, 4), pady="4", row="0", sticky="w")
        self.serial_device_name_cb = ttk.Combobox(self.settings_lf)
        self.serial_device_name = tk.StringVar(value="(選択してください)")
        self.serial_device_name_cb.configure(
            state="normal", textvariable=self.serial_device_name
        )
        self.serial_device_name_cb.grid(column="1", padx=(4, 8), pady="4", row="0", sticky="ew")
        self.serial_device_name_cb.bind("<<ComboboxSelected>>", self.set_device, add="")
        self.com_port_label = ttk.Label(self.settings_lf)
        if platform.system() == "Windows" or platform.system() == "Darwin":
            self.com_port_label.configure(text="COM Port:")
        else:
            self.com_port_label.configure(text="Port:")
        self.com_port_label.grid(column="0", padx=(8, 4), pady="4", row="1", sticky="w")
        self.com_port_f = ttk.Frame(self.settings_lf)
        self.com_port_entry = ttk.Entry(self.com_port_f)
        self.com_port = tk.IntVar(value="")
        self.com_port_name = tk.StringVar()  # added
        self.com_port_entry.configure(
            state="readonly", textvariable=self.com_port, width="5"
        )
        self.com_port_entry.pack(side="left", padx="4")
        self.baud_rate_label = ttk.Label(self.com_port_f)
        self.baud_rate_label.configure(text="Baud Rate:")
        self.baud_rate_label.pack(side="left", padx=(16, 4))
        self.baud_rate_cb = ttk.Combobox(self.com_port_f)
        self.baud_rate = tk.StringVar(value="")
        self.baud_rate_cb.configure(
            justify="right",
            state="readonly",
            textvariable=self.baud_rate,
            values="9600 4800 115200",
        )
        self.baud_rate_cb.configure(width="8")
        self.baud_rate_cb.pack(side="left", padx="4")
        self.baud_rate_cb.bind("<<ComboboxSelected>>", self.applyBaudRate, add="")
        self.com_port_f.grid(column="1", pady="4", row="1", sticky="w")
        self.serial_buttons_f = ttk.Frame(self.settings_lf)
        self.scan_device_button = ttk.Button(self.serial_buttons_f)
        self.scan_device_button.configure(text="Scan Device")
        self.scan_device_button.pack(side="left", padx="4")
        self.scan_device_button.configure(command=self.locateDeviceCmbbox)
        self.reload_com_port_button = ttk.Button(self.serial_buttons_f)
        self.reload_com_port_button.configure(text="Reload Port")
        self.reload_com_port_button.pack(side="left", padx="4")
        self.reload_com_port_button.configure(command=self.activateSerial)
        self.disconnect_com_port_button = ttk.Button(self.serial_buttons_f)
        self.disconnect_com_port_button.configure(text="Disconnect Port")
        self.disconnect_com_port_button.pack(side="left", padx=(4, 8))
        self.disconnect_com_port_button.configure(command=self.inactivateSerial)
        self.serial_buttons_f.grid(column="0", columnspan="2", pady="4", row="2", sticky="e")
        self.settings_lf.columnconfigure(1, weight=1)
        self.settings_lf.configure(text="Connection")
        self.settings_lf.grid(column="0", padx="5", pady="3", row="0", sticky="nsew")
        self.serial_data_lf = ttk.Labelframe(self.serial_f)
        self.serial_data_format_name_label = ttk.Label(self.serial_data_lf)
        self.serial_data_format_name_label.configure(text="Format:")
        self.serial_data_format_name_label.grid(column="0", padx=(8, 4), pady="4", row="0", sticky="w")
        # 送信方式の登録簿にある形式のうち、この環境で使えるもの
        # (FTDI直結の基板用の形式は、ftd2xxが使える場合のみ)
        serial_data_format_list = transport_names()
        self.serial_data_format_list = serial_data_format_list
        self.serial_data_format_name_cb = ttk.Combobox(self.serial_data_lf)
        self.serial_data_format_name = tk.StringVar(value="Default")
        self.serial_data_format_name_cb.configure(
            state="normal",
            textvariable=self.serial_data_format_name,
            values=serial_data_format_list,
        )
        self.serial_data_format_name_cb.configure(width="22")
        self.serial_data_format_name_cb.grid(column="1", padx=(4, 8), pady="4", row="0", sticky="ew")
        self.serial_data_format_name_cb.bind(
            "<<ComboboxSelected>>", self.set_serial_data_format
        )
        self.show_serial_checkbox = ttk.Checkbutton(self.serial_data_lf)
        self.is_show_serial = tk.BooleanVar()  # modified
        self.show_serial_checkbox.configure(
            text="Show Serial", variable=self.is_show_serial
        )
        self.show_serial_checkbox.grid(column="0", columnspan="2", padx=(8, 4), pady="4", row="1", sticky="w")
        self.serial_data_lf.configure(text="Data")
        self.serial_data_lf.grid(column="1", padx="5", pady="3", row="0", sticky="nsew")
        # self.serial_f.configure(height='200', width='200')    # removed
        self.serial_f.pack()
        self.controller_nb.add(self.serial_f, padding="5", sticky="nsew", text="Serial")

    def locateDeviceCmbbox(self) -> None:
        """Scan Device ボタン(と起動時): シリアルポートの一覧を取得して、Device の選択肢に入れる"""
        # ポート情報取得
        self.serial_devices = self.serial_service.list_port_descriptions()
        self.serial_device_name_cb["values"] = self.serial_devices

    def set_init_device_name(self) -> None:
        """起動時: 設定されているポート番号に当たるデバイスが一覧にあれば、Device に表示する"""
        description = self.serial_service.find_description(self.serial_devices, self.com_port.get())
        if description is not None:
            self.serial_device_name.set(description)

    def set_device(self, event: tk.Event | None = None) -> None:
        """
        Device を選んだとき: 選んだデバイスのポート番号を COM Port に入れる
        (説明に "COM番号" が無いデバイスの場合は、COM Port を変えない)
        """
        try:
            self.com_port.set(port_number(self.serial_device_name.get()))
        except (AttributeError, ValueError):
            pass

    def set_serial_data_format(self, event: tk.Event | None = None) -> None:
        """
        Format を選んだとき(と起動時): 送るデータの形式を切り替え、その形式で決まるボーレートに合わせて接続し直す
        (Software-Controller の HAT の初期化と、プレビューの右クリックの動作の切り替えも行う)
        """
        baud_rate = self.serial_service.set_data_format(self.serial_data_format_name.get())
        self.keys_software_controller.init_hat()
        self.preview.changeRightMouseMode(self.serial_data_format_name.get())

        # 送るデータの形式で決まるボーレートに合わせる(FTDI直結の基板はボーレートを使わない)
        if baud_rate is not None:
            print(f"ボーレートを強制的に{baud_rate}に変更します。")
            self.baud_rate.set(str(baud_rate))
        self.activateSerial()

    def applyBaudRate(self, event: tk.Event | None = None) -> None:
        """Baud Rate を選んだとき: 何もしない(選んだ値は、次に接続するときに使われる)"""
        pass

    def activateSerial(self) -> None:
        """Reload Port ボタン(と起動時など): 表示中のポートとボーレートで接続し、接続できたら設定に保存する"""
        connected = self.serial_service.connect(self.com_port.get(), self.com_port_name.get(), self.baud_rate.get())
        # キーボードでの手動操作の入力先(接続できなかった場合はNone)
        self.keyPress = self.serial_service.key_press
        if connected:
            self.settings.com_port.set(self.com_port.get())
            self.settings.baud_rate.set(self.baud_rate.get())
            self.settings.save()

    def inactivateSerial(self) -> None:
        """Disconnect Port ボタン: シリアルポートを切断する"""
        self.serial_service.disconnect()
        self.keyPress = self.serial_service.key_press
