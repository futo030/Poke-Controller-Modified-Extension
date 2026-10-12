#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Discordの通知先の設定画面(メニューバーの 設定 > Discord の通知先...)

- 通知先は、名前を付けて複数登録できる(プロファイルの discord_token.ini の、名前ごとのセクションに保存する)
- 名前は、コマンドの discord_text / discord_image の name(keys)で通知先を選ぶときに使う
- 既定の通知先 DISCORD_WEBHOOK は必ず作成する(未設定の間は、名前を DISCORD_WEBHOOK から変更できない)
"""
from __future__ import annotations

import tkinter as tk
import tkinter.messagebox as tkmsg
import tkinter.ttk as ttk
from logging import getLogger, DEBUG, NullHandler
from typing import Callable

from DiscordNotify import (
    DEFAULT_WEBHOOK,
    RECEIVE_SECTION,
    check_webhook_name,
    is_default_webhook_set,
    load_setting,
    next_webhook_name,
    save_setting,
    webhook_names,
)

_logger = getLogger(__name__)
_logger.addHandler(NullHandler())
_logger.setLevel(DEBUG)
_logger.propagate = True

TITLE = "Discord の通知先"
# 入力欄: (設定ファイルの項目名, 表示名)
FIELDS = (("webhook_url", "Webhook URL"), ("username", "Username"), ("avatar_url", "Avatar URL"))
ENTRY_WIDTH = 64


class DiscordSettingWindow:
    """
    Discord の通知先(名前ごとの Webhook URL・Username・Avatar URL)を登録・変更・削除するウィンドウ
    """

    def __init__(self, root: tk.Tk, setting_path: str, on_saved: Callable[[], None] | None = None):
        """
        root: メインウィンドウ(この位置を基準に表示する)
        setting_path: プロファイルの discord_token.ini
        on_saved: 保存・削除した後に呼ぶ関数
        """
        self.root = root
        self.setting_path = setting_path
        self.on_saved = on_saved
        self.setting = load_setting(setting_path)

        self.window = tk.Toplevel(root)
        self.window.title(TITLE)
        self.window.resizable(False, False)
        root_geometry = root.geometry().split("+")
        self.window.geometry("%+d%+d" % (100 + int(root_geometry[1]), 60 + int(root_geometry[2])))

        body = ttk.Frame(self.window, padding=10)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Name:").grid(column=0, row=0, padx=(0, 8), pady=3, sticky="w")
        self.name = tk.StringVar()
        self.name_cb = ttk.Combobox(body, textvariable=self.name, width=ENTRY_WIDTH - 3)
        self.name_cb.grid(column=1, row=0, pady=3, sticky="ew")
        self.name_cb.bind("<<ComboboxSelected>>", self.showSelected)
        self.name_cb.bind("<Return>", self.showSelected)
        self.name_cb.bind("<FocusOut>", self.showSelected)
        self.vars = {}
        for row, (key, label) in enumerate(FIELDS, start=1):
            ttk.Label(body, text=f"{label}:").grid(column=0, row=row, padx=(0, 8), pady=3, sticky="w")
            self.vars[key] = tk.StringVar()
            ttk.Entry(body, textvariable=self.vars[key], width=ENTRY_WIDTH).grid(column=1, row=row, pady=3, sticky="ew")
        self.note = tk.StringVar()
        ttk.Label(body, textvariable=self.note, wraplength=520, justify="left").grid(
            column=0, columnspan=2, row=len(FIELDS) + 1, pady=(6, 0), sticky="w"
        )

        buttons = ttk.Frame(body)
        buttons.grid(column=0, columnspan=2, row=len(FIELDS) + 2, pady=(10, 0), sticky="ew")
        ttk.Button(buttons, text="Save", width=9, command=self.save).pack(side="left")
        self.delete_button = ttk.Button(buttons, text="Delete", width=9, command=self.delete)
        self.delete_button.pack(side="left", padx=4)
        ttk.Button(buttons, text="Close", width=9, command=self.destroy).pack(side="right")
        self.window.bind("<Escape>", lambda event: self.destroy())

        self.refresh(next_webhook_name(webhook_names(self.setting)))
        _logger.debug("Create discord setting window")

    def refresh(self, name: str) -> None:
        """
        名前の候補と入力欄を、設定の内容に合わせる。name: 名前の欄に入れる値
        """
        names = webhook_names(self.setting)
        self.name_cb["values"] = names
        if is_default_webhook_set(self.setting):
            self.name_cb.configure(state="normal")
            self.delete_button.configure(state="normal")
            self.note.set(
                "Name は、コマンドの discord_text / discord_image で通知先を選ぶ名前です。"
                "登録済みの名前を選ぶと、その設定を変更できます。"
            )
        else:
            # 既定の通知先は必ず作成する: 設定されるまで、名前を変更できないようにする
            name = DEFAULT_WEBHOOK
            self.name_cb.configure(state="disabled")
            self.delete_button.configure(state="disabled")
            self.note.set(f"{DEFAULT_WEBHOOK} が設定されていないため、Name は変更できません。先に {DEFAULT_WEBHOOK} を設定してください。")
        self.name.set(name)
        self.showValues(name)

    def showValues(self, name: str) -> None:
        """名前 name の通知先の設定を、入力欄に表示する(登録されていない名前の場合は、空にする)"""
        for key, _ in FIELDS:
            self.vars[key].set(self.setting.get(name, key, fallback="") if self.setting.has_section(name) else "")

    def showSelected(self, event: tk.Event | None = None) -> None:
        """
        登録済みの名前が入力・選択された場合は、その設定を入力欄に表示する
        (Name を選んだとき、Enter を押したとき、フォーカスが外れたとき)
        """
        name = self.name.get().strip()
        if name in webhook_names(self.setting):
            self.showValues(name)

    def save(self) -> None:
        """
        Save ボタン: 入力した内容を、名前 Name の通知先として設定ファイルに保存し、on_saved を呼ぶ
        (名前が使えない場合や、Webhook URL が空の場合は、警告を表示して保存しない)
        """
        name = self.name.get().strip()
        error = check_webhook_name(name)
        if error is None and self.vars["webhook_url"].get().strip() == "":
            error = "Webhook URL を入力してください。"
        if error is not None:
            tkmsg.showwarning(TITLE, error, parent=self.window)
            return
        # 他で書き換えられた内容を消さないよう、読み直してから書き込む
        self.setting = load_setting(self.setting_path)
        if not self.setting.has_section(RECEIVE_SECTION):
            # 新しく作るファイルは、起動時に作られるものと同じ構成にする
            self.setting[RECEIVE_SECTION] = {"channel_id": "", "token": ""}
        self.setting[name] = {key: self.vars[key].get().strip() for key, _ in FIELDS}
        save_setting(self.setting_path, self.setting)
        _logger.debug(f"Assign Discord Webhook Setting: {name}")
        print(f"Discordの通知先 [{name}] を保存しました。")
        self.refresh(name)
        if self.on_saved is not None:
            self.on_saved()

    def delete(self) -> None:
        """
        Delete ボタン: 確認のうえ、名前 Name の通知先を設定ファイルから削除し、on_saved を呼ぶ
        (既定の通知先と、登録されていない名前は削除できない)
        """
        name = self.name.get().strip()
        if name == DEFAULT_WEBHOOK:
            tkmsg.showwarning(TITLE, f"{DEFAULT_WEBHOOK} は削除できません。", parent=self.window)
            return
        self.setting = load_setting(self.setting_path)
        if name not in webhook_names(self.setting):
            tkmsg.showwarning(TITLE, f"通知先「{name}」は登録されていません。", parent=self.window)
            return
        if not tkmsg.askyesno(TITLE, f"通知先「{name}」を削除しますか？", parent=self.window):
            return
        self.setting.remove_section(name)
        save_setting(self.setting_path, self.setting)
        _logger.debug(f"Delete Discord Webhook Setting: {name}")
        print(f"Discordの通知先 [{name}] を削除しました。")
        self.refresh(next_webhook_name(webhook_names(self.setting)))
        if self.on_saved is not None:
            self.on_saved()

    def isOpen(self) -> bool:
        """ウィンドウが開いているか(閉じた後は False)"""
        try:
            return bool(self.window.winfo_exists())
        except tk.TclError:
            return False

    def lift(self) -> None:
        """ウィンドウを手前に出して、フォーカスを移す(最小化している場合は元に戻す)"""
        self.window.deiconify()
        self.window.lift()
        self.window.focus_set()

    def destroy(self) -> None:
        """ウィンドウを閉じる(Close ボタン、Esc)"""
        self.window.destroy()
