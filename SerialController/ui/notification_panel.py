#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Notification タブ: コマンドの開始・終了時の通知
"""
from __future__ import annotations

import tkinter as tk
import tkinter.ttk as ttk
from Commands.CommandBase import Command
from services import notification_image


class NotificationPanelMixin:
    """
    Notification タブ: コマンドの開始・終了時の通知
    (PokeControllerApp に取り込んで使う。部品や設定は self の属性として、ほかのファイルと共有する)
    """

    def _buildNotificationTab(self) -> None:
        """
        Notification タブの部品を作る(起動時に1回だけ呼ぶ)
        """
        self.notification_f = ttk.Frame(self.controller_nb)
        self.windows_notification_lf = ttk.Labelframe(self.notification_f)
        self.win_notification_start_checkbox = ttk.Checkbutton(
            self.windows_notification_lf
        )
        self.is_win_notification_start = tk.BooleanVar()
        self.win_notification_start_checkbox.configure(
            text="Start", variable=self.is_win_notification_start
        )
        self.win_notification_start_checkbox.grid(column="0", padx=(8, 4), pady="4", row="0", sticky="w")
        self.win_notification_start_checkbox.configure(
            command=self.mode_change_notification
        )
        self.win_notification_end_checkbox = ttk.Checkbutton(
            self.windows_notification_lf
        )
        self.is_win_notification_end = tk.BooleanVar()
        self.win_notification_end_checkbox.configure(
            text="End", variable=self.is_win_notification_end
        )
        self.win_notification_end_checkbox.grid(column="1", padx="4", pady="4", row="0", sticky="w")
        self.win_notification_end_checkbox.configure(
            command=self.mode_change_notification
        )
        self.send_win_button = ttk.Button(self.windows_notification_lf)
        self.send_win_button.configure(text="Test")
        self.send_win_button.grid(column="0", columnspan="2", padx="8", pady="4", row="1", sticky="ew")
        self.send_win_button.configure(command=self.sendWinNotfication)
        self.windows_notification_lf.configure(text="Windows Notification")
        self.windows_notification_lf.grid(column="0", padx="5", pady="3", row="0", sticky="new")
        self.notification_f.columnconfigure(0, weight=1, uniform="notification")
        self.line_notification_lf = ttk.Labelframe(self.notification_f)
        self.line_notification_start_checkbox = ttk.Checkbutton(
            self.line_notification_lf
        )
        self.is_line_notification_start = tk.BooleanVar()
        self.line_notification_start_checkbox.configure(
            text="Start", variable=self.is_line_notification_start
        )
        self.line_notification_start_checkbox.grid(column="0", padx=(8, 4), pady="4", row="0", sticky="w")
        self.line_notification_start_checkbox.configure(
            command=self.mode_change_notification
        )
        self.line_notification_end_checkbox = ttk.Checkbutton(self.line_notification_lf)
        self.is_line_notification_end = tk.BooleanVar()
        self.line_notification_end_checkbox.configure(
            text="End", variable=self.is_line_notification_end
        )
        self.line_notification_end_checkbox.grid(column="1", padx="4", pady="4", row="0", sticky="w")
        self.line_notification_end_checkbox.configure(
            command=self.mode_change_notification
        )
        self.send_line_button = ttk.Button(self.line_notification_lf)
        self.send_line_button.configure(text="Test")
        self.send_line_button.grid(column="0", columnspan="2", padx="8", pady="4", row="1", sticky="ew")
        self.send_line_button.configure(command=self.sendLineImage)
        self.line_notification_lf.configure(text="Line Notification")
        self.line_notification_lf.grid(column="1", padx="5", pady="3", row="0", sticky="new")
        self.notification_f.columnconfigure(1, weight=1, uniform="notification")
        self.discord_notification_lf = ttk.Labelframe(self.notification_f)
        self.discord_notification_start_checkbox = ttk.Checkbutton(
            self.discord_notification_lf
        )
        self.is_discord_notification_start = tk.BooleanVar()
        self.discord_notification_start_checkbox.configure(
            text="Start", variable=self.is_discord_notification_start
        )
        self.discord_notification_start_checkbox.grid(column="0", padx=(8, 4), pady="4", row="0", sticky="w")
        self.discord_notification_start_checkbox.configure(
            command=self.mode_change_notification
        )
        self.discord_notification_end_checkbox = ttk.Checkbutton(
            self.discord_notification_lf
        )
        self.is_discord_notification_end = tk.BooleanVar()
        self.discord_notification_end_checkbox.configure(
            text="End", variable=self.is_discord_notification_end
        )
        self.discord_notification_end_checkbox.grid(column="1", padx="4", pady="4", row="0", sticky="w")
        self.discord_notification_end_checkbox.configure(
            command=self.mode_change_notification
        )
        # 通知に付ける画像(画面 = カメラの今の画像 / ウィンドウ全体)。Test・Start・End と、Main Panel の Discord ボタンに効く
        self.discord_notification_image = tk.StringVar(value=notification_image.DEFAULT)
        self.discord_notification_image_radios = {}
        for column, kind in enumerate(notification_image.KINDS):
            radio = ttk.Radiobutton(
                self.discord_notification_lf, text=notification_image.LABELS[kind], value=kind,
                variable=self.discord_notification_image, command=self.mode_change_notification,
            )  # fmt: skip
            radio.grid(column=column, padx=(8, 4) if column == 0 else 4, pady="4", row="1", sticky="w")
            self.discord_notification_image_radios[kind] = radio
        self.send_discord_button = ttk.Button(self.discord_notification_lf)
        self.send_discord_button.configure(text="Test")
        self.send_discord_button.grid(column="0", columnspan="2", padx="8", pady="4", row="2", sticky="ew")
        self.send_discord_button.configure(command=self.sendDiscordImage)
        self.discord_notification_lf.configure(text="Discord Notification")
        self.discord_notification_lf.grid(column="2", padx="5", pady="3", row="0", sticky="new")
        self.notification_f.columnconfigure(2, weight=1, uniform="notification")
        self.notification_f.pack()
        self.controller_nb.add(self.notification_f, padding="5", sticky="nsew", text="Notification")
        # Maskタブ: キャプチャ画面の上に置く目隠し(長方形・楕円)
        self.masks = []

    def mode_change_notification(self, *event: object) -> None:
        """
        Notification タブのチェックボックスを切り替えたとき(と設定の読み込み後): チェックの状態を Command に反映する
        event: 使わない(チェックボックスの command からは引数なしで呼ばれる)
        """
        Command.isWinNotStart = self.is_win_notification_start.get()
        Command.isWinNotEnd = self.is_win_notification_end.get()
        Command.isLineNotStart = self.is_line_notification_start.get()
        Command.isLineNotEnd = self.is_line_notification_end.get()
        Command.isDiscordNotStart = self.is_discord_notification_start.get()
        Command.isDiscordNotEnd = self.is_discord_notification_end.get()
        # 通知に付ける画像は、コマンドのスレッドからも取り出すので、tkinter の変数ではなく、ふつうの値で持っておく
        self._discord_image_kind = notification_image.normalize(self.discord_notification_image.get())
        self._main_window_handle = self._mainWindowHandle()
        Command._notification_image = self.discordNotificationImage
