#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
送信方式(Transport)の共通の型。

送るデータの形式(画面の Data Format)ごとの違いを、1つのクラスにまとめる。
- 合成した入力を、機器へ送るデータにする方法
- ポートの開き方、形式で決まるボーレート
- ボタンのビットの並び、使える機能(タッチスクリーン、文字列の行の送信など)

形式を足すときは、このクラスを継承したクラスを作り、registry.py に登録する。
"""
from __future__ import annotations

from collections import OrderedDict
from typing import TYPE_CHECKING

from Commands.Keys import conversion_default_button

if TYPE_CHECKING:
    from Commands.Keys import SendFormat
    from Commands.Sender import Sender


class Transport:
    """送信方式の基底クラス。形式ごとの違いを、クラスの変数と、下のメソッドの上書きで表す"""

    # 形式の名前(画面の Data Format に表示し、設定ファイルにも保存する。変えると、保存済みの設定が合わなくなる)
    name = ""
    # 形式で決まるボーレート(接続するときに、この値に合わせる。None: ボーレートを使わない)
    baud_rate: int | None = 9600
    # Button -> 送るビット の対応
    button_conversion = conversion_default_button
    # タッチスクリーンの入力を送れるか
    has_touchscreen = False
    # 文字列の行を送れるか(キーボード入力の関数など)
    supports_text = False
    # 入力の合成を経由しない送信(Mcu コマンド、direct_serial など)を、そのまま機器へ送ってよいか
    allows_raw_write = True
    # 送ってはいけない場合に、1回だけ表示する文と、ログに残す文
    raw_write_message = ""
    raw_write_log = ""
    # コマンドの終了時に、ほかの入力源が残っていなければ送る行(None: 送らず、入力を離した状態を送る)
    end_row: str | None = None
    # 前回と同じデータなら送らないか
    skip_unchanged = False

    def is_available(self) -> bool:
        """この環境で使えるか(必要なライブラリが入っているか、など)"""
        return True

    def unavailable_message(self) -> str:
        """使えない場合に表示する文"""
        return ""

    def open(self, sender: Sender, port_num: int, port_name: str = "", baudrate: int = 9600) -> bool:
        """
        ポートを開いて sender.ser に入れる。開けたかを返す(既定は COM ポート)

        port_num: ポートの番号(COM の後ろの数字など)。port_name が空の場合に使う
        port_name: ポートの名前。指定した場合は、番号より、こちらで開く
        """
        return sender._openSerial(port_num, port_name, baudrate)

    def keyboard_steps(self, kind: str, value: str | int | None = None) -> list | None:
        """
        Switch へのキーボード入力(TypeString / TypeKey など)の手順。この形式では使えない場合は None。

        kind: "init"(始める前の準備) / "text"(value の文字列を打つ) /
              "Key"(value のキーを押して離す) / "Press"(押したまま) / "Release"(離す)
        value: "text" では打つ文字列、キーの操作では SwitchKeyboard.KEY か数値。"init" では使わない
        戻り値: [(送るもの, 送った後に待つ秒数), ...]
            送るもの: 文字列(行として、そのまま送る)、または encode_keyboard に渡す値の組
        """
        return None

    def encode_keyboard(self, state: OrderedDict, encoder: SendFormat, *action: int) -> str | bytes | list[int]:
        """
        keyboard_steps が返した値の組(action)を、今のコントローラーの状態(state)と一緒に送るデータにする
        (キーボードの操作を、コントローラーの状態と同じデータで送る形式が使う)

        戻り値は encode と同じ(文字列は行として、bytes・数値のリストはそのまま送る)。
        対応していない形式では NotImplementedError
        """
        raise NotImplementedError

    def encode(
        self, state: OrderedDict, last_sent: dict | None, encoder: SendFormat, port: object
    ) -> str | bytes | list[int] | None:
        """
        合成した入力(state)を、機器へ送るデータにする。

        state: SendFormat.format と同じ形(btn は、この形式のビットの並び)
        last_sent: 前回送った state(分からない場合は None)
        encoder: 変換に使える SendFormat
        port: 今開いているポート(serial.Serial、FtdiPort。開いていなければ None。形式で違うので object)
        戻り値: 文字列(行として送る)、bytes・数値のリスト(そのまま送る)、None(送らない)
        """
        raise NotImplementedError
