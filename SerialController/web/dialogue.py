#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
コマンドから開くダイアログ(Web 版): ブラウザに表示を頼み、入力結果を待つ

ウィジェットの種類と戻り値は、tkinter 版(PokeConDialogue.py)と同じにする。
"""
from __future__ import annotations

import itertools
import threading
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from Commands.CommandBase import Command

# 入力を待つ間、取り消されていないかを確かめる間隔(秒)
WAIT_INTERVAL = 0.2
WIDGET_KINDS = ("check", "combo", "entry", "radio", "scale", "spin")


def build_fields(message: int | str | list, mode: int) -> list:
    """
    ダイアログの内容を、ブラウザに渡す形(JSON にできる辞書のリスト)にする。
    mode 0: 入力欄だけ(message は、項目名または項目名のリスト)
    mode 1: ウィジェットの指定のリスト(["Check", 名前, 初期値] など。["Next"] は列の区切り)
    各辞書の "key" は、戻り値の辞書で使うキー(項目名そのもの。文字列でない場合もある)
    """
    if mode == 0:
        names = message if type(message) is list else [message]
        return [{"kind": "entry", "key": name, "name": str(name), "value": ""} for name in names]
    fields = []
    for item in message:
        kind = str(item[0]).casefold()
        if kind == "next":
            fields.append({"kind": "next"})
            continue
        field = {"kind": kind, "key": item[1], "name": str(item[1])}
        if kind == "check":
            field["value"] = bool(item[2])
        elif kind == "entry":
            field["value"] = str(item[2])
        elif kind in ("combo", "radio", "spin"):
            field["options"] = [str(option) for option in item[2]]
            field["value"] = str(item[3])
        elif kind == "scale":
            field.update({"min": item[2], "max": item[3], "value": item[4], "digits": int(item[5])})
        else:
            # 知らない種類は、tkinter 版と同じく枠だけを表示する(値は持たない)
            field["kind"] = "unknown"
        fields.append(field)
    return fields


def input_fields(fields: list) -> list:
    """値を持つ項目(列の区切りと、知らない種類を除く)"""
    return [field for field in fields if field["kind"] in WIDGET_KINDS]


def coerce_value(field: dict, value: object) -> bool | int | float | str:
    """
    ブラウザから届いた値を、tkinter 版が返すのと同じ型にする(おかしな値は、初期値に戻す)
    field: build_fields が作った項目、value: ブラウザから届いた値(型は決まっていない)
    """
    kind = field["kind"]
    try:
        if kind == "check":
            return bool(value)
        if kind == "scale":
            number = min(max(float(value), float(field["min"])), float(field["max"]))
            return round(number, field["digits"]) if field["digits"] != 0 else int(number)
        if kind in ("combo", "radio"):
            return str(value) if str(value) in field["options"] or str(value) == field["value"] else field["value"]
        return str(value)
    except (TypeError, ValueError):
        return field["value"]


def build_result(fields: list, values: list, need: type) -> list | dict:
    """
    入力結果を、コマンドに返す形にする(need が dict なら {項目名: 値}、それ以外はリスト)
    values: 値を持つ項目の順の値(足りない分は、初期値を使う)
    """
    inputs = input_fields(fields)
    values = list(values) + [field["value"] for field in inputs[len(values):]]
    coerced = [coerce_value(field, value) for field, value in zip(inputs, values)]
    if need is dict:
        return {field["key"]: value for field, value in zip(inputs, coerced)}
    if need is not list:
        print("Wrong arg. Try Return list.")
    return coerced


class DialogueBroker:
    """
    ダイアログの表示を画面に頼み、コマンドのスレッドで結果を待つ
    """

    def __init__(self, show: Callable[[dict], None], hide: Callable[[int], None]):
        """
        show: ダイアログの表示を画面に頼む関数(引数は、ブラウザに渡す辞書)
        hide: ダイアログを閉じるよう画面に頼む関数(引数は、ダイアログの番号)
        """
        self._show = show
        self._hide = hide
        self._ids = itertools.count(1)
        self._lock = threading.Lock()
        self._pending = {}

    def open(
        self,
        command: Command,
        title: str,
        message: int | str | list,
        desc: str | None = None,
        need: type = list,
        mode: int = 0,
        pos: int = 2,
    ) -> list | dict | bool:
        """
        Command.dialogue_handler に登録する関数。入力結果(キャンセルの場合は False)を返す
        (コマンドのスレッドで呼ばれ、ブラウザで入力が終わるか、取り消されるまで戻らない)
        command: 開いたコマンド(使わない)、title: 題名、message / mode: ダイアログの内容(build_fields を参照)
        desc: 説明の文(None なら無し)、need: 戻り値の型(list / dict)、pos: ボタンの位置(1～3。それ以外は 2)
        """
        fields = build_fields(message, mode)
        entry = {
            "event": threading.Event(),
            "answer": None,
            "request": {
                "id": next(self._ids),
                "title": str(title),
                "desc": None if desc is None else str(desc),
                "pos": pos if pos in (1, 2, 3) else 2,
                "fields": [{k: v for k, v in field.items() if k != "key"} for field in fields],
            },
        }
        dialogue_id = entry["request"]["id"]
        with self._lock:
            self._pending[dialogue_id] = entry
        try:
            self._show(entry["request"])
            while not entry["event"].wait(WAIT_INTERVAL):
                pass
        finally:
            with self._lock:
                self._pending.pop(dialogue_id, None)
            self._hide(dialogue_id)
        answer = entry["answer"]
        if answer is None:
            return False
        return build_result(fields, answer, need)

    def pending_requests(self) -> list:
        """
        入力を待っているダイアログ(あとから開いたブラウザに表示するために使う)
        """
        with self._lock:
            return [entry["request"] for entry in self._pending.values()]

    def answer(self, dialogue_id: int, ok: bool, values: list | None = None) -> bool:
        """
        ブラウザからの入力結果を受け取る。そのダイアログが入力を待っていたかを返す
        ok: OK が押されたか(False はキャンセル)、values: 値を持つ項目の順の値
        """
        with self._lock:
            entry = self._pending.get(dialogue_id)
        if entry is None or entry["event"].is_set():
            return False
        entry["answer"] = list(values or []) if ok else None
        entry["event"].set()
        return True

    def cancel_all(self) -> None:
        """
        入力を待っているダイアログを、すべてキャンセルとして閉じる(コマンドを止めるとき)
        """
        with self._lock:
            entries = list(self._pending.values())
        for entry in entries:
            entry["answer"] = None
            entry["event"].set()
