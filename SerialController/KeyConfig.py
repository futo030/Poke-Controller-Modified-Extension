#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import configparser
import os
import tkinter as tk
import tkinter.messagebox as tkmsg
import tkinter.ttk as ttk
from logging import getLogger, DEBUG, NullHandler
from typing import TYPE_CHECKING, Callable

from pynput.keyboard import Listener

import ControllerColors
import KeyMap
import Profile
import Theme
from ControllerLayouts import Compact3DSGUI, CompactDSGUI, CompactGameCubeGUI, CompactSwitchJoyConGUI

if TYPE_CHECKING:
    from pynput.keyboard import Key, KeyCode

LABEL_FONT = ("Yu Gothic UI", 9, "bold")
# ゲーム機ごとの、図に使うレイアウトと、色(コントローラー設定)の種類。SwitchはJoy-Conの色を使う
CONSOLE_LAYOUTS = {
    KeyMap.SWITCH: (CompactSwitchJoyConGUI, ControllerColors.SWITCH_JOYCON),
    KeyMap.N3DS: (Compact3DSGUI, ControllerColors.N3DS),
    KeyMap.NDS: (CompactDSGUI, ControllerColors.NDS),
    KeyMap.GAMECUBE: (CompactGameCubeGUI, ControllerColors.GAMECUBE),
}


def _addKeyConfigStyleHook() -> None:
    """
    この画面のフレームだけを、テーマの入力欄の色(デフォルトでは白)にするスタイルを作る(最初に開いたときに1回登録する)
    ("TFrame" そのものを変えると、メイン画面を含むすべてのフレームの背景が変わる)
    """
    global _style_hook_added
    if not _style_hook_added:
        _style_hook_added = True
        Theme.add_style_hook(lambda style: style.configure("KeyConfig.TFrame", background=Theme.color("field")))


_style_hook_added = False


class _NullKey:
    """
    図のコントローラー用: 押しても何も送らない入力
    """

    def __getattr__(self, name: str) -> Callable[..., None]:
        """
        どの名前のメソッドを呼ばれても、何もしない関数を返す
        """
        return lambda *args, **kwargs: None


