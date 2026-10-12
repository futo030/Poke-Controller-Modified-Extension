#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Status タブ(いちばん左。Camera タブの左): 今つながっている機器と、実行中のコマンドを表示する

- 表示するだけで、設定は変えない
- 表示する文字は services/status_text.py が作る
- Status タブを表示している間だけ、決まった間隔で調べ直す(ほかのタブを見ている間は、何もしない)
"""
from __future__ import annotations

import platform
import tkinter as tk
import tkinter.ttk as ttk

from Audio import AUDIO_AVAILABLE
from services import status_text

# Status タブを表示している間の、調べ直す間隔(ミリ秒)
STATUS_REFRESH_MS = 500
# 行の並び: (値を入れる属性の名前の元, 見出し)
STATUS_ROWS = (
    ("camera", "Camera Device:"),
    ("audio_input", "Audio Device (Input):"),
    ("audio_output", "(Output):"),
    ("serial", "Serial Device:"),
    ("command", "実行中のコマンド:"),
    ("started", "開始時間:"),
)


class StatusPanelMixin:
    """
    Status タブ: カメラ・音声・シリアルの機器と、実行中のコマンドの表示
    (PokeControllerApp に取り込んで使う。部品や設定は self の属性として、ほかのファイルと共有する)
    """

    def _buildStatusTab(self) -> None:
        """
        Status タブの部品を作る(起動時に1回だけ呼ぶ)
        """
        self.status_f = ttk.Frame(self.controller_nb)
        self.status_f.columnconfigure(0, weight=1)
        self.status_lf = ttk.Labelframe(self.status_f, text="Status")
        self.status_lf.columnconfigure(1, weight=1)
        # 行ごとの、表示する文字(status_values["camera"] など)
        self.status_values = {}
        self.status_value_labels = {}
        for row, (key, title) in enumerate(STATUS_ROWS):
            ttk.Label(self.status_lf, text=title).grid(column=0, row=row, padx=(8, 4), pady=3, sticky="e")
            value = tk.StringVar(value="")
            # (幅は、枠に合わせて伸ばす。長い名前で、タブの幅が広がらないように、求める幅は小さくしておく)
            label = ttk.Label(self.status_lf, textvariable=value, width=10, anchor="w")
            label.grid(column=1, row=row, padx=(4, 8), pady=3, sticky="ew")
            self.status_values[key] = value
            self.status_value_labels[key] = label
        self.status_lf.grid(column=0, row=0, sticky="ew")
        self.controller_nb.add(self.status_f, padding="5", sticky="nsew", text="Status")
        self._status_after = None
        # Status タブを表示したときに調べ直し、表示している間は、決まった間隔で調べ直す
        self.status_f.bind("<Map>", lambda event: self._scheduleStatusRefresh(0), add="+")

    def statusTexts(self) -> dict:
        """Status タブの各行に表示する文字を、今の状態から作る(行の名前 -> 文字)"""
        camera_opened = self._statusCameraOpened()
        audio = getattr(self, "audio", None)
        audio_available = AUDIO_AVAILABLE and audio is not None
        audio_running = bool(audio_available and audio.is_running)
        serial_opened = self._statusSerialOpened()
        service = getattr(self, "command_service", None)
        running = service is not None and service.is_running and service.current is not None
        return {
            "camera": status_text.camera_text(self.camera_name_fromDLL.get(), self.capture_size.get(), camera_opened),
            "audio_input": status_text.audio_input_text(
                self.audio_device_display.get() if audio_available else "", audio_running, audio_available
            ),
            "audio_output": status_text.audio_output_text(
                self.audio_output_device.get() if audio_available else "", audio_running,
                bool(self.is_audio_playback.get()) if audio_available else False, audio_available,
            ),
            "serial": status_text.serial_text(
                self.serial_device_name.get(), self._statusValue(self.com_port), self.baud_rate.get(), serial_opened,
                "COM" if platform.system() == "Windows" else "Port ",
            ),
            "command": status_text.command_text(service.current.NAME if running else None),
            "started": status_text.started_text(
                service.current.NAME if running else None, service.started_at if running else None
            ),
        }

    def _statusCameraOpened(self) -> bool:
        """
        カメラを開いているか。Camera.isOpened と同じ判定を、ログを出さずに行う
        (isOpened は、呼ぶたびに DEBUG のログを出す。Status タブは何度も調べるので、Log タブが埋まってしまう)
        """
        camera = getattr(self, "camera", None)
        source = getattr(camera, "camera", None)
        return bool(source is not None and source.isOpened())

    def _statusSerialOpened(self) -> bool:
        """シリアルポートを開いているか。Sender.isOpened と同じ判定を、ログを出さずに行う(理由は _statusCameraOpened と同じ)"""
        ser = getattr(self, "ser", None)
        port = getattr(ser, "ser", None)
        return bool(port is not None and port.isOpen())

    def _statusValue(self, variable: tk.Variable) -> object:
        """tkinter の変数の値(入力の途中などで、数として読めないときは、入っている文字のまま)"""
        try:
            return variable.get()
        except tk.TclError:
            return self.root.getvar(str(variable))

    def refreshStatus(self) -> None:
        """Status タブの表示を、今の状態に合わせる(変わった行だけを書き換える)"""
        for key, text in self.statusTexts().items():
            if self.status_values[key].get() != text:
                self.status_values[key].set(text)

    def _scheduleStatusRefresh(self, delay: int = STATUS_REFRESH_MS) -> None:
        """delay ミリ秒後に、Status タブを調べ直す(すでに予約していれば、何もしない)"""
        if self._status_after is None:
            self._status_after = self.root.after(delay, self._onStatusRefresh)

    def _onStatusRefresh(self) -> None:
        """Status タブを調べ直し、表示している間は、次も予約する(ほかのタブに切り替えると、止まる)"""
        self._status_after = None
        try:
            if not self.status_f.winfo_viewable():
                return
            self.refreshStatus()
        except tk.TclError:
            # ウィンドウを閉じている途中
            return
        except AttributeError:
            # 起動の途中(ほかのタブの部品を、まだ作っていない)。次の回に調べる
            pass
        self._scheduleStatusRefresh()
