#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import List, TYPE_CHECKING

import math
import os
import time
import platform
import threading
from collections import OrderedDict

import serial
from logging import getLogger, DEBUG, NullHandler

from Commands.FtdiPort import FtdiError
from Commands.Keys import (
    Hat,
    InputSource,
    KeyPress,
    SendFormat,
    center,
    get_button_conversion,
    revert_button_bits,
)
from Commands.transport import Transport, get_transport, port_transport
from services.serial_monitor import SerialMonitor

if TYPE_CHECKING:
    import tkinter as tk
    from Commands.InputRecorder import InputRecorder

# 入力源毎に優先度で1つを選ぶ項目(ボタン以外)と、そのニュートラル値
_EXCLUSIVE_GROUPS = {
    "hat": (("hat",), (int(Hat.CENTER),)),
    "lstick": (("lx", "ly"), (center, center)),
    "rstick": (("rx", "ry"), (center, center)),
    "touch": (("sx", "sy"), (0, 0)),
}


# 何も入力していない状態(合成のたびにSendFormatを作らないよう、1回だけ作って複製する)
_NEUTRAL_STATE = OrderedDict(SendFormat().format)


def _neutral_state() -> OrderedDict:
    """何も入力していない状態の、新しい複製を返す"""
    return OrderedDict(_NEUTRAL_STATE)


def _is_neutral(state: dict) -> bool:
    """state(SendFormat.format と同じ形)が、何も入力していない状態か"""
    if state["btn"] != 0:
        return False
    for keys, neutral in _EXCLUSIVE_GROUPS.values():
        if tuple(state[k] for k in keys) != neutral:
            return False
    return True


class _InputLayer(object):
    """
    1つの入力源の状態
    """

    def __init__(self, priority: int) -> None:
        """priority: 入力源の優先度(InputSource。大きいほど優先する)"""
        self.priority = int(priority)
        self.state = None
        # 項目毎に最後に変化した時の通し番号(同じ優先度の入力源同士では後から変化した方を採用する)
        self.changed = {}


# 送信の失敗が、この回数続いたら、on_send_failures を呼ぶ
SEND_FAILURE_LIMIT = 5
# ポートを開けなかったときに、エラーの内容に続けて表示する案内(ボタンの名前は、Serial タブの実際の表示)
OPEN_FAILED_HINT = "機器の抜き差しを行い、[Scan Device]+[Reload Port]を実施すると改善することがあります。"


