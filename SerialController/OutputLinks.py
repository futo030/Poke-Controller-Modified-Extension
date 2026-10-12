#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
出力画面(Output)に表示する、クリックで処理を行うリンク

- link(文字, 処理) で、リンクの印を付けた文字列を作る。これを print すると、出力画面ではその文字がリンクになる
  (印は出力画面に書き込むときに取り除く)
- リンクをクリックすると、メインスレッドで処理を呼ぶ。once=True のリンクは、1回押すとリンクではなくなる
- どのスレッドからでも作れる(自動化スクリプトのスレッドから print してよい)
"""
from __future__ import annotations

import re
import threading
from typing import Callable

_START = "\x01"
_SEPARATOR = "\x02"
_END = "\x03"
_PATTERN = re.compile(f"{_START}(\\d+){_SEPARATOR}(.*?){_END}", re.DOTALL)

_lock = threading.Lock()
_next_id = 1
# リンクの番号 -> (処理, 1回だけか)
_actions: dict[int, tuple[Callable[[], None], bool]] = {}


def link(label: str, action: Callable[[], None], once: bool = False) -> str:
    """
    クリックすると action を呼ぶリンクの文字列を返す
    label: リンクにする文字、once: 1回押すと、リンクではなくなるようにするか
    """
    global _next_id
    with _lock:
        link_id = _next_id
        _next_id += 1
        _actions[link_id] = (action, once)
    return f"{_START}{link_id}{_SEPARATOR}{label}{_END}"


def has_link(text: str) -> bool:
    """文字列に、リンクの印が含まれているか"""
    return _START in text


def split(text: str) -> list[tuple[str, int | None]]:
    """
    文字列を (文字, リンクの番号 / リンクでなければNone) の並びに分ける
    """
    parts = []
    position = 0
    for match in _PATTERN.finditer(text):
        if match.start() > position:
            parts.append((text[position : match.start()], None))
        parts.append((match.group(2), int(match.group(1))))
        position = match.end()
    if position < len(text):
        parts.append((text[position:], None))
    return parts


def strip(text: str) -> str:
    """
    リンクの印を取り除いた文字列を返す
    """
    return _PATTERN.sub(lambda match: match.group(2), text)


def run(link_id: int) -> bool:
    """
    リンクの処理を呼ぶ。1回だけのリンクなら、その後は使えなくする
    戻り値: そのリンクが1回だけのリンクだったか(その番号のリンクが無い・もう使えない場合は、何もせず False)
    """
    with _lock:
        entry = _actions.get(link_id)
        if entry is None:
            return False
        action, once = entry
        if once:
            del _actions[link_id]
    action()
    return once
