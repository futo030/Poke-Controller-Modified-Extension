#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
テーマ(配色)を作る・編集するウィンドウ(メニューの 表示 > テーマ > テーマを作る / 編集する...)

役割(背景、入力欄、文字など)ごとに色を選ぶ。選んでいる間は、本体の色を一時的に変えて、見た目を確かめられる
(保存せずに閉じると、元のテーマに戻る)。保存すると、themes フォルダーにファイル(*.json)を書き、そのテーマに切り替える。
ファイルの形と、読み書きは Theme.py。
"""
from __future__ import annotations

import tkinter as tk
import tkinter.colorchooser as colorchooser
import tkinter.ttk as ttk
from logging import getLogger, DEBUG, NullHandler
from tkinter import messagebox
from typing import Callable

import Theme

_logger = getLogger(__name__)
_logger.addHandler(NullHandler())
_logger.setLevel(DEBUG)
_logger.propagate = True

TITLE = "テーマを作る / 編集する"
NEW_THEME = "(新しいテーマ)"
# 役割の説明(Theme.USER_THEME_ROLES の順)
ROLE_LABELS = {
    "bg": "背景",
    "surface": "少し浮いた部分(タブの見出し・メニューバー)",
    "field": "入力欄・出力画面の背景",
    "border": "枠線",
    "fg": "文字",
    "muted": "薄い文字(使えない項目・Log の DEBUG)",
    "accent": "強調(チェック・フォーカス)",
    "select": "選んでいる所の背景",
    "select_fg": "選んでいる所の文字",
    "check_fg": "チェックの印",
    "button": "ボタン",
    "button_active": "マウスを重ねたボタン",
    "sash": "仕切り線",
    "link": "リンクの文字",
    "code": "Instruction Manual のコードの背景",
    "danger": "赤(記録中の表示・Log の ERROR)",
}
# 色を打ち込んでから、本体に反映するまでの待ち時間(ms)
PREVIEW_DELAY_MS = 200
SWATCH_WIDTH = 4


class ThemeEditorWindow:
    """テーマを作る・編集するウィンドウ"""

    def __init__(
        self,
        root: tk.Tk,
        on_preview: Callable[[dict | None], None],
        on_saved: Callable[[str], None],
        on_deleted: Callable[[], None],
    ):
        """
        root: メインウィンドウ(この位置を基準に表示する)
        on_preview: 本体の色を一時的に変える関数(引数は、テーマの定義。None なら、元のテーマに戻す)
        on_saved: 保存した後に呼ぶ関数(引数は、保存したテーマの ID。メニューを作り直して、そのテーマに切り替える)
        on_deleted: テーマを削除した後に呼ぶ関数(メニューを作り直す)
        """
        self.root = root
        self.on_preview = on_preview
        self.on_saved = on_saved
        self.on_deleted = on_deleted
        self._loading = False
        self._preview_job = None
        # 編集しているテーマのファイルの名前(.json の前。新しいテーマなら None)
        self.stem: str | None = None

        self.window = tk.Toplevel(root)
        self.window.title(TITLE)
        root_geometry = root.geometry().split("+")
        self.window.geometry("%+d%+d" % (40 + int(root_geometry[1]), 40 + int(root_geometry[2])))
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.resizable(False, False)

        body = ttk.Frame(self.window, padding=10)
        body.pack(fill="both", expand=True)
        top = ttk.Frame(body)
        top.pack(fill="x")
        ttk.Label(top, text="編集するテーマ:").grid(column=0, row=0, sticky="w")
        self.target = tk.StringVar()
        self.target_cb = ttk.Combobox(top, textvariable=self.target, state="readonly", width=30)
        self.target_cb.grid(column=1, row=0, sticky="w", padx=(4, 0))
        self.target_cb.bind("<<ComboboxSelected>>", lambda event: self.loadTarget())
        self.delete_button = ttk.Button(top, text="削除", width=6, command=self.delete)
        self.delete_button.grid(column=2, row=0, padx=(8, 0))
        ttk.Label(top, text="名前:").grid(column=0, row=1, sticky="w", pady=(6, 0))
        self.name = tk.StringVar()
        self.name_entry = ttk.Entry(top, textvariable=self.name, width=32)
        self.name_entry.grid(column=1, row=1, sticky="w", padx=(4, 0), pady=(6, 0))
        ttk.Label(top, text="元にする配色:").grid(column=0, row=2, sticky="w", pady=(6, 0))
        self.base = tk.StringVar()
        self.base_cb = ttk.Combobox(top, textvariable=self.base, state="readonly", width=30)
        self.base_cb.grid(column=1, row=2, sticky="w", padx=(4, 0), pady=(6, 0))
        self.base_button = ttk.Button(top, text="この配色を読み込む", command=self.loadBase)
        self.base_button.grid(column=2, row=2, padx=(8, 0), pady=(6, 0))
        self.dark = tk.BooleanVar()
        ttk.Checkbutton(top, text="暗い配色(タイトルバーも暗くする)", variable=self.dark, command=self._changed).grid(
            column=1, columnspan=2, row=3, sticky="w", padx=(4, 0), pady=(6, 0)
        )

        # 役割ごとの色(2 列に並べる)
        colors_f = ttk.LabelFrame(body, text="色(四角を押して選ぶか、#rrggbb を入力)", padding=(8, 6))
        colors_f.pack(fill="x", pady=(10, 0))
        self.colors: dict = {}
        self.swatches: dict = {}
        roles = Theme.USER_THEME_ROLES
        half = (len(roles) + 1) // 2
        for index, role in enumerate(roles):
            column, row = (index // half) * 4, index % half
            ttk.Label(colors_f, text=ROLE_LABELS.get(role, role)).grid(column=column, row=row, sticky="w", pady=2)
            swatch = tk.Label(colors_f, width=SWATCH_WIDTH, relief="solid", borderwidth=1, cursor="hand2")
            # (色の見本は、テーマの色の置き換えの対象にしない)
            swatch.theme_exclude = True
            swatch.grid(column=column + 1, row=row, padx=(8, 4), pady=2)
            swatch.bind("<Button-1>", lambda event, role=role: self.chooseColor(role))
            variable = tk.StringVar()
            entry = ttk.Entry(colors_f, textvariable=variable, width=9)
            entry.grid(column=column + 2, row=row, pady=2, padx=(0, 24 if column == 0 else 0))
            variable.trace_add("write", lambda *args, role=role: self._onColorTyped(role))
            self.colors[role] = variable
            self.swatches[role] = swatch

        self.preview = tk.BooleanVar(value=True)
        ttk.Checkbutton(body, text="選んでいる色を、本体の画面で試す(保存せずに閉じると、元のテーマに戻ります)",
                        variable=self.preview, command=self._togglePreview).pack(anchor="w", pady=(10, 0))
        bottom = ttk.Frame(body)
        bottom.pack(fill="x", pady=(8, 0))
        self.message = tk.StringVar()
        ttk.Label(bottom, textvariable=self.message, wraplength=420, justify="left").pack(side="left")
        ttk.Button(bottom, text="閉じる", width=9, command=self.close).pack(side="right")
        self.save_button = ttk.Button(bottom, text="保存", width=9, command=self.save)
        self.save_button.pack(side="right", padx=4)

        self.refreshTargets()
        self.loadTarget()
        _logger.debug("Create theme editor window")

    # ---------------------------------------------------------------- 一覧

    def _baseChoices(self) -> dict:
        """元にする配色の選択肢: 表示する名前 -> テーマの ID(デフォルトは、色が Windows の設定で決まるので、出さない)"""
        return {
            Theme.theme_name(theme_id): theme_id for theme_id in Theme.theme_ids() if theme_id != Theme.DEFAULT_THEME
        }

    def refreshTargets(self, select: str | None = None) -> None:
        """
        編集するテーマと、元にする配色の選択肢を、今あるテーマに合わせる。
        select: 選ぶテーマのファイルの名前(None なら、新しいテーマ)
        """
        self._targets = {NEW_THEME: None}
        for theme_id in Theme.user_theme_ids():
            stem = theme_id[len(Theme.USER_THEME_PREFIX):]
            self._targets[f"{Theme.theme_name(theme_id)} ({stem}.json)"] = stem
        self.target_cb.configure(values=list(self._targets))
        label = next((label for label, stem in self._targets.items() if stem == select and stem is not None), NEW_THEME)
        self.target.set(label)
        choices = self._baseChoices()
        self.base_cb.configure(values=list(choices))
        # 初めは、今のテーマ。デフォルトのテーマ(色が Windows の設定で決まる)のときは、それに近い、白基調のテーマ
        origin = Theme.saved_theme_id()
        if origin not in choices.values():
            origin = Theme.TEMPLATE_BASE_THEME
        current = next((label for label, theme_id in choices.items() if theme_id == origin), None)
        self.base.set(current or next(iter(choices), ""))

    def loadTarget(self) -> None:
        """編集するテーマを選んだとき: そのテーマの名前と色を、欄に入れる(新しいテーマなら、元にする配色の色)"""
        self.stem = self._targets.get(self.target.get())
        if self.stem is None:
            self.name.set(self._newName())
            self.delete_button.state(["disabled"])
            self.loadBase()
        else:
            theme = Theme.THEMES[Theme.USER_THEME_PREFIX + self.stem]
            self.name.set(theme["name"])
            self.delete_button.state(["!disabled"])
            self._setColors(theme)
        self.message.set("")

    def _newName(self) -> str:
        """新しいテーマの、初めの名前(ほかのテーマと重ならないもの)"""
        names = {Theme.theme_name(theme_id) for theme_id in Theme.theme_ids()}
        name, number = "My Theme", 1
        while name in names:
            number += 1
            name = f"My Theme {number}"
        return name

    def loadBase(self) -> None:
        """この配色を読み込む: 元にする配色の色を、欄に入れる(名前は変えない)"""
        theme_id = self._baseChoices().get(self.base.get(), Theme.TEMPLATE_BASE_THEME)
        self._setColors(Theme.THEMES[theme_id])

    def _setColors(self, theme: dict) -> None:
        """テーマの定義の色と、暗い配色かを、欄に入れる"""
        self._loading = True
        for role, variable in self.colors.items():
            variable.set(theme["colors"][role])
        self.dark.set(bool(theme["dark"]))
        self._loading = False
        self._updateSwatches()
        self._changed()

    # ---------------------------------------------------------------- 色

    def _updateSwatches(self) -> None:
        """色の見本を、欄の値に合わせる(読めない値の見本は、変えない)"""
        for role, variable in self.colors.items():
            value = variable.get().strip()
            if Theme.is_color(value):
                self.swatches[role].configure(background=value)

    def chooseColor(self, role: str) -> None:
        """色の見本を押したとき: 色を選ぶ画面を出し、選んだ色を欄に入れる"""
        current = self.colors[role].get().strip()
        chosen = colorchooser.askcolor(
            color=current if Theme.is_color(current) else None, parent=self.window, title=ROLE_LABELS.get(role, role)
        )
        if chosen and chosen[1]:
            self.colors[role].set(str(chosen[1]).lower())

    def _onColorTyped(self, role: str) -> None:
        """色の欄の値が変わったとき: 見本を合わせ、少し待ってから、本体の色に反映する"""
        if self._loading:
            return
        self._updateSwatches()
        self._changed()

    def definition(self) -> tuple[dict | None, str]:
        """欄の内容を、ファイルに書く形(name / dark / colors)にする。戻り値: (内容, 使えない理由)。使えないときは、内容は None"""
        data = {
            "name": self.name.get().strip(),
            "dark": bool(self.dark.get()),
            "colors": {role: variable.get().strip() for role, variable in self.colors.items()},
        }
        try:
            Theme.parse_user_theme(data)
        except ValueError as error:
            return None, str(error)
        return data, ""

    # ---------------------------------------------------------------- 本体で試す

    def _changed(self) -> None:
        """色や、暗い配色かが変わったとき: 少し待ってから、本体の色に反映する(続けて変わる間は、待ち直す)"""
        if self._loading:
            return
        if self._preview_job is not None:
            self.window.after_cancel(self._preview_job)
        self._preview_job = self.window.after(PREVIEW_DELAY_MS, self._applyPreview)

    def _applyPreview(self) -> None:
        """本体の色を、欄の色に一時的に変える(「本体の画面で試す」にチェックがあり、欄の値がすべて読める場合)"""
        self._preview_job = None
        if not self.preview.get():
            return
        data, error = self.definition()
        if data is None:
            # (名前が空なだけなら、色は試せる)
            data = {"name": self.name.get().strip() or "preview", "dark": bool(self.dark.get()),
                    "colors": {role: variable.get().strip() for role, variable in self.colors.items()}}
            try:
                Theme.parse_user_theme(data)
            except ValueError:
                return
        self.on_preview(Theme.parse_user_theme(data))
        self.window.lift()

    def _togglePreview(self) -> None:
        """「本体の画面で試す」を切り替えたとき: チェックを外したら、元のテーマに戻す"""
        if self.preview.get():
            self._changed()
        else:
            self.on_preview(None)
            self.window.lift()

    # ---------------------------------------------------------------- 保存・削除

    def save(self) -> None:
        """保存: themes フォルダーにファイルを書き、そのテーマに切り替える(新しいテーマは、新しいファイルに書く)"""
        data, error = self.definition()
        if data is None:
            self.message.set(error)
            return
        others = {Theme.theme_name(theme_id) for theme_id in Theme.theme_ids()
                  if theme_id != Theme.USER_THEME_PREFIX + (self.stem or "")}
        if data["name"] in others:
            self.message.set(f"「{data['name']}」という名前のテーマが、すでにあります。")
            return
        if self._preview_job is not None:
            self.window.after_cancel(self._preview_job)
            self._preview_job = None
        try:
            stem = Theme.save_user_theme(data, self.stem)
        except OSError as error:
            messagebox.showwarning(TITLE, f"テーマを保存できませんでした。\n{error}", parent=self.window)
            return
        self.on_saved(Theme.USER_THEME_PREFIX + stem)
        self.refreshTargets(select=stem)
        self.stem = stem
        self.delete_button.state(["!disabled"])
        self.message.set(f"保存しました({stem}.json)。このテーマに切り替えました。")
        self.window.lift()

    def delete(self) -> None:
        """削除: 選んでいるテーマのファイルを、確かめてから消す(使っているテーマなら、デフォルトのテーマに戻る)"""
        if self.stem is None:
            return
        name = Theme.theme_name(Theme.USER_THEME_PREFIX + self.stem)
        if not messagebox.askyesno(TITLE, f"テーマ「{name}」({self.stem}.json)を削除しますか?", parent=self.window):
            return
        try:
            Theme.delete_user_theme(self.stem)
        except OSError as error:
            messagebox.showwarning(TITLE, f"テーマを削除できませんでした。\n{error}", parent=self.window)
            return
        self.on_deleted()
        self.refreshTargets()
        self.loadTarget()
        self.message.set(f"「{name}」を削除しました。")
        self.window.lift()

    # ---------------------------------------------------------------- ウィンドウ

    def isOpen(self) -> bool:
        """ウィンドウが開いているか"""
        return bool(self.window.winfo_exists())

    def lift(self) -> None:
        """ウィンドウを前面に出す"""
        self.window.deiconify()
        self.window.lift()
        self.window.focus_force()

    def close(self) -> None:
        """閉じる: 本体の色を、元のテーマ(保存した場合は、保存したテーマ)に戻す"""
        if self._preview_job is not None:
            self.window.after_cancel(self._preview_job)
            self._preview_job = None
        self.on_preview(None)
        self.window.destroy()
        _logger.debug("Close theme editor window")