class Sender:
    """
    シリアル送信を行うクラス
    - 送信は全てロック内で行う(複数スレッドからの送信が混ざらないようにする)
    - KeyPressからの送信は入力源毎の状態を合成して送る
      (コマンド実行中に手動操作しても、コマンドの入力が上書きされないようにする)
        ボタン: 全入力源の論理和
        Hat・スティック・タッチ: 倒されている入力源のうち、優先度の高いもの
                                 (同じ優先度なら後から変化したもの)
    - 操作記録中は、手動操作の入力源(コマンド以外)のみを合成した状態をInputRecorderに渡す
    - 送るデータの形式(Data Format)ごとの違い(送るデータへの変換、ポートの開き方、使える機能)は、
      送信方式(Commands/transport)が持つ。このクラスは、今の形式の送信方式に問い合わせて送る
    - 送信方式によっては、合成を経由しない送信(writeRow等)は行わない
      (例: FTDI直結の基板。文字列を送るとMPSSEのコマンドとして解釈され、意図しないピンが動くため)
    """

    def __init__(self, is_show_serial: tk.BooleanVar | bool, if_print: bool = True) -> None:
        """
        is_show_serial: 送ったデータを表示するか。tkinter の変数(チェックボックスの変更に合わせる)か、
                        真偽値(画面を使わない場合。後から変えるときは set_show_serial)
        if_print: show_input で、押したボタンを self.press(...) の形で表示するか
        """
        self.ser = None
        self._lock = threading.RLock()
        # 入力源 -> _InputLayer
        self._layers = {}
        self._layer_seq = 0
        # 最後に送信した合成状態(Default形式でスティックの変化を判定するため。None: 不明)
        self._last_sent = None
        self._encoder = SendFormat()
        # 操作記録(記録していない場合はNone)
        self._recorder: InputRecorder | None = None
        # 最後に送信したデータ(同じデータは送らない送信方式で使う)、直接送信を止めたことを表示済みか
        self._last_payload = None
        self._raw_write_warned = False
        self.is_show_serial = is_show_serial
        # 送信処理(コマンド実行スレッド)からTkを呼ばないよう、表示有無をboolで保持する
        # (別スレッドからのBooleanVar.get()はメインスレッドの処理完了まで待たされるため)
        if hasattr(is_show_serial, "trace_add"):
            # tkinterの変数: チェックボックスの変更に合わせる
            self.show_serial = bool(is_show_serial.get())
            is_show_serial.trace_add("write", self._on_show_serial_changed)
        else:
            # 真偽値(画面を使わない場合)。変更は set_show_serial で行う
            self.show_serial = bool(is_show_serial)
        # シリアルモニター(Show Serial にチェックを入れている間に送ったデータを溜める。画面が取り出して表示する)
        self.monitor = SerialMonitor()
        # 送信の失敗が続いた回数(1 回でも送れたら 0 に戻す)と、続いたときに呼ぶ関数(回数, 最後のエラー)。
        # 接続が切れたまま、コマンドが進み続けないように、画面や本体が、この関数でコマンドを止める
        # (ポートを開いていない場合は、失敗に数えない。接続せずにスクリプトを試すことがあるため)
        self.on_send_failures = None
        self._send_failures = 0
        self._send_failures_reported = False

        self._logger = getLogger(__name__)
        self._logger.addHandler(NullHandler())
        self._logger.setLevel(DEBUG)
        self._logger.propagate = True

        self.before = None
        self.L_holding = False
        self._L_holding = None
        self.R_holding = False
        self._R_holding = None
        self.is_print = if_print
        self.time_bef = time.perf_counter()
        self.time_aft = time.perf_counter()
        self.Buttons = [
            "Stick.RIGHT",
            "Stick.LEFT",
            "Button.Y",
            "Button.B",
            "Button.A",
            "Button.X",
            "Button.L",
            "Button.R",
            "Button.ZL",
            "Button.ZR",
            "Button.MINUS",
            "Button.PLUS",
            "Button.LCLICK",
            "Button.RCLICK",
            "Button.HOME",
            "Button.CAPTURE",
        ]
        self.Hat = ["TOP", "TOP_RIGHT", "RIGHT", "BTM_RIGHT", "BTM", "BTM_LEFT", "LEFT", "TOP_LEFT", "CENTER"]

    def openSerial(self, portNum: int, portName: str = "", baudrate: int = 9600) -> bool:
        """
        今の Data Format の送信方式で、ポートを開く。開けたかを返す(入力源の状態は、すべて捨てる)

        portNum: ポートの番号(COM の後ろの数字など)。portName が空の場合に使う
        portName: ポートの名前。指定した場合は、番号より、こちらで開く
        baudrate: ボーレート(使わない送信方式もある)
        """
        with self._lock:
            # 接続し直した(送信形式が変わった可能性がある)ので、入力源の状態は破棄する
            self._layers.clear()
            self._last_sent = None
            self._last_payload = None
            self._raw_write_warned = False
            # ポートの開き方は、送信方式で決まる(COMポート、FTDIのデバイスなど)
            return get_transport(KeyPress.serial_data_format_name).open(self, portNum, portName, baudrate)

    def transport(self) -> Transport:
        """
        今の送信方式(設定の Data Format。開いているポートが形式を決めている場合は、そちら)
        """
        return port_transport(self.ser, KeyPress.serial_data_format_name)

    def _openSerial(self, portNum: int, portName: str = "", baudrate: int = 9600) -> bool:
        """
        COM ポートを開いて self.ser に入れる。開けたかを返す(送信方式の open の既定が、これを呼ぶ)

        portName が空なら、OS に合わせた名前(COM / /dev/tty.usbserial- / /dev/ttyUSB + portNum)を
        開く。portName を指定した場合は、その名前で開く。どちらも、baudrate で開く
        """
        try:
            if portName is None or portName == "":
                if os.name == "nt":
                    print("connecting to " + "COM" + str(portNum) + "(" + str(baudrate) + ")")
                    self._logger.info("connecting to " + "COM" + str(portNum) + "(" + str(baudrate) + ")")
                    self.ser = serial.Serial("COM" + str(portNum), baudrate)
                    return True
                elif os.name == "posix":
                    if platform.system() == "Darwin":
                        print("connecting to " + "/dev/tty.usbserial-" + str(portNum) + "(" + str(baudrate) + ")")
                        self._logger.info(
                            "connecting to " + "/dev/tty.usbserial-" + str(portNum) + "(" + str(baudrate) + ")"
                        )
                        self.ser = serial.Serial("/dev/tty.usbserial-" + str(portNum), baudrate)
                        return True
                    else:
                        print("connecting to " + "/dev/ttyUSB" + str(portNum) + "(" + str(baudrate) + ")")
                        self._logger.info("connecting to " + "/dev/ttyUSB" + str(portNum) + "(" + str(baudrate) + ")")
                        self.ser = serial.Serial("/dev/ttyUSB" + str(portNum), baudrate)
                        return True
                else:
                    print("Not supported OS")
                    self._logger.warning("Not supported OS")
                    return False
            else:
                print("connecting to " + portName + "(" + str(baudrate) + ")")
                self._logger.info("connecting to " + portName + "(" + str(baudrate) + ")")
                self.ser = serial.Serial(portName, baudrate)
                return True
        except IOError as e:
            print("COM Port: can't be established")
            # 原因(ポート番号の間違い、ほかのアプリが使用中など)が分かるように、エラーの内容も表示する
            print(e)
            print(OPEN_FAILED_HINT)
            self._logger.error(f"COM Port: can't be established: {e}")
            return False

    def closeSerial(self) -> None:
        """ポートを閉じる(開いていない(self.ser が None の)場合は、何もしない)"""
        self._logger.debug("Closing the serial communication")
        with self._lock:
            self._last_sent = None
            self._last_payload = None
            if self.ser is not None:
                self.ser.close()

    def isOpened(self) -> bool:
        """ポートを開いているか"""
        self._logger.debug("Checking if serial communication is open")
        return True if self.ser is not None and self.ser.isOpen() else False

    def set_show_serial(self, show: bool) -> None:
        """
        送信したデータを表示するかを切り替える
        """
        self.show_serial = bool(show)

    def _on_show_serial_changed(self, *args: str) -> None:
        """Show Serial のチェックの変更を、show_serial に写す(args は、tkinter の trace が渡す値。使わない)"""
        # チェックボックス操作時にメインスレッドで呼ばれる
        self.show_serial = bool(self.is_show_serial.get())

    def _show_sent(self, value: str | bytes | list[int]) -> None:
        """
        送ったデータを、シリアルモニター(Output の Serial タブ)に渡す。Show Serial にチェックを入れている間は、標準出力にも表示する
        (シリアルモニターには、チェックに関係なく、いつも渡す。溜めるだけで、表示は画面の側が行う)
        value: 送った行(文字列)、または送ったデータ(bytes は 16 進で表示する)
        """
        if self.show_serial:
            print(value.hex(" ") if isinstance(value, bytes) else value)
        self.monitor.add(self.transport().name, value)

    ############### 入力源の合成 ###############
    def send_state(self, source: object, priority: int, state: dict) -> None:
        """
        入力源の現在の状態を登録し、全入力源を合成した状態を送信する
        source: 入力源を識別するオブジェクト(KeyPress, ProController等)
        priority: 入力源の優先度(InputSource)
        state: SendFormat.formatと同じ形式の状態(ボタンは現在の送信形式のビット配置)
        """
        state = OrderedDict((k, int(v)) for k, v in state.items())
        with self._lock:
            if _is_neutral(state):
                # ニュートラルになった入力源は外す
                self._layers.pop(source, None)
            else:
                layer = self._layers.get(source)
                if layer is None:
                    layer = _InputLayer(priority)
                    self._layers[source] = layer
                self._layer_seq += 1
                for name, (keys, _) in _EXCLUSIVE_GROUPS.items():
                    new = tuple(state[k] for k in keys)
                    if layer.state is None or new != tuple(layer.state[k] for k in keys):
                        layer.changed[name] = self._layer_seq
                layer.state = state
            self._send_merged()
            self._record()

    def release(self, source: object, end_row: str | None = None) -> bool:
        """
        入力源の登録を解除し、残りの入力源を合成した状態を送信する
        source: 入力源を識別するオブジェクト(send_state に渡したもの)
        end_row: 他の入力源が残っていない場合に、合成状態の代わりに送る行(Noneなら送らない)
        戻り値: 他の入力源が残っているか
        """
        with self._lock:
            removed = self._layers.pop(source, None) is not None
            remaining = bool(self._layers)
            if not remaining and end_row is not None:
                self.writeRow(end_row)
            elif removed:
                self._send_merged()
            self._record()
            return remaining

    def release_all(self, end_row: str | None = None) -> None:
        """
        すべての入力源の登録を解除して、何も押していない状態を送る(メニューの「すべての入力を離す」)
        end_row: 何も押していない状態の代わりに送る行(Default の形式の "end"。None なら、合成した状態を送る)
        """
        with self._lock:
            self._layers.clear()
            if end_row is not None:
                self._last_sent = None
                self.writeRow(end_row)
            else:
                self._send_merged()
            self._record()

    ############### 操作記録 ###############
    @property
    def recording(self) -> bool:
        """操作を記録している最中か"""
        return self._recorder is not None

    def start_recording(self, recorder: InputRecorder) -> None:
        """
        手動操作(キーボード・マウス・Proコントローラー)の記録を開始する
        recorder: 開始済み(start()済み)のInputRecorder
        """
        with self._lock:
            self._recorder = recorder
            # 開始時点で入力中の操作も記録する
            self._record()

    def stop_recording(self) -> InputRecorder | None:
        """
        記録を止めてInputRecorderを返す(自動化スクリプトの出力は呼び出し側でstop()を呼んで行う)
        """
        with self._lock:
            recorder, self._recorder = self._recorder, None
            return recorder

    def _record(self) -> None:
        """
        手動操作の入力源のみを合成した状態を記録に渡す(ロック内で呼ぶこと)
        """
        if self._recorder is None:
            return
        state = self._merge(manual_only=True)
        # ボタンは送信形式のビット配置になっているので、Buttonのビット配置に戻す
        buttons = revert_button_bits(state["btn"], get_button_conversion(KeyPress.serial_data_format_name))
        self._recorder.update_raw(
            buttons, state["hat"], state["lx"], state["ly"], state["rx"], state["ry"], state["sx"], state["sy"]
        )

    def _merge(self, manual_only: bool = False) -> OrderedDict:
        """
        入力源の状態を合成して返す(ロック内で呼ぶこと)。
        ボタンは論理和、十字キー・スティック・タッチは、倒されている入力源のうち優先度の高いもの
        (同じ優先度なら、後から変化したもの)
        manual_only: True では、手動操作の入力源(コマンド以外)だけを合成する
        """
        merged = _neutral_state()
        layers = list(self._layers.values())
        if manual_only:
            layers = [layer for layer in layers if layer.priority > InputSource.COMMAND]
        for layer in layers:
            merged["btn"] |= layer.state["btn"]
        for name, (keys, neutral) in _EXCLUSIVE_GROUPS.items():
            best = None
            for layer in layers:
                value = tuple(layer.state[k] for k in keys)
                if value == neutral:
                    continue
                rank = (layer.priority, layer.changed.get(name, 0))
                if best is None or rank > best[0]:
                    best = (rank, value)
            if best is not None:
                for k, v in zip(keys, best[1]):
                    merged[k] = v
        return merged

    def _send_merged(self) -> None:
        """
        合成した状態を現在の送信形式に変換して送信する(ロック内で呼ぶこと)
        """
        merged = self._merge()
        transport = self.transport()
        payload = transport.encode(merged, self._last_sent, self._encoder, self.ser)
        self._last_sent = merged
        if payload is None:
            return
        if transport.skip_unchanged:
            # 前回と同じデータなら送らない
            if payload == self._last_payload:
                return
            self._last_payload = payload
        if isinstance(payload, str):
            self._writeRow(payload)
        else:
            self._writeList(payload)

    def _blocks_raw_write(self) -> bool:
        """
        合成を経由しない送信を行わない送信方式の場合に、送信を止める(ロック内で呼ぶこと)
        戻り値: 送信を止めるか(止める場合は、接続ごとに 1 回だけ、その旨を表示する)
        """
        transport = self.transport()
        if transport.allows_raw_write:
            return False
        if not self._raw_write_warned:
            self._raw_write_warned = True
            print(transport.raw_write_message)
            self._logger.warning(transport.raw_write_log)
        return True

    def send_keyboard(self, item: str | tuple) -> None:
        """
        Switch へのキーボード入力の1手順を送る(送るものは、送信方式の keyboard_steps が決める)。
        文字列は行としてそのまま送り、値の組は、今のコントローラーの状態と一緒に送るデータにして送る
        item: keyboard_steps が返した手順の「送るもの」(待つ秒数は含まない。待つのは呼び出し側)
        """
        if isinstance(item, str):
            self.writeRow(item)
            return
        with self._lock:
            payload = self.transport().encode_keyboard(self._merge(), self._encoder, *item)
            if isinstance(payload, str):
                self._writeRow(payload)
            else:
                self._writeList(payload)

    ############### 送信 ###############
    # 以下の公開メソッドは入力源の合成を経由せずに送信する
    # (送信後のデバイスの状態が分からなくなるため、次回の合成送信ではスティックも送る)
    def writeRow(self, row: str, is_show: bool = False) -> None:
        """
        行を、合成を経由せずに送る(行末に改行を付ける)

        is_show: True では、前に送った行を、self.press(...) の形で表示する(show_input)
        """
        with self._lock:
            if self._blocks_raw_write():
                return
            self._last_sent = None
            self._writeRow(row, is_show)

    def writeList(self, values: list, is_show: bool = False) -> None:
        """数値のリスト(または bytes)を、合成を経由せずに、そのまま送る(is_show は使わない)"""
        with self._lock:
            if self._blocks_raw_write():
                return
            self._last_sent = None
            self._writeList(values, is_show)

    def writeRow_wo_perf_counter(self, row: str, is_show: bool = False) -> None:
        """
        行を、合成を経由せずに送る(送った時刻と行を覚えない版。is_show は使わない)
        """
        with self._lock:
            if self._blocks_raw_write():
                return
            self._last_sent = None
            self._writeRow_wo_perf_counter(row, is_show)

    def _sendSucceeded(self) -> None:
        """送れたとき: 続いていた失敗の回数を、0 に戻す"""
        if self._send_failures:
            self._send_failures = 0
            self._send_failures_reported = False

    def _sendFailed(self, error: Exception) -> None:
        """
        送信に失敗したとき: 続いた回数を数え、SEND_FAILURE_LIMIT 回になったら、on_send_failures を 1 回だけ呼ぶ
        (次に送れるまでは、もう呼ばない)
        """
        self._send_failures += 1
        if self._send_failures < SEND_FAILURE_LIMIT or self._send_failures_reported:
            return
        self._send_failures_reported = True
        callback = self.on_send_failures
        if callback is not None:
            try:
                callback(self._send_failures, error)
            except Exception:
                self._logger.exception("Failed to report the send failures")

    def _writeRow(self, row: str, is_show: bool = False) -> None:
        """
        行を送る(ロック内で呼ぶこと)。送信の例外は出さずに、ログに残す
        (ポートを開いていない場合は、その旨を表示する)
        """
        try:
            self.time_bef = time.perf_counter()
            if self.before is not None and self.before != "end" and is_show:
                output = self.before.split(" ")
                self.show_input(output)

            self.ser.write((row + "\r\n").encode("utf-8"))
            self.time_aft = time.perf_counter()
            self.before = row
            self._sendSucceeded()
        except serial.serialutil.SerialException as e:
            # print(e)
            self._logger.error(f"Error : {e}")
            self._sendFailed(e)
        except AttributeError as e:
            print("Using a port that is not open.")
            self._logger.error("Maybe Using a port that is not open.")
            self._logger.error(e)
        # self._logger.debug(f"{row}")
        # Show sending serial datas
        self._show_sent(row)

    def _writeList(self, values: list | bytes, is_show: bool = False) -> None:
        """数値のリスト・bytes を、そのまま送る(ロック内で呼ぶこと)。送信の例外は出さずに、ログに残す"""
        try:
            self.time_bef = time.perf_counter()
            if self.before is not None and self.before != "end" and is_show:
                pass

            self.ser.write(values)
            self.time_aft = time.perf_counter()
            self.before = values
            self._sendSucceeded()
        except (serial.serialutil.SerialException, FtdiError) as e:
            # print(e)
            self._logger.error(f"Error : {e}")
            self._sendFailed(e)
        except AttributeError as e:
            print("Using a port that is not open.")
            self._logger.error("Maybe Using a port that is not open.")
            self._logger.error(e)
        # self._logger.debug(f"{values}")
        # Show sending serial datas
        self._show_sent(values)

    def _writeRow_wo_perf_counter(self, row: str, is_show: bool = False) -> None:
        """行を送る(ロック内で呼ぶこと)。送った時刻と行は覚えない。送信の例外は、表示してログに残す"""
        try:
            self.ser.write((row + "\r\n").encode("utf-8"))
            self._sendSucceeded()
        except serial.serialutil.SerialException as e:
            # エラーはあえてprintでも出す。
            print(e)
            self._logger.error(f"Error : {e}")
            self._sendFailed(e)
        except AttributeError as e:
            print("Using a port that is not open.")
            self._logger.error("Maybe Using a port that is not open.")
            self._logger.error(e)
        # self._logger.debug(f"{row}")
        # Show sending serial datas
        self._show_sent(row)

    def show_input(self, output: List[str]) -> None:
        """
        Default の形式の行を読み解いて、押していた入力を self.press(..., duration=...) の形で表示する
        (手で操作した内容を、スクリプトに写すためのもの。is_print が False なら表示しない)

        output: 行を空白で分けたもの(ボタン(16 進)、十字キー、左X、左Y、右X、右Y)。
                スティックの値は、印の付いた側だけが付いている行(左X 左Y だけ、右X 右Y だけ、なし)も読める
        ボタンの下位 2 ビットは、スティックの値が付いているかの印(0x2: 左、0x1: 右)で、ボタンとしては表示しない。
        印のある行では、倒しているスティックを Direction(Stick.LEFT / Stick.RIGHT, 角度) として一緒に表示し、
        倒したままのスティックとして覚える(値の付いていない側は、前に覚えたままにする)。
        印のない行では、覚えているスティックを一緒に表示する。
        読み解けない行の例外は出さずに、ログに残す
        """
        try:
            flags = int(output[0], 16)
            useRStick = flags >> 0 & 1
            useLStick = flags >> 1 & 1
            # ボタン(印の 2 ビットを除く)と、十字キー
            btns = [self.Buttons[x] for x in range(2, 16) if flags >> x & 1]
            Hat = self.Hat[int(output[1])]
            if Hat != "CENTER":
                btns = btns + ["Hat." + str(Hat)]
            # スティックの値(その行に付いていない側は None)。
            # 4 つあれば 左・右 の順。2 つ以下のときは、印の付いた側の値だけが、左・右 の順に並んでいる
            values = [int(x, 16) for x in output[2:]]
            LStick = RStick = None
            if len(values) >= 4:
                LStick, RStick = values[0:2], values[2:4]
            else:
                if useLStick and len(values) >= 2:
                    LStick, values = values[0:2], values[2:]
                if useRStick and len(values) >= 2:
                    RStick = values[0:2]
            if not self.is_print:
                return

            def direction(stick: str, degree: float) -> str:
                """スティックの向きを、Direction(スティック, 角度) の形の文字にする"""
                return "Direction({}, {:.0f})".format(stick, degree)

            def degree(stick: list) -> float:
                """スティックの値(X, Y)を、角度(度。0 が右、90 が上)にする"""
                return math.degrees(math.atan2(128 - stick[1], stick[0] - 128))

            items = list(btns)
            if useLStick or useRStick:
                # スティックの値が付いている行: 倒しているスティックを表示し、倒したままのスティックとして覚える
                # (値の付いていない側は、前に覚えた状態のまま)
                if RStick is not None:
                    self.R_holding = RStick != [128, 128]
                    if self.R_holding:
                        self._R_holding = degree(RStick)
                if LStick is not None:
                    self.L_holding = LStick != [128, 128]
                    if self.L_holding:
                        self._L_holding = degree(LStick)
                if self.R_holding:
                    items.append(direction("Stick.RIGHT", self._R_holding))
                if self.L_holding:
                    items.append(direction("Stick.LEFT", self._L_holding))
            else:
                # スティックの値が付いていない行: 倒したままのスティックがあれば、一緒に表示する
                if self.L_holding:
                    items.append(direction("Stick.LEFT", self._L_holding))
                elif self.R_holding:
                    items.append(direction("Stick.RIGHT", self._R_holding))
                if not btns:
                    # 何も押していない行で、スティックが中央なら、倒したままの扱いをやめる
                    if LStick == [128, 128]:
                        self.L_holding = False
                    if RStick == [128, 128]:
                        self.R_holding = False

            if not items:
                return
            duration = self.time_bef - self.time_aft
            if len(items) == 1:
                text = "self.press({}, duration={:.2f})".format(items[0], duration)
            else:
                text = "self.press([{}], duration={:.2f})".format(", ".join(items), duration)
            print(text)
            self._logger.debug(text)
        except Exception as e:
            self._logger.error(f"Error: {e}")
