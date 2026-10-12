#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
画面上のキーボード(Keyboard ウィンドウ)からの、Switch へのキーボード入力の送信

スクリプトの TypeString / TypeKey と同じ手順(送信方式の keyboard_steps)で送る。送った後は、マイコンが打ち終わるまで待つ必要が
あるので、送信は専用のスレッドで、頼まれた順に行う(画面を止めない)。画面(tkinter)には触れない。

- 使えるのは、Data Format がキーボード入力に対応している形式(Default / NX)で、シリアルポートに接続しているときだけ
- キーボード入力の用意(スクリプトの KeyBoard_Init の行)は、送らない(コントローラーの入力を離す行なので、コマンドの実行中や、
  手動での操作中に、その入力を離してしまわないようにする)
- OK のキーは、キーボードではなく、コントローラーの + ボタンを短く押す(Switch のキーボード画面の「OK」)
- Switch 側の入力モード(かな / カナ / 英字)を、打つ文字に合わせて切り替えられる(type_text の mode、set_mode)。
  今のモードは、自分が送ったキーから覚えておき、分からないとき(初めと、forget_mode の後)は、どのモードからでも合う並びを送る
  (キーの並びは services/switch_keyboard_layout.py の mode_keys)
"""
from __future__ import annotations

import queue
import threading
import time
from logging import getLogger, DEBUG, NullHandler
from typing import TYPE_CHECKING, Callable

from Commands import SwitchKeyboard
from Commands.Keys import Button, InputSource, KeyPress
from Commands.SwitchKeyboard import KEY
from Commands.transport import get_transport
from Commands.transport.registry import keyboard_transport_names
from services import switch_keyboard_layout as layout

if TYPE_CHECKING:
    from Commands.Sender import Sender

_logger = getLogger(__name__)
_logger.addHandler(NullHandler())
_logger.setLevel(DEBUG)
_logger.propagate = True

# コントローラーのボタン(OK = +)を押している時間(秒)
BUTTON_SECONDS = 0.1
# 頼まれたまま、まだ送っていないものの数の上限(これを超えたら、受け付けない。押しすぎで、送信が延々と続かないようにする)
MAX_PENDING = 200


# モードを切り替えるキーを 1 回押した後のモード: (今のモード, キー) → 次のモード(実機で確かめた動き)
_MODE_AFTER_KEY = {
    (layout.MODE_KANA, int(KEY.JP_HIRAGANA)): layout.MODE_KATAKANA,
    (layout.MODE_KATAKANA, int(KEY.JP_HIRAGANA)): layout.MODE_KANA,
    (layout.MODE_ALNUM, int(KEY.JP_HIRAGANA)): layout.MODE_KANA,
    (layout.MODE_KANA, int(KEY.JP_HANZEN)): layout.MODE_ALNUM,
    (layout.MODE_KATAKANA, int(KEY.JP_HANZEN)): layout.MODE_ALNUM,
    (layout.MODE_ALNUM, int(KEY.JP_HANZEN)): layout.MODE_KANA,
}


class KeyboardTyper:
    """
    Switch へのキーボード入力を、頼まれた順に送る。使い終わったら close
    """

    def __init__(
        self,
        ser: Sender,
        on_message: Callable[[str, bool], None] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        """
        ser: 送る相手
        on_message: 知らせを受け取る関数(文, 誤りか)。送信のスレッドから呼ぶ
        sleep: 待つ関数(テスト用に変えられる)
        """
        self.ser = ser
        self.on_message = on_message
        self._sleep = sleep
        self._key = None
        # Switch 側の、今の入力モード(分からないときは None)。送信のスレッドが、送ったキーに合わせて書き換える
        self.mode = None
        self._queue = queue.Queue()
        self._closed = False
        self._thread = threading.Thread(target=self._run, name="KeyboardTyper", daemon=True)
        self._thread.start()

    # ---------------------------------------------------------------- 頼む(画面のスレッドから)

    def unavailable_reason(self) -> str:
        """今、送れない理由(送れるなら空文字)"""
        if not self.ser.isOpened():
            return "シリアルポートに接続していません。"
        format_name = KeyPress.serial_data_format_name
        if get_transport(format_name).keyboard_steps("init") is None:
            names = " / ".join(keyboard_transport_names())
            return f"キーボード入力は、Data Format が {names} の場合のみ使えます(現在: {format_name})。"
        return ""

    def type_text(self, text: str, label: str | None = None, mode: str | None = None) -> bool:
        """
        半角の文字列を打つよう頼む。受け付けたか
        label: 知らせに出す文字(None なら text)
        mode: 打つ前に合わせる、Switch 側の入力モード(layout.MODE_KANA など。None なら、切り替えない)
        """
        if not text or SwitchKeyboard.find_invalid_characters(text):
            return False
        return self._enqueue(("text", text, mode), label if label is not None else text)

    def type_segments(self, segments: list, label: str) -> bool:
        """
        入力モードごとに区切った文字列(layout.segment_text の結果)を、モードを切り替えながら、続けて打つよう頼む。
        受け付けたか(1 つの依頼として扱うので、途中だけが送られることはない)
        """
        if not segments or any(not text or SwitchKeyboard.find_invalid_characters(text) for _, text in segments):
            return False
        return self._enqueue(("segments", list(segments), None), label)

    def set_mode(self, mode: str, label: str | None = None) -> bool:
        """Switch 側の入力モードを、mode に合わせるよう頼む(すでに合っていれば、何も送らない)。受け付けたか"""
        return self._enqueue(("mode", mode, None), label if label is not None else f"入力モード: {layout.MODE_LABELS[mode]}")

    def forget_mode(self) -> None:
        """覚えている入力モードを忘れる(Switch 側で、モードを変えたとき。次に合わせるときに、初めからやり直す)"""
        self._enqueue(("forget", None, None), "")

    def type_key(self, key: int, label: str | None = None) -> bool:
        """キー(KEY.ENTER など)を 1 回押して離すよう頼む。受け付けたか"""
        return self._enqueue(("Key", int(key), None), label if label is not None else SwitchKeyboard.key_name(key))

    def press_button(self, button: Button = Button.PLUS, label: str = "OK (+)") -> bool:
        """コントローラーのボタンを短く押すよう頼む(既定は、+ ボタン)。受け付けたか"""
        return self._enqueue(("button", button, None), label)

    def _enqueue(self, job: tuple, label: str) -> bool:
        """送信の依頼を、順番待ちに入れる。今は送れない・溜まりすぎのときは、知らせて、受け付けない"""
        if self._closed:
            return False
        reason = self.unavailable_reason()
        if reason:
            self._notify(reason, True)
            return False
        if self._queue.qsize() >= MAX_PENDING:
            self._notify("送信待ちが多すぎます。送り終わるまで、お待ちください。", True)
            return False
        self._queue.put((job, label))
        return True

    def pending(self) -> int:
        """まだ送っていない依頼の数"""
        return self._queue.qsize()

    def close(self) -> None:
        """送信をやめる(順番待ちのものは、送らない)"""
        self._closed = True
        self._queue.put(None)

    # ---------------------------------------------------------------- 送る(専用のスレッド)

    def _notify(self, text: str, is_error: bool = False) -> None:
        """知らせを、on_message に渡す"""
        if self.on_message is not None:
            try:
                self.on_message(text, is_error)
            except Exception:
                _logger.exception("on_message failed")

    def _run(self) -> None:
        """順番待ちの依頼を、1 つずつ送る(スレッドの中身。close まで)"""
        while True:
            item = self._queue.get()
            if item is None or self._closed:
                return
            job, label = item
            try:
                self._send(job)
                if label:
                    self._notify(f"送信: {label}")
            except Exception as e:
                _logger.exception("Failed to send the keyboard input")
                self._notify(f"送信できませんでした: {e}", True)

    def _steps(self, kind: str, value: str | int | None = None) -> list:
        """今の Data Format での、キーボード入力の手順。使えない形式のときは RuntimeError"""
        steps = get_transport(KeyPress.serial_data_format_name).keyboard_steps(kind, value)
        if steps is None:
            raise RuntimeError("この Data Format では、キーボード入力を使えません。")
        return steps

    def _send(self, job: tuple) -> None:
        """依頼を 1 つ送り、マイコンが打ち終わるまで待つ"""
        kind, value, mode = job
        if kind == "forget":
            self.mode = None
            return
        if kind == "mode":
            self._switch_mode(value)
            return
        if kind == "segments":
            for segment_mode, text in value:
                self._switch_mode(segment_mode)
                self._type("text", text)
            return
        if kind == "button":
            if self._key is None:
                self._key = KeyPress(self.ser, source=InputSource.MOUSE)
            self._key.input([value])
            self._sleep(BUTTON_SECONDS)
            self._key.inputEnd([value])
            self._sleep(BUTTON_SECONDS)
            return
        if mode is not None:
            self._switch_mode(mode)
        self._type(kind, value)
        if kind == "Key" and value in (int(KEY.JP_HANZEN), int(KEY.JP_HIRAGANA)):
            # モードを切り替えるキーを、じかに送った: 今のモードが分かっていれば、その先のモードを覚える
            self.mode = _MODE_AFTER_KEY.get((self.mode, value))

    def _type(self, kind: str, value: str | int) -> None:
        """文字列・キーを送り、マイコンが打ち終わるまで待つ"""
        for item, seconds in self._steps(kind, value):
            self.ser.send_keyboard(item)
            self._sleep(seconds)

    def _switch_mode(self, mode: str) -> None:
        """Switch 側の入力モードを、mode にするキーを送る(今のモードが分からなければ、どのモードからでも合う並び)"""
        for name in layout.mode_keys(self.mode, mode):
            self._type("Key", int(KEY[name]))
        self.mode = mode


__all__ = ["KeyboardTyper", "KEY", "BUTTON_SECONDS", "MAX_PENDING"]
