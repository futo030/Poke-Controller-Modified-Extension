#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
コントローラー設定のウィンドウ(メニューバーの 設定 > コントローラーの色...)

Software-Controller / Controller Simulator の本体の色を、コントローラーの種類ごとに設定する。
種類ごとのタブに、プレビュー・色の指定(Custom)・事前に用意した色と書き出した自分の色の一覧(Preset)を置く。
"""
from __future__ import annotations

import os
import tkinter as tk
import tkinter.colorchooser as tkcolor
import tkinter.filedialog as tkfiledialog
import tkinter.messagebox as tkmsg
import tkinter.ttk as ttk
from logging import getLogger, DEBUG, NullHandler
from typing import Callable, Literal

import ControllerColors
import Theme
from ControllerLayouts import (
    Compact3DSGUI,
    CompactDSGUI,
    CompactGameCubeGUI,
    CompactSwitchJoyConGUI,
    CompactSwitchProGUI,
)

# プレビューに使うレイアウト
PREVIEW_LAYOUTS = {
    ControllerColors.SWITCH_JOYCON: CompactSwitchJoyConGUI,
    ControllerColors.SWITCH_PRO: CompactSwitchProGUI,
    ControllerColors.N3DS: Compact3DSGUI,
    ControllerColors.NDS: CompactDSGUI,
    ControllerColors.GAMECUBE: CompactGameCubeGUI,
}
# Presetの一覧の大きさ(入りきらない分はスクロールする)
PRESET_LIST_WIDTH = 250
PRESET_LIST_HEIGHT = 300


class _NullKey:
    """
    プレビュー用: 押しても何も送らない入力
    """

    def __getattr__(self, name: str) -> Callable[..., None]:
        """
        どの名前のメソッドを呼ばれても、何もしない関数を返す
        """
        return lambda *args, **kwargs: None


class _ControllerColorTab:
    """
    1つの種類のタブ(プレビュー / Custom / Preset)
    """

    def __init__(self, window: ControllerColorWindow, parent: tk.Misc, controller_type: str, colors: dict[str, str]):
        """
        window: このタブを持つウィンドウ
        parent: タブを置く Notebook
        controller_type: コントローラーの種類(ControllerColors.CONTROLLER_TYPES のキー)
        colors: 開いたときの色(色の項目 -> "#RRGGBB")
        """
        self.window = window
        self.controller_type = controller_type
        self.colors = dict(colors)
        self.frame = ttk.Frame(parent, padding=8)
        self.preview_panel = None
        self.preset_tiles = []

        self.preview_f = tk.Frame(self.frame)
        self.preview_f.grid(row=0, column=0, sticky="nw")

        # Custom: 色ごとに、色見本・#RRGGBB の入力・色を選ぶ画面
        custom_lf = ttk.Labelframe(self.frame, text="Custom")
        self.swatches = {}
        self.entries = {}
        for row, (key, label) in enumerate(ControllerColors.CONTROLLER_TYPES[controller_type]["keys"]):
            ttk.Label(custom_lf, text=f"{label}:").grid(row=row, column=0, sticky="w", padx=(8, 4), pady=3)
            swatch = tk.Label(custom_lf, width=3, relief="solid", borderwidth=1)
            swatch.theme_exclude = True
            swatch.grid(row=row, column=1, padx=4, pady=3)
            var = tk.StringVar()
            entry = ttk.Entry(custom_lf, textvariable=var, width=9)
            entry.grid(row=row, column=2, padx=4, pady=3)
            entry.bind("<Return>", lambda event, key=key: self._onEntry(key))
            entry.bind("<FocusOut>", lambda event, key=key: self._onEntry(key))
            ttk.Button(custom_lf, text="Choose...", width=9, command=lambda key=key: self._choose(key)).grid(
                row=row, column=3, padx=(4, 8), pady=3
            )
            self.swatches[key] = swatch
            self.entries[key] = var
        custom_lf.grid(row=1, column=0, sticky="new", pady=(8, 0))

        # Preset: 事前に用意した色と、書き出した自分の色。入りきらない分はスクロールする
        preset_lf = ttk.Labelframe(self.frame, text="Preset")
        self.preset_canvas = tk.Canvas(
            preset_lf, width=PRESET_LIST_WIDTH, height=PRESET_LIST_HEIGHT, highlightthickness=0
        )
        self.preset_sb = ttk.Scrollbar(preset_lf, orient="vertical", command=self.preset_canvas.yview)
        self.preset_canvas.configure(yscrollcommand=self.preset_sb.set)
        self.preset_inner = ttk.Frame(self.preset_canvas)
        self.preset_canvas.create_window(0, 0, anchor="nw", window=self.preset_inner)
        self.preset_canvas.pack(side="left", fill="both", expand=True, padx=(4, 0), pady=4)
        self.preset_sb.pack(side="right", fill="y", pady=4)
        preset_lf.grid(row=0, column=1, rowspan=2, sticky="ns", padx=(10, 0))
        for widget in (self.preset_canvas, self.preset_inner):
            widget.bind("<MouseWheel>", self._onMouseWheel)

        self.refreshPresets()
        self.refresh()

    # ---------- 表示 ----------
    def refresh(self) -> None:
        """
        今の色を、プレビュー・色見本・入力欄・Presetの選択の表示に反映する
        """
        for key, color in self.colors.items():
            self.swatches[key].configure(bg=color)
            self.entries[key].set(color)
        if self.preview_panel is not None:
            self.preview_panel.destroy()
        for child in self.preview_f.winfo_children():
            child.destroy()
        self.preview_panel = PREVIEW_LAYOUTS[self.controller_type](
            self.window.root, None, parent=self.preview_f, key=_NullKey(), colors=self.colors
        )
        for tile, colors in self.preset_tiles:
            selected = colors == self.colors
            tile.configure(highlightbackground=Theme.color("strong_border") if selected else Theme.color("tile_border"),
                           highlightthickness=2 if selected else 1)  # fmt: skip

    def refreshPresets(self) -> None:
        """
        Presetの一覧を作り直す(事前に用意した色、続いて書き出した自分の色)
        """
        for child in self.preset_inner.winfo_children():
            child.destroy()
        self.preset_tiles = []
        presets = [(name, dict(colors)) for name, colors in ControllerColors.CONTROLLER_TYPES[self.controller_type]["presets"]]
        user_presets = ControllerColors.list_user_presets(self.controller_type)
        row = 0
        for index, (name, colors) in enumerate(presets + user_presets):
            if index == len(presets):
                ttk.Separator(self.preset_inner, orient="horizontal").grid(
                    row=row, column=0, columnspan=2, sticky="ew", padx=4, pady=4
                )
                row += 1
            tile = tk.Frame(self.preset_inner, highlightbackground=Theme.color("tile_border"), highlightthickness=1, cursor="hand2")
            for key in ControllerColors.color_keys(self.controller_type):
                color_label = tk.Label(tile, bg=colors[key], width=6 // len(colors))
                # コントローラーの色は、テーマを変えても変えない
                color_label.theme_exclude = True
                color_label.pack(side="left")
            tile.grid(row=row, column=0, padx=(4, 6), pady=2)
            label = ttk.Label(self.preset_inner, text=name, cursor="hand2")
            label.grid(row=row, column=1, sticky="w", padx=(0, 6))
            for widget in (tile, label, *tile.winfo_children()):
                widget.bind("<Button-1>", lambda event, colors=colors: self.setColors(colors))
                widget.bind("<MouseWheel>", self._onMouseWheel)
            self.preset_tiles.append((tile, colors))
            row += 1
        self.preset_inner.update_idletasks()
        self.preset_canvas.configure(scrollregion=(0, 0, 0, self.preset_inner.winfo_reqheight()))

    def showSelectedPreset(self) -> None:
        """
        選択中のPresetが見える位置までスクロールする
        """
        self.preset_inner.update_idletasks()
        height = self.preset_inner.winfo_reqheight()
        for tile, colors in self.preset_tiles:
            if colors == self.colors and height > PRESET_LIST_HEIGHT:
                self.preset_canvas.yview_moveto(max(tile.winfo_y() - PRESET_LIST_HEIGHT / 2, 0) / height)
                return

    def _onMouseWheel(self, event: tk.Event) -> Literal["break"]:
        """Presetの一覧の上でマウスホイールを回したとき: 入りきらない場合にスクロールする(ほかの部品には伝えない)"""
        if self.preset_inner.winfo_reqheight() > PRESET_LIST_HEIGHT:
            self.preset_canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
        return "break"

    # ---------- 色の変更 ----------
    def setColors(self, colors: dict[str, str]) -> None:
        """
        このタブの色を変え、表示に反映する(Presetを選んだとき、色を入力・選択したとき、Reset・Load)
        colors: 色の項目 -> 色(足りない色・読めない色は初期値にする)
        """
        self.colors = ControllerColors.complete_colors(self.controller_type, colors)
        self.refresh()

    def _onEntry(self, key: str) -> None:
        """色の入力欄で Enter を押したとき、フォーカスが外れたとき: 入力した色にする(色として読めない場合は元に戻す)。key: 色の項目"""
        color = ControllerColors.normalize_color(self.entries[key].get())
        if color is None:
            # 色として読めない場合は元に戻す
            self.entries[key].set(self.colors[key])
        elif color != self.colors[key]:
            self.setColors({**self.colors, key: color})
        else:
            self.entries[key].set(color)

    def _choose(self, key: str) -> None:
        """Choose... ボタン: 色を選ぶ画面を開き、選んだ色にする。key: 色の項目"""
        _, color = tkcolor.askcolor(color=self.colors[key], parent=self.window.window, title="Color")
        if color is not None:
            self.setColors({**self.colors, key: color})


class ControllerColorWindow:
    """
    コントローラー設定のウィンドウ(種類ごとのタブと、Load / Save / Reset / OK / Cancel のボタン)
    """

    def __init__(self, root: tk.Tk, on_apply: Callable[[dict], None], initial_type: str | None = None):
        """
        root: メインウィンドウ(この位置を基準に表示する)
        on_apply: OKを押したときに呼ぶ関数(種類 -> 色 の辞書を渡す)
        initial_type: 最初に表示するタブの種類
        """
        self._logger = getLogger(__name__)
        self._logger.addHandler(NullHandler())
        self._logger.setLevel(DEBUG)
        self._logger.propagate = True

        self.root = root
        self.on_apply = on_apply
        self.window = tk.Toplevel(root)
        self.window.title("コントローラー設定")
        self.window.resizable(False, False)
        root_geometry = root.geometry().split("+")
        self.window.geometry("%+d%+d" % (100 + int(root_geometry[1]), 60 + int(root_geometry[2])))

        body = ttk.Frame(self.window, padding=10)
        body.pack(fill="both", expand=True)
        self.nb = ttk.Notebook(body)
        self.tabs = {}
        for controller_type in ControllerColors.CONTROLLER_TYPES:
            tab = _ControllerColorTab(self, self.nb, controller_type, ControllerColors.get_colors(controller_type))
            self.nb.add(tab.frame, text=controller_type)
            self.tabs[controller_type] = tab
        self.nb.pack(fill="both", expand=True)
        if initial_type in self.tabs:
            self.nb.select(self.tabs[initial_type].frame)

        buttons = ttk.Frame(body)
        buttons.pack(fill="x", pady=(10, 0))
        ttk.Button(buttons, text="Load...", width=9, command=self.load).pack(side="left")
        ttk.Button(buttons, text="Save...", width=9, command=self.save).pack(side="left", padx=4)
        ttk.Button(buttons, text="Reset", width=9, command=self.reset).pack(side="left")
        ttk.Button(buttons, text="Cancel", width=9, command=self.destroy).pack(side="right")
        ttk.Button(buttons, text="OK", width=9, command=self.ok).pack(side="right", padx=4)
        self.window.bind("<Escape>", lambda event: self.destroy())
        self.window.update_idletasks()
        for tab in self.tabs.values():
            tab.showSelectedPreset()
        self._logger.debug("Create controller color window")

    def currentTab(self) -> _ControllerColorTab:
        """表示中のタブを返す"""
        selected = self.nb.select()
        return next(tab for tab in self.tabs.values() if str(tab.frame) == selected)

    def reset(self) -> None:
        """
        Reset: 表示中の種類の色を、初期値に戻す
        """
        tab = self.currentTab()
        tab.setColors(ControllerColors.default_colors(tab.controller_type))
        tab.showSelectedPreset()

    def save(self) -> None:
        """
        Save...: 表示中の種類の色を、名前を付けてファイルに書き出す(Presetの一覧にも並ぶ)
        """
        tab = self.currentTab()
        os.makedirs(ControllerColors.USER_PRESET_DIR, exist_ok=True)
        path = tkfiledialog.asksaveasfilename(
            parent=self.window,
            title=f"Save ({tab.controller_type})",
            initialdir=ControllerColors.USER_PRESET_DIR,
            defaultextension=".json",
            filetypes=[("Controller Color", "*.json")],
        )
        if not path:
            return
        try:
            ControllerColors.save_preset_file(path, tab.controller_type, tab.colors)
        except OSError as e:
            self._logger.error(f"Failed to save controller colors: {e}")
            tkmsg.showerror("Save", f"書き出せませんでした。\n{e}", parent=self.window)
            return
        tab.refreshPresets()
        tab.refresh()
        tab.showSelectedPreset()

    def load(self) -> None:
        """
        Load...: ファイルから色を読み込む(表示中の種類と違う種類のファイルは読み込まない)
        """
        tab = self.currentTab()
        os.makedirs(ControllerColors.USER_PRESET_DIR, exist_ok=True)
        path = tkfiledialog.askopenfilename(
            parent=self.window,
            title=f"Load ({tab.controller_type})",
            initialdir=ControllerColors.USER_PRESET_DIR,
            filetypes=[("Controller Color", "*.json")],
        )
        if not path:
            return
        try:
            controller_type, colors = ControllerColors.load_preset_file(path)
        except (OSError, ValueError) as e:
            self._logger.error(f"Failed to load controller colors: {e}")
            tkmsg.showerror("Load", f"読み込めませんでした。\n{e}", parent=self.window)
            return
        if controller_type != tab.controller_type:
            tkmsg.showwarning(
                "Load",
                f"このファイルは「{controller_type}」の色です。\n「{tab.controller_type}」には読み込めません。",
                parent=self.window,
            )
            return
        tab.setColors(colors)
        tab.showSelectedPreset()

    def ok(self) -> None:
        """OK: すべての種類の色を on_apply に渡して、ウィンドウを閉じる"""
        self.on_apply({controller_type: dict(tab.colors) for controller_type, tab in self.tabs.items()})
        self.destroy()

    def focus_force(self) -> None:
        """ウィンドウを手前に出して、フォーカスを移す"""
        self.window.lift()
        self.window.focus_force()

    def protocol(self, event: str, func: Callable[[], None]) -> None:
        """
        ウィンドウの操作("WM_DELETE_WINDOW" など)に、呼ぶ関数を結び付ける
        event: 操作の名前
        func: 呼ぶ関数
        """
        self.window.protocol(event, func)

    def destroy(self) -> None:
        """ウィンドウを閉じる(Cancel、Esc、OK の後。プレビューのコントローラーも片付ける。2回呼んでも何もしない)"""
        if self.window is None:
            return
        for tab in self.tabs.values():
            if tab.preview_panel is not None:
                tab.preview_panel.destroy()
                tab.preview_panel = None
        window, self.window = self.window, None
        window.destroy()
        self._logger.debug("Controller color window destroyed")
