#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Status タブに表示する文字を作る(今つながっている機器と、実行中のコマンド・開始時間を、1 行ずつの文字にする)

画面(tkinter)には触れない。値を集めて表示するのは ui/status_panel.py
"""
from __future__ import annotations

import re
from datetime import datetime

# 機器を使っていないとき、コマンドを実行していないときに表示する文字
NOT_OPENED = "(開いていません)"
NOT_USED = "(使用していません)"
NOT_AVAILABLE = "(使用できません)"
NOT_CONNECTED = "(接続していません)"
NO_PLAYBACK = "(再生しません)"
NO_COMMAND = "(なし)"
UNKNOWN_TIME = "(不明)"
# カメラの名前のうち、ここから後ろ(機器を見分けるための長い文字)は、表示しない
CAMERA_NAME_CUT = "(@"
START_TIME_FORMAT = "%Y/%m/%d %H:%M:%S"


def camera_name(name: str) -> str:
    """カメラの名前から、「(@」以降(機器を見分けるための長い文字)を取り除く"""
    return str(name).split(CAMERA_NAME_CUT, 1)[0].strip()


def camera_text(name: str, capture_size: str, opened: bool) -> str:
    """
    Camera Device の行: 名前 (Capture Size: 幅x高さ)。開いていなければ、その旨
    name: Camera タブの Device の表示、capture_size: 取り込みサイズ("幅x高さ")、opened: カメラを開いているか
    """
    if not opened:
        return NOT_OPENED
    return f"{camera_name(name) or '(名前なし)'} (Capture Size: {capture_size})"


def audio_input_text(name: str, running: bool, available: bool = True) -> str:
    """
    Audio Device (Input) の行: 取り込んでいるデバイスの名前。取り込んでいなければ、その旨
    available: 音声の機能を使えるか(sounddevice が入っているか)
    """
    if not available:
        return NOT_AVAILABLE
    if not running:
        return NOT_USED
    return str(name).strip() or "(名前なし)"


def audio_output_text(name: str, running: bool, playback: bool, available: bool = True) -> str:
    """Audio Device (Output) の行: 再生しているデバイスの名前。取り込んでいない・再生しない場合は、その旨"""
    if not available:
        return NOT_AVAILABLE
    if not running:
        return NOT_USED
    if not playback:
        return NO_PLAYBACK
    return str(name).strip() or "(名前なし)"


def serial_text(name: str, port: object, baud_rate: object, opened: bool, port_label: str = "COM") -> str:
    """
    Serial Device の行: 名前 (Baud Rate: xxx)。接続していなければ、その旨。
    名前にポート(COMxx)が入っていないときは、名前 (COMxx, Baud Rate: xxx)(名前に入っているときは、重ねて出さない)
    port_label: ポートの番号の前に付ける文字(Windows は "COM"。ほかの OS は "Port ")
    """
    if not opened:
        return NOT_CONNECTED
    name = str(name).strip()
    port_text = f"{port_label}{port}"
    # (COM1 が、COM13 の一部として見つからないように、後ろが数字でないことも確かめる)
    named = re.search(re.escape(port_text) + r"(?!\d)", name) is not None
    detail = f"Baud Rate: {baud_rate}" if named else f"{port_text}, Baud Rate: {baud_rate}"
    return f"{name} ({detail})" if name else detail


def command_text(name: str | None) -> str:
    """
    実行中のコマンド の行: 名前。実行していなければ、その旨
    name: 実行中のコマンドの名前(実行していなければ None)
    """
    return str(name) if name else NO_COMMAND


def started_text(name: str | None, started_at: datetime | None) -> str:
    """
    開始時間 の行: yyyy/mm/dd hh:mm:ss。実行していなければ、その旨(名前が長くても見えるように、名前とは別の行に出す)
    name: 実行中のコマンドの名前(実行していなければ None)、started_at: 開始した時刻(分からなければ None)
    """
    if not name:
        return NO_COMMAND
    if started_at is None:
        return UNKNOWN_TIME
    return started_at.strftime(START_TIME_FORMAT)