class PokeKeycon:
    """
    キーコンフィグの画面: キーボードのキーとコントローラーのボタンの対応を、ゲーム機ごとに設定する
    入力欄を選んでキーを押すと、そのキーが欄に入る。OKで保存し、キャンセルでは何も変えない
    """

    SETTING_PATH = os.path.join(os.path.dirname(__file__), "profiles", "default", "settings.ini")

    def __init__(
        self,
        master: tk.Misc | None = None,
        initial_console: str | None = None,
        on_saved: Callable[[], None] | None = None,
        **kw: object,
    ):
        """
        master: 親のウィンドウ(メインウィンドウ)
        initial_console: 最初に表示するタブのゲーム機
        on_saved: OKで設定を保存した後に呼ぶ関数(キーボード操作に、新しい対応をすぐ使わせるため)
        kw: 使っていない(以前の呼び出し方との互換のために受け取る)
        """
        self.master = master
        self.on_saved = on_saved
        self.kc = tk.Toplevel(master)
        self.kc.title("Key Config")
        self.listener = None
        self._close_handler = None
        self.setting = configparser.ConfigParser()
        self.setting.optionxform = str

        self._logger = getLogger(__name__)
        self._logger.addHandler(NullHandler())
        self._logger.setLevel(DEBUG)
        self._logger.propagate = True

        self.kc.resizable(False, False)

        # Initialize style
        # この画面のフレームだけを、テーマの入力欄の色(デフォルトでは白)にする
        _addKeyConfigStyleHook()

        # build ui
        self.key_config_frame = ttk.Frame(self.kc, style="KeyConfig.TFrame")
        # ゲーム機ごとのタブ。vars: ゲーム機 -> {ボタンの名前: 入力欄の変数}
        self.nb = ttk.Notebook(self.key_config_frame)
        self.vars = {}
        self.entries = {}
        self.tab_frames = {}
        self.previews = []
        for console in KeyMap.CONSOLES:
            tab = ttk.Frame(self.nb, style="KeyConfig.TFrame")
            # 上: コントローラーの図(コントローラー設定の色。HOLDボタンは置かない。押しても何も送らない)
            layout_class, color_type = CONSOLE_LAYOUTS[console]
            colors = ControllerColors.get_colors(color_type)
            preview_f = tk.Frame(tab)
            self.previews.append(
                layout_class(self.kc, None, parent=preview_f, key=_NullKey(), colors=colors, hold_button=False)
            )
            preview_f.grid(column="0", row="0", padx="8", pady=(8, 6))
            # 下: 白い背景の表。左の列と右の列を、項目の左の印の色(本体の色)で示す
            table = tk.Frame(tab, bg=Theme.color("field"))
            self.vars[console] = {}
            side_colors = (colors["left"], colors["right"]) if "left" in colors else (colors["body"],) * 2
            for side, (buttons, color) in enumerate(zip(KeyMap.BUTTONS[console], side_colors)):
                for row, (text, name) in enumerate(buttons):
                    cell = tk.Frame(table, bg=Theme.color("field"))
                    tk.Label(cell, bg=color, width=1).pack(side="left", fill="y", padx=(0, 5))
                    tk.Label(cell, text=text, bg=Theme.color("field"), font=LABEL_FONT, width=10, anchor="w").pack(side="left")
                    cell.grid(column=side * 2, row=row, padx=(14 if side else 0, 6), pady="2", sticky="w")
                    var = tk.StringVar()
                    entry = ttk.Entry(table, width="12")
                    entry.configure(state="readonly", textvariable=var)
                    entry.grid(column=side * 2 + 1, row=row, pady="2")
                    entry.bind("<FocusIn>", lambda event, var=var: self.onFocusInController(var))
                    entry.bind("<FocusOut>", self.onFocusOutController)
                    self.vars[console][name] = var
                    self.entries[(console, name)] = entry
            table.grid(column="0", row="1", padx="10", pady=(0, 8), sticky="n")
            self.nb.add(tab, text=console)
            self.tab_frames[console] = tab
        self.nb.grid(column="0", row="0", sticky="nsew")
        if initial_console in self.tab_frames:
            self.nb.select(self.tab_frames[initial_console])

        self.frame_button = ttk.Frame(self.key_config_frame, style="KeyConfig.TFrame")
        self.ok_button = ttk.Button(self.frame_button)
        self.ok_button.configure(text="OK", command=self.ok)
        self.ok_button.grid(column="0", padx=(10, 5), pady="5", row="0", sticky="e")
        self.cancel_button = ttk.Button(self.frame_button)
        self.cancel_button.configure(text="キャンセル", command=self.cancel)
        self.cancel_button.grid(column="1", padx=(0, 10), pady="5", row="0", sticky="e")
        self.frame_button.grid(column="0", row="1", sticky="e")

        self.key_config_frame.pack(side="top")

        # Main widget
        self.mainwindow = self.key_config_frame

        self.load_config()

    def run(self) -> None:
        """このファイルを直接実行したとき用: 画面を表示して、閉じるまで待つ"""
        self.mainwindow.mainloop()

    def onFocusInController(self, var: tk.StringVar) -> None:
        """
        入力欄を選んだとき: キーの受け付けを始め、押したキーをその欄に入れる
        var: 選んだ入力欄の変数
        """
        # 入力欄を選んでいる間、押したキーをその欄に入れる
        self._stop_listener()
        self.listener = Listener(on_press=lambda key: self.on_press(key, var=var))
        self.listener.start()
        self._logger.debug("Activate key config window")

    def onFocusOutController(self, event: tk.Event) -> None:
        """入力欄からフォーカスが外れたとき: キーの受け付けをやめる"""
        self._stop_listener()

    def _stop_listener(self) -> None:
        """キーの受け付けをやめる(受け付けていない場合は何もしない)"""
        if self.listener is not None:
            self.listener.stop()
            self.listener = None

    def on_press(self, key: Key | KeyCode | None, var: tk.StringVar) -> None:
        """
        キーを押したとき(pynput のスレッドから呼ばれる): そのキーを入力欄に入れる
        key: 押したキー(文字のキーはその文字、それ以外は Key.space のような名前で入れる。名前の付いていないキーは入れない)
        var: 入れる先の入力欄の変数
        """
        char = getattr(key, "char", None)
        text = char if char else str(key)
        if text.startswith("<"):
            # 名前の付いていないキー(保存しても読み込めない)は使わない
            return
        var.set(text)

    def load_config(self) -> None:
        """設定ファイルから、ゲーム機ごとのキーの対応を読み込んで、入力欄に表示する(保存されていないボタンは初期値)"""
        if os.path.isfile(self.SETTING_PATH):
            self.setting.read(self.SETTING_PATH, encoding="utf-8")
        for console in KeyMap.CONSOLES:
            for name, value in KeyMap.load_keymap(self.setting, console).items():
                self.vars[console][name].set(value)

    def find_duplicates(self) -> list[str]:
        """
        同じゲーム機の中で、同じキーを複数のボタンに割り当てているものを、メッセージのリストで返す
        """
        messages = []
        for console in KeyMap.CONSOLES:
            left, right = KeyMap.BUTTONS[console]
            used = {}
            for text, name in (*left, *right):
                used.setdefault(self.vars[console][name].get(), []).append(text)
            for value, texts in used.items():
                if len(texts) > 1:
                    messages.append(f"{console}: キー「{value}」 → {' / '.join(texts)}")
        return messages

    def save_config(self) -> bool:
        """
        入力欄の内容を設定ファイルに保存する。同じキーを複数のボタンに割り当てている場合は、警告して保存しない
        保存した(または保存しないモードの)場合はTrueを返す
        """
        duplicates = self.find_duplicates()
        if duplicates:
            tkmsg.showwarning(
                "Key Config",
                "同じキーが複数のボタンに割り当てられています。設定は適用されません。\n\n" + "\n".join(duplicates),
                parent=self.kc,
            )
            return False
        if Profile.is_read_only():
            # 同じプロファイルで2つ目以降に起動した場合は、ファイルには保存せず、このウィンドウの間だけ使う
            for console in KeyMap.CONSOLES:
                KeyMap.set_session_keymap(console, {name: var.get() for name, var in self.vars[console].items()})
            tkmsg.showinfo(
                "Key Config",
                "このウィンドウは設定を保存しないモードのため、変更はこのウィンドウを閉じるまでの間だけ使われます。",
                parent=self.kc,
            )
            return True
        # 他の設定を古い内容で上書きしないよう、ファイルを読み直してから、キーの対応だけを書き換える
        setting = configparser.ConfigParser()
        setting.optionxform = str
        if os.path.isfile(self.SETTING_PATH):
            setting.read(self.SETTING_PATH, encoding="utf-8")
        for console in KeyMap.CONSOLES:
            KeyMap.store_keymap(setting, console, {name: var.get() for name, var in self.vars[console].items()})
        with open(self.SETTING_PATH, "w", encoding="utf-8") as file:
            self._logger.debug("Apply key setting")
            setting.write(file)
        self.setting = setting
        return True

    def ok(self) -> None:
        """
        OK: 保存して閉じる(同じキーがある場合は閉じない)
        """
        self._stop_listener()
        if self.save_config():
            if self.on_saved is not None:
                self.on_saved()
            self._close()

    def cancel(self) -> None:
        """
        キャンセル: 何も変えずに閉じる
        """
        self._close()

    def _close(self) -> None:
        """ウィンドウを閉じる(OK、キャンセル)。× ボタン用の関数が登録されていれば、それを呼ぶ"""
        # ×ボタンと同じ閉じ方をする(開いた側が、開いていない状態に戻せるように)
        if self._close_handler is not None:
            self._close_handler()
        else:
            self.destroy()

    def close(self) -> None:
        """ウィンドウを隠し、キーの受け付けをやめる(ウィンドウは破棄しない)"""
        self.kc.withdraw()
        self._stop_listener()

    def bind(self, event: str, func: Callable[[tk.Event], object]) -> None:
        """
        ウィンドウのイベントに、呼ぶ関数を結び付ける
        event: イベントの名前
        func: 呼ぶ関数(イベントを受け取る)
        """
        self.kc.bind(event, func)

    def protocol(self, event: str, func: Callable[[], None]) -> None:
        """
        ウィンドウの操作に、呼ぶ関数を結び付ける
        ("WM_DELETE_WINDOW" の関数は覚えておき、OK やキャンセルで閉じるときにも、× ボタンと同じ関数を呼ぶ)
        event: 操作の名前
        func: 呼ぶ関数
        """
        if event == "WM_DELETE_WINDOW":
            self._close_handler = func
        self.kc.protocol(event, func)

    def focus_force(self) -> None:
        """ウィンドウにフォーカスを移す(隠している場合は表示する)"""
        self.kc.focus_force()
        self.kc.deiconify()

    def destroy(self) -> None:
        """キーの受け付けをやめ、図のコントローラーを片付けて、ウィンドウを破棄する"""
        self._stop_listener()
        for preview in self.previews:
            preview.destroy()
        self.previews = []
        self.kc.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = PokeKeycon(root)
    app.run()
