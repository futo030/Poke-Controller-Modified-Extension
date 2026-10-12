#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
送るデータの形式(Data Format)ごとに、決まった入力を順に行い、機器へ送るデータを記録する。

test_transport_golden.py が、ここで得た結果を tests/data/transport_golden.json と比べる
(形式ごとの処理を整理しても、送るデータが1バイトも変わらないことを確かめるため)。

新しい形式を足したとき・送るデータを意図して変えたときは、SerialController フォルダで次を実行して、
記録を作り直す(差分を確認してからコミットする):
    python tests/transport_scenarios.py --write
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Commands import SwitchKeyboard  # noqa: E402
from Commands.FtdiPort import FTDI_FORMATS, FtdiPort  # noqa: E402
from Commands.Keys import (  # noqa: E402
    Button,
    Direction,
    Hat,
    InputSource,
    KeyPress,
    Stick,
    Touchscreen,
    get_button_conversion,
    is_ftdi_format,
)
from Commands.Sender import Sender  # noqa: E402
from services import serial_service  # noqa: E402
from services.app_core import AppCore  # noqa: E402

GOLDEN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "transport_golden.json")

# 記録する形式(これまでにある形式。新しい形式は、ここに足す)
FORMATS = ["Default", "NX", "Qingpi", "3DS Controller(FW:-x.3)", "3DS Controller(FW:x.4-)"] + list(FTDI_FORMATS)


class FakeSerial:
    """COM ポートの代役(送られたデータを記録する)"""

    def __init__(self, log: list):
        self.log = log

    def write(self, data):
        self.log.append(_payload(data))

    def isOpen(self):
        return True

    def close(self):
        pass


class FakeFtdiDevice:
    """FTDI のデバイスの代役"""

    def __init__(self, log: list):
        self.log = log

    def write(self, data):
        self.log.append(_payload(data))
        return len(data)

    def close(self):
        pass


class FakeRecorder:
    """操作記録の代役(渡された状態を記録する)"""

    def __init__(self, log: list):
        self.log = log

    def update_raw(self, *values):
        self.log.append("record " + " ".join(str(int(value)) for value in values))


def _payload(data) -> str:
    if isinstance(data, (bytes, bytearray)):
        try:
            text = bytes(data).decode("ascii")
        except UnicodeDecodeError:
            text = None
        if text is not None and text.endswith("\r\n") and text.isprintable() is False and text[:-2].isprintable():
            return "text " + text[:-2]
        return "bytes " + bytes(data).hex(" ")
    return "list " + " ".join(format(int(value), "02x") for value in data)


def _steps(sender: Sender, command: KeyPress, mouse: KeyPress, log: list):
    """決まった入力を順に行う"""

    def mark(name):
        log.append(f"# {name}")

    mark("press A")
    command.input(Button.A)
    command.inputEnd(Button.A)
    mark("each button")
    for button in Button:
        command.input(button)
        command.inputEnd(button)
    mark("each hat")
    for hat in Hat:
        command.input(hat)
        command.inputEnd(hat)
    mark("sticks")
    for direction in (
        Direction.UP, Direction.RIGHT, Direction.DOWN_LEFT, Direction.R_UP, Direction.R_DOWN_RIGHT,
        Direction(Stick.LEFT, 30, 0.5), Direction(Stick.RIGHT, 200, 0.25),
    ):
        command.input(direction)
        command.inputEnd(direction)
    mark("combination")
    command.input([Button.B, Button.ZR, Hat.TOP_RIGHT, Direction.UP, Direction.R_LEFT])
    command.inputEnd([Button.B, Direction.UP])
    command.inputEnd([Button.ZR, Hat.TOP_RIGHT, Direction.R_LEFT])
    mark("touch")
    command.input(Touchscreen(100, 50))
    command.inputEnd(Touchscreen(100, 50))
    command.input([Button.A, Touchscreen(319, 239)])
    command.inputEnd([Button.A, Touchscreen(319, 239)])
    mark("two sources")
    command.input([Button.A, Direction.UP])
    mouse.input([Button.X, Hat.LEFT, Direction.DOWN])
    command.inputEnd([Button.A, Direction.UP])
    mouse.inputEnd([Button.X, Hat.LEFT, Direction.DOWN])
    mark("recording")
    sender.start_recording(FakeRecorder(log))
    mouse.input([Button.Y, Button.SELECT, Hat.BTM, Touchscreen(10, 20)])
    mouse.inputEnd([Button.Y, Button.SELECT, Hat.BTM, Touchscreen(10, 20)])
    sender.stop_recording()
    mark("hold and neutral")
    command.holdButton = [Button.L, Direction.RIGHT]
    command.input(Button.A)
    command.inputEnd(Button.A)
    command.neutral()
    mark("end with another source")
    command.input(Button.A)
    mouse.input(Button.B)
    command.end()
    mouse.inputEnd(Button.B)
    mark("end alone")
    command.input(Button.A)
    command.end()
    mark("raw write")
    sender.writeRow("end")
    sender.writeList([0xAB, 0x01, 0x02])
    sender.writeRow_wo_perf_counter("0x0004 8")
    mark("after raw write")
    command.input(Direction.UP)
    command.inputEnd(Direction.UP)
    command.end()


def run_format(name: str) -> dict:
    """1つの形式について、送るデータと、形式で決まる値を記録する"""
    original = KeyPress.serial_data_format_name
    KeyPress.serial_data_format_name = name
    log: list = []
    printed = io.StringIO()
    try:
        with contextlib.redirect_stdout(printed):
            sender = Sender(False)
            if is_ftdi_format(name):
                sender.ser = FtdiPort(FakeFtdiDevice(log), name)
            else:
                sender.ser = FakeSerial(log)
            _steps(sender, KeyPress(sender, InputSource.COMMAND), KeyPress(sender, InputSource.MOUSE), log)
    finally:
        KeyPress.serial_data_format_name = original
    core = SimpleNamespace(settings=SimpleNamespace(serial_data_format_name=name))
    return {
        "baud_rate": serial_service.forced_baud_rate(name),
        "keyboard_input": SwitchKeyboard.is_text_format(name),
        "touchscreen": AppCore.has_touchscreen.fget(core),
        "buttons": {button.name: int(value) for button, value in get_button_conversion(name).items()},
        "printed": sorted(set(line for line in printed.getvalue().splitlines() if line.strip())),
        "sent": log,
    }


def run_all() -> dict:
    return {name: run_format(name) for name in FORMATS}


def main():
    result = run_all()
    if "--write" in sys.argv:
        os.makedirs(os.path.dirname(GOLDEN_FILE), exist_ok=True)
        with io.open(GOLDEN_FILE, "w", encoding="utf-8", newline="\n") as file:
            json.dump(result, file, ensure_ascii=False, indent=1)
            file.write("\n")
        print(f"wrote {GOLDEN_FILE}")
    for name, values in result.items():
        print(name, len(values["sent"]), "lines")


if __name__ == "__main__":
    main()
