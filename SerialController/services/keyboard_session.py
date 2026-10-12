#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Keyboard ウィンドウの中身(画面を持たない版)

画面上のキーボード(Switch のキーボード画面への入力)の、キーの配置を画面に渡す形にまとめ、押されたキー・入力された文字列を、
送信の処理(services/keyboard_typer.py)に頼む。Web 版のブラウザの画面が使う。画面(tkinter)には触れない。
キーの配置と、送る文字は services/switch_keyboard_layout.py。
"""
from __future__ import annotations

from logging import getLogger, DEBUG, NullHandler
from typing import TYPE_CHECKING, Callable

from services import switch_keyboard_layout as layout
from services.keyboard_typer import KEY, KeyboardTyper

if TYPE_CHECKING:
    from Commands.Sender import Sender

_logger = getLogger(__name__)
_logger.addHandler(NullHandler())
_logger.setLevel(DEBUG)
_logger.propagate = True

# 右側のキー(消す・空白・改行): 名前 → (送るキー, 知らせに出す文字)
SPECIAL_KEYS = {
    "backspace": (KEY.BACKSPACE, "BackSpace"),
    "space": (KEY.SPACE, "空白"),
    "enter": (KEY.ENTER, "改行 (Enter)"),
}
READY_MESSAGE = "キーを押すと、Switch に送ります。"


class KeyboardSession:
    """
    画面上のキーボードの 1 つ分。使い終わったら close
    """

    def __init__(
        self,
        ser: Sender,
        on_message: Callable[[str, bool], None] | None = None,
        typer: KeyboardTyper | None = None,
    ):
        """
        ser: 送る相手
        on_message: 知らせを受け取る関数(文, 誤りか)。送信のスレッドからも呼ぶ
        typer: 送信の処理(None なら、作る。テスト用に、代わりのものを渡せる)
        """
        self.on_message = on_message
        self.typer = typer if typer is not None else KeyboardTyper(ser, on_message=on_message)
        # 最後に合わせたページ(ページを変えたときだけ、Switch 側の入力モードを合わせる)
        self.page = layout.PAGE_HIRAGANA

    def close(self) -> None:
        """送信をやめる"""
        self.typer.close()

    # ---------------------------------------------------------------- 画面に渡すもの

    @staticmethod
    def layout_state() -> dict:
        """
        キーの配置を、画面に渡す形で返す:
        {"pages": [{"id", "label", "kana"}], "rows": {ページ: 5 行 × 11 列}, "small_rows": {かな・カナのページ: 同じ}}
        マスは {"c": 文字, "ok": 送れるか}。キーのないマスは None
        """

        def cells(page: str, small: bool) -> list:
            """そのページの配置を、マスの一覧にする"""
            return [
                [{"c": character, "ok": layout.sendable(character)} if character else None for character in row]
                for row in layout.page_rows(page, small)
            ]

        return {
            "pages": [
                {"id": page, "label": layout.PAGE_LABELS[page], "kana": page in layout.KANA_PAGES} for page in layout.PAGES
            ],
            "rows": {page: cells(page, False) for page in layout.PAGES},
            "small_rows": {page: cells(page, True) for page in layout.KANA_PAGES},
        }

    def availability(self) -> tuple[str, bool]:
        """開いたときに表示する知らせ(文, 誤りか): 今は送れない場合は、その理由"""
        reason = self.typer.unavailable_reason()
        return (reason, True) if reason else (READY_MESSAGE, False)

    @staticmethod
    def preview(text: str, auto_mode: bool) -> str:
        """入力に合わせて表示する、実際に送る文字(ローマ字に直したもの)か、送れない文字"""
        typed, invalid = layout.convert_text(text)
        if invalid:
            return "送れない文字があります: " + " ".join(invalid)
        if typed and auto_mode:
            segments, _ = layout.segment_text(text)
            return "送る文字: " + "  ".join(f"[{layout.MODE_LABELS[mode]}] {part}" for mode, part in segments)
        if typed and typed != text:
            return "送る文字: " + typed
        return ""

    # ---------------------------------------------------------------- 操作

    def _notify(self, text: str, is_error: bool = False) -> None:
        """知らせを、on_message に渡す"""
        if self.on_message is not None:
            self.on_message(text, is_error)

    def show_page(self, page: str, auto_mode: bool) -> None:
        """
        ページを切り替えたとき: 自動で切り替える設定で、送れる状態なら、Switch 側の入力モードを、そのページに合わせる
        (同じページのままなら、何も送らない。知らないページは KeyError)
        """
        mode = layout.PAGE_MODES[page]
        changed = page != self.page
        self.page = page
        if changed and auto_mode and not self.typer.unavailable_reason():
            self.typer.set_mode(mode)

    def press(self, page: str, small: bool, row: int, column: int, auto_mode: bool) -> bool:
        """
        文字のキーを押したとき: その文字を打つよう頼む(かな・カナは、ローマ字で送る)。受け付けたか
        page / small: 表示しているページ。row / column: キーの位置
        """
        try:
            character = layout.page_rows(page, bool(small) and page in layout.KANA_PAGES)[int(row)][int(column)]
        except (KeyError, IndexError, TypeError, ValueError):
            return False
        typed = layout.typed_text(character) if character else None
        if typed is None:
            return False
        if not auto_mode:
            mode = None
        elif page in layout.KANA_PAGES:
            # かな・カナのページのキーは、そのページのモード(? ! などの記号も、そのモードのまま打つ)
            mode = layout.PAGE_MODES[page]
        else:
            # 英字・記号のページのキーは、英字(「・」「〜」のように、かなのモードでしか打てない記号は、かな)
            mode = layout.character_mode(character)
        label = character if typed == character else f"{character} ({typed})"
        return self.typer.type_text(typed, label, mode)

    def special(self, name: str) -> bool:
        """右側のキー("backspace" / "space" / "enter")を 1 回押すよう頼む。受け付けたか(知らない名前は False)"""
        if name not in SPECIAL_KEYS:
            return False
        key, label = SPECIAL_KEYS[name]
        return self.typer.type_key(key, label)

    def ok(self) -> bool:
        """OK: コントローラーの + ボタンを短く押すよう頼む(Switch のキーボード画面の OK)。受け付けたか"""
        return self.typer.press_button()

    def sync(self, page: str) -> bool:
        """地球のマーク: Switch 側の入力モードを、そのページに合わせ直す(覚えているモードを忘れて、初めから合わせる)"""
        mode = layout.PAGE_MODES[page]
        self.page = page
        self.typer.forget_mode()
        return self.typer.set_mode(mode, f"入力モードを合わせ直しました: {layout.MODE_LABELS[mode]}")

    def forget(self) -> None:
        """自動で切り替える設定を変えたとき: 覚えている入力モードを忘れる"""
        self.typer.forget_mode()

    def send_text(self, text: str, auto_mode: bool, send_enter: bool) -> bool:
        """
        入力した文字列を打つよう頼む。受け付けたか(受け付けたら、画面の側は、入力欄を空にする)。
        送れない文字があるときは、送らずに知らせる。send_enter: 送信した後に、改行 (Enter) も送るか
        """
        if not text:
            if send_enter:
                self.special("enter")
            return False
        typed, invalid = layout.convert_text(text)
        if invalid:
            self._notify("送れない文字があるため、送っていません: " + " ".join(invalid), True)
            return False
        if auto_mode:
            # 入力モードごとに区切って、切り替えながら打つ
            accepted = self.typer.type_segments(layout.segment_text(text)[0], text)
        else:
            accepted = self.typer.type_text(typed, text if typed == text else f"{text} ({typed})")
        if not accepted:
            return False
        if send_enter:
            self.special("enter")
        return True
