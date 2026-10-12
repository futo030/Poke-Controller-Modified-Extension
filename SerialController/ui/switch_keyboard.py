#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Keyboard ウィンドウ(Software-Controller / Controller Simulator の Keyboard ボタンで開く)

Switch のソフトウェアキーボードと同じ並びのキーを表示し、押したキーの文字を、マイコンのキーボード機能で Switch に打つ。
「テキスト入力」のタブでは、入力した文字列を、Enter でまとめて打つ。
Switch 側の入力モード(かな / カナ / 英字)は、表示しているページや、打つ文字に合わせて、自動で切り替える(チェックで止められる)。
キーの配置と、送る文字への変換は services/switch_keyboard_layout.py、送信は services/keyboard_typer.py。
"""
from __future__ import annotations

import queue
import tkinter as tk
import tkinter.ttk as ttk
from logging import getLogger, DEBUG, NullHandler
from typing import TYPE_CHECKING

import Theme
from services import switch_keyboard_layout as layout
from services.keyboard_typer import KEY, KeyboardTyper

if TYPE_CHECKING:
    from Commands.Sender import Sender

_logger = getLogger(__name__)
_logger.addHandler(NullHandler())
_logger.setLevel(DEBUG)
_logger.propagate = True

TITLE = "Keyboard"
# Switch のソフトウェアキーボードに合わせた色(テーマを変えても、変えない)
BACKGROUND = "#2b2b2b"
KEY_COLOR = "#454545"
KEY_ACTIVE_COLOR = "#5a5a5a"
KEY_TEXT_COLOR = "#ffffff"
EMPTY_COLOR = "#222222"
DISABLED_TEXT_COLOR = "#7a7a7a"
SIDE_COLOR = "#3a3a3a"
SELECTED_TEXT_COLOR = "#2fd0ff"
OK_COLOR = "#2f6f7d"
# 欧文のフォントにする(日本語のフォントは「\」を「¥」の形で表示するため。かな・カナは、自動で日本語のフォントになる)
KEY_FONT = ("Segoe UI", 12)
SIDE_FONT = ("Segoe UI", 10)
KEY_WIDTH = 3
# 送信の結果の知らせを、画面に反映する間隔(ms)
POLL_MS = 80


class SwitchKeyboardWindow:
    """
    Keyboard ウィンドウ
    """

    def __init__(self, root: tk.Tk, ser: Sender, typer: KeyboardTyper | None = None):
        """
        root: メインウィンドウ(この位置を基準に表示する)
        ser: 送る相手
        typer: 送信の処理(None なら、作る。テスト用に、代わりのものを渡せる)
        """
        self.root = root
        self._messages = queue.Queue()
        self.typer = typer if typer is not None else KeyboardTyper(ser, on_message=lambda text, error: self._messages.put((text, error)))
        self.page = layout.PAGE_HIRAGANA
        self.small = False

        self.window = tk.Toplevel(root)
        self.window.title(TITLE)
        self.window.resizable(False, False)
        root_geometry = root.geometry().split("+")
        self.window.geometry("%+d%+d" % (120 + int(root_geometry[1]), 160 + int(root_geometry[2])))
        self.window.protocol("WM_DELETE_WINDOW", self.close)

        self.notebook = ttk.Notebook(self.window)
        self.notebook.pack(fill="both", expand=True, padx=6, pady=(6, 0))
        # Switch 側の入力モードを、ページや文字に合わせて、自動で切り替えるか
        self.auto_mode = tk.BooleanVar(value=True)
        self._buildKeysTab()
        self._buildTextTab()
        bottom = ttk.Frame(self.window, padding=(8, 4))
        bottom.pack(fill="x")
        self.auto_mode_check = ttk.Checkbutton(
            bottom, text="Switch 側の入力モード(かな / カナ / 英字)を、自動で切り替える", variable=self.auto_mode,
            command=self._onAutoModeChanged,
        )
        self.auto_mode_check.pack(anchor="w")
        self.status = tk.StringVar()
        self.status_label = ttk.Label(bottom, textvariable=self.status)
        self.status_label.pack(fill="x", pady=(2, 0))
        self.showPage(self.page, sync=False)
        self._showAvailability()
        self._poll()
        _logger.debug("Create keyboard window")

    # ---------------------------------------------------------------- キーのタブ

    def _button(self, parent: tk.Misc, text: str, command: object, color: str = KEY_COLOR, font: tuple = KEY_FONT, **options: object) -> tk.Button:
        """キーのボタンを作る(色は、Switch のキーボードに合わせた固定の色)"""
        return tk.Button(
            parent, text=text, command=command, font=font, width=KEY_WIDTH, relief="flat", borderwidth=0,
            background=color, foreground=KEY_TEXT_COLOR, activebackground=KEY_ACTIVE_COLOR,
            activeforeground=KEY_TEXT_COLOR, disabledforeground=DISABLED_TEXT_COLOR, takefocus=0, **options,
        )

    def _buildKeysTab(self) -> None:
        """キーボードのタブ(左: ページの切り替え。中央: 文字のキー。右: 消す・空白・改行・OK)を作る"""
        tab = tk.Frame(self.notebook, background=BACKGROUND, padx=6, pady=6)
        # キーボードの色は、テーマを変えても変えない
        tab.theme_exclude = True
        self.notebook.add(tab, text="キーボード")
        self.keys_tab = tab

        # 左: ページの切り替え
        side = tk.Frame(tab, background=BACKGROUND)
        side.grid(column=0, row=0, sticky="ns", padx=(0, 6))
        self.page_buttons = {}
        for row, pages in enumerate(((layout.PAGE_HIRAGANA, layout.PAGE_KATAKANA), (layout.PAGE_LOWER, layout.PAGE_UPPER))):
            for column, page in enumerate(pages):
                button = self._button(side, layout.PAGE_LABELS[page], lambda page=page: self.showPage(page), SIDE_COLOR, SIDE_FONT)
                button.grid(column=column, row=row, sticky="nsew", padx=1, pady=1)
                self.page_buttons[page] = button
        button = self._button(
            side, layout.PAGE_LABELS[layout.PAGE_SYMBOL], lambda: self.showPage(layout.PAGE_SYMBOL), SIDE_COLOR, SIDE_FONT
        )
        button.grid(column=0, columnspan=2, row=2, sticky="nsew", padx=1, pady=1)
        self.page_buttons[layout.PAGE_SYMBOL] = button
        # 小字゛゜: かな・カナのページを、濁点・半濁点・小さい字のページに切り替える
        self.small_button = self._button(side, "小字゛゜", self.toggleSmall, SIDE_COLOR, SIDE_FONT)
        self.small_button.grid(column=0, columnspan=2, row=3, sticky="nsew", padx=1, pady=1)
        # 地球のマーク: Switch 側の入力モードを、今のページに合わせ直す(Switch 側でモードを変えて、ずれたときに使う)
        self.sync_button = self._button(side, "\U0001f310", self.syncMode, SIDE_COLOR, SIDE_FONT)
        self.sync_button.grid(column=0, columnspan=2, row=4, sticky="nsew", padx=1, pady=1)
        for row in range(layout.ROWS):
            side.rowconfigure(row, weight=1, uniform="side")

        # 中央: 文字のキー
        grid = tk.Frame(tab, background=BACKGROUND)
        grid.grid(column=1, row=0)
        self.key_buttons = []
        for row in range(layout.ROWS):
            buttons = []
            for column in range(layout.COLUMNS):
                button = self._button(grid, "", lambda row=row, column=column: self.pressKey(row, column))
                button.grid(column=column, row=row, padx=1, pady=1, ipady=2)
                buttons.append(button)
            self.key_buttons.append(buttons)

        # 右: 消す・空白・改行・OK
        right = tk.Frame(tab, background=BACKGROUND)
        right.grid(column=2, row=0, sticky="ns", padx=(6, 0))
        self.backspace_button = self._button(right, "⌫", lambda: self.sendKey(KEY.BACKSPACE, "BackSpace"), SIDE_COLOR, SIDE_FONT, )
        self.backspace_button.configure(width=6)
        self.backspace_button.grid(column=0, row=0, sticky="nsew", pady=1)
        self.space_button = self._button(right, "空白", lambda: self.sendKey(KEY.SPACE, "空白"), SIDE_COLOR, SIDE_FONT)
        self.space_button.grid(column=0, row=1, sticky="nsew", pady=1)
        self.enter_button = self._button(right, "改行", lambda: self.sendKey(KEY.ENTER, "改行 (Enter)"), SIDE_COLOR, SIDE_FONT)
        self.enter_button.grid(column=0, row=2, sticky="nsew", pady=1)
        self.ok_button = self._button(right, "OK", self.sendOk, OK_COLOR, SIDE_FONT)
        self.ok_button.grid(column=0, row=3, rowspan=2, sticky="nsew", pady=1)
        for row in range(layout.ROWS):
            right.rowconfigure(row, weight=1, uniform="right")

    def showPage(self, page: str, small: bool = False, sync: bool = True) -> None:
        """
        文字のキーを、そのページの配置にする(送れない文字のキーは、押せなくする)
        page: ページ(layout.PAGE_HIRAGANA など)。small: かな・カナの、濁点・半濁点・小さい字のページにするか
        sync: Switch 側の入力モードも、このページに合わせるか(自動で切り替える設定で、送れる状態のときだけ)
        """
        changed = page != self.page
        self.page = page
        self.small = bool(small) and page in layout.KANA_PAGES
        self.rows = layout.page_rows(page, self.small)
        for row, buttons in enumerate(self.key_buttons):
            for column, button in enumerate(buttons):
                character = self.rows[row][column]
                if not character:
                    button.configure(text="", state="disabled", background=EMPTY_COLOR)
                elif layout.sendable(character):
                    button.configure(text=character, state="normal", background=KEY_COLOR)
                else:
                    button.configure(text=character, state="disabled", background=KEY_COLOR)
        for name, button in self.page_buttons.items():
            button.configure(foreground=SELECTED_TEXT_COLOR if name == page else KEY_TEXT_COLOR)
        self.small_button.configure(
            state="normal" if page in layout.KANA_PAGES else "disabled",
            foreground=SELECTED_TEXT_COLOR if self.small else KEY_TEXT_COLOR,
        )
        if sync and changed and self.auto_mode.get() and not self.typer.unavailable_reason():
            self.typer.set_mode(layout.PAGE_MODES[page])

    def toggleSmall(self) -> None:
        """小字゛゜: かな・カナのページを、濁点・半濁点・小さい字のページと切り替える"""
        self.showPage(self.page, not self.small, sync=False)

    def pressKey(self, row: int, column: int) -> None:
        """文字のキーを押したとき: その文字を打つよう頼む(かな・カナは、ローマ字で送る)"""
        character = self.rows[row][column]
        typed = layout.typed_text(character) if character else None
        if typed is None:
            return
        label = character if typed == character else f"{character} ({typed})"
        self.typer.type_text(typed, label, self._modeFor(character))

    def _modeFor(self, character: str) -> str | None:
        """
        その文字のキーを打つ前に合わせる、Switch 側の入力モード(自動で切り替えない設定なら None)。
        かな・カナのページのキーは、そのページのモード(? ! などの記号も、そのモードのまま打つ)。
        英字・記号のページのキーは、英字(「・」「〜」のように、かなのモードでしか打てない記号は、かな)
        """
        if not self.auto_mode.get():
            return None
        if self.page in layout.KANA_PAGES:
            return layout.PAGE_MODES[self.page]
        return layout.character_mode(character)

    def syncMode(self) -> None:
        """地球のマーク: Switch 側の入力モードを、今のページに合わせ直す(覚えているモードを忘れて、初めから合わせる)"""
        self.typer.forget_mode()
        self.typer.set_mode(layout.PAGE_MODES[self.page], f"入力モードを合わせ直しました: {layout.MODE_LABELS[layout.PAGE_MODES[self.page]]}")

    def _onAutoModeChanged(self) -> None:
        """自動で切り替えるチェックを変えたとき: 地球のマークを使える・使えない状態にし、説明と、送る文字の表示を合わせる"""
        self.sync_button.configure(state="normal" if self.auto_mode.get() else "disabled")
        self.typer.forget_mode()
        self._updateNote()
        self._updatePreview()

    def sendKey(self, key: int, label: str) -> None:
        """キー(消す・空白・改行、入力モードの切り替え)を 1 回押すよう頼む"""
        self.typer.type_key(key, label)

    def sendOk(self) -> None:
        """OK: コントローラーの + ボタンを短く押すよう頼む(Switch のキーボード画面の OK)"""
        self.typer.press_button()

    # ---------------------------------------------------------------- テキスト入力のタブ

    def _buildTextTab(self) -> None:
        """テキスト入力のタブ(入力欄と、送信のボタン)を作る"""
        tab = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(tab, text="テキスト入力")
        tab.columnconfigure(0, weight=1)
        ttk.Label(tab, text="文字を入力して、Enter を押すと、Switch に送ります。").grid(column=0, columnspan=2, row=0, sticky="w")
        self.text = tk.StringVar()
        self.text_entry = ttk.Entry(tab, textvariable=self.text, font=KEY_FONT)
        self.text_entry.grid(column=0, row=1, sticky="ew", pady=(8, 4))
        self.text_entry.bind("<Return>", lambda event: self.sendText())
        self.send_button = ttk.Button(tab, text="送信", width=8, command=self.sendText)
        self.send_button.grid(column=1, row=1, padx=(6, 0), pady=(8, 4))
        self.preview = tk.StringVar()
        ttk.Label(tab, textvariable=self.preview, wraplength=560, justify="left").grid(column=0, columnspan=2, row=2, sticky="w")
        self.send_enter = tk.BooleanVar(value=False)
        ttk.Checkbutton(tab, text="送信した後に、改行 (Enter) も送る", variable=self.send_enter).grid(
            column=0, columnspan=2, row=3, sticky="w", pady=(8, 0)
        )
        self.note = tk.StringVar()
        ttk.Label(tab, textvariable=self.note, wraplength=560, justify="left").grid(
            column=0, columnspan=2, row=4, sticky="w", pady=(10, 0)
        )
        self._updateNote()
        self.text.trace_add("write", lambda *args: self._updatePreview())
        self.notebook.bind("<<NotebookTabChanged>>", lambda event: self._onTabChanged())

    def _onTabChanged(self) -> None:
        """タブを切り替えたとき: テキスト入力のタブなら、入力欄にフォーカスを移す"""
        if self.notebook.index("current") == 1:
            self.text_entry.focus_set()

    def _updateNote(self) -> None:
        """テキスト入力のタブの説明を、入力モードを自動で切り替えるかに合わせる"""
        lines = ["・送れるのは、半角の英数字・記号と、かな・カナです(漢字は送れません)。"]
        if self.auto_mode.get():
            lines += [
                "・ひらがな・カタカナ・英数字が混ざっていても、Switch 側の入力モードを切り替えながら、そのとおりに打ちます。",
                "・最後に打った部分は、確定の前の状態(下線)で残ります。改行 (Enter) で確定します。",
            ]
        else:
            lines += [
                "・かな・カナは、ローマ字に直して送ります。Switch 側を、ローマ字入力の「かな」または「カナ」に"
                "しておいてください(ひらがなになるか、カタカナになるかは、Switch 側のモードで決まります)。",
                "・半角の英数字を送るときは、Switch 側を、英字のモードにしておいてください。",
            ]
        self.note.set("\n".join(lines))

    def _updatePreview(self) -> None:
        """入力に合わせて、実際に送る文字(ローマ字に直したもの)か、送れない文字を表示する"""
        text = self.text.get()
        typed, invalid = layout.convert_text(text)
        if invalid:
            self.preview.set("送れない文字があります: " + " ".join(invalid))
        elif typed and self.auto_mode.get():
            segments, _ = layout.segment_text(text)
            self.preview.set("送る文字: " + "  ".join(f"[{layout.MODE_LABELS[mode]}] {part}" for mode, part in segments))
        elif typed and typed != text:
            self.preview.set("送る文字: " + typed)
        else:
            self.preview.set("")

    def sendText(self) -> None:
        """送信(Enter): 入力した文字列を打つよう頼み、入力欄を空にする。送れない文字があるときは、送らない"""
        text = self.text.get()
        if not text:
            if self.send_enter.get():
                self.sendKey(KEY.ENTER, "改行 (Enter)")
            return
        typed, invalid = layout.convert_text(text)
        if invalid:
            self.setStatus("送れない文字があるため、送っていません: " + " ".join(invalid), True)
            return
        if self.auto_mode.get():
            # 入力モードごとに区切って、切り替えながら打つ
            accepted = self.typer.type_segments(layout.segment_text(text)[0], text)
        else:
            accepted = self.typer.type_text(typed, text if typed == text else f"{text} ({typed})")
        if not accepted:
            return
        if self.send_enter.get():
            self.sendKey(KEY.ENTER, "改行 (Enter)")
        self.text.set("")

    # ---------------------------------------------------------------- 知らせ

    def setStatus(self, text: str, is_error: bool = False) -> None:
        """下の行に、知らせを表示する(誤りは、赤い文字)"""
        self.status.set(text)
        self.status_label.configure(foreground=Theme.color("danger") if is_error else Theme.color("fg"))

    def _showAvailability(self) -> None:
        """開いたとき: 今は送れない場合(未接続、対応していない Data Format)は、その理由を表示する"""
        reason = self.typer.unavailable_reason()
        if reason:
            self.setStatus(reason, True)
        else:
            self.setStatus("キーを押すと、Switch に送ります。")

    def _poll(self) -> None:
        """一定の間隔で、送信のスレッドからの知らせを、下の行に表示する"""
        if not self.window.winfo_exists():
            return
        message = None
        while True:
            try:
                message = self._messages.get_nowait()
            except queue.Empty:
                break
        if message is not None:
            self.setStatus(*message)
        self.window.after(POLL_MS, self._poll)

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
        """送信をやめて、ウィンドウを閉じる"""
        self.typer.close()
        if self.window.winfo_exists():
            self.window.destroy()
        _logger.debug("Close keyboard window")
