#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FTDI(FT232H等)のGPIOにDSのボタンを直結した基板への送信

- マイコンは無く、MPSSEモードのコマンドでピンの状態を直接書き換える
    0x82, 値, 方向 : Cバス(ACBUS0-7)
    0x80, 値, 方向 : Dバス(ADBUS0-7)
  押しているボタンのピンは「出力・Low」、離しているピンは「入力(ハイインピーダンス)」にする
- 基板は配線の違いで3種類(Rev1 / Rev2 / Rev3)ある
- 対応する入力はボタンと十字キーのみ(スティック・タッチは配線が無い)

FTDIのD2XXドライバーを使うため、ftd2xxパッケージが必要(pip install ftd2xx)。
ftd2xxが無い環境でも、このモジュールは読み込める(FTDI_AVAILABLEがFalseになる)。
"""
from __future__ import annotations

import time
from logging import getLogger, DEBUG, NullHandler

from Commands.Keys import FTDI_FORMAT_PREFIX, Button, Hat

try:
    import ftd2xx

    FTDI_AVAILABLE = True
    FTDI_IMPORT_ERROR = None
except Exception as e:  # パッケージが無い場合のほか、ドライバー(ftd2xx.dll)が無い場合も含む
    ftd2xx = None
    FTDI_AVAILABLE = False
    FTDI_IMPORT_ERROR = e

_logger = getLogger(__name__)
_logger.addHandler(NullHandler())
_logger.setLevel(DEBUG)
_logger.propagate = True

# MPSSEのコマンド
SET_BITS_HIGH = 0x82  # Cバス(ACBUS)の値・方向を設定
SET_BITS_LOW = 0x80  # Dバス(ADBUS)の値・方向を設定
# MPSSEの同期確認に使う、存在しないコマンドと、それに対する応答
BAD_COMMAND = 0xAA
BAD_COMMAND_RESPONSE = b"\xfa\xaa"

# ビットモード
BITMODE_RESET = 0x00
BITMODE_MPSSE = 0x02
# FT_Purgeの対象(受信・送信の両方)
PURGE_RX_TX = 1 | 2
# 入力の遅延を小さくするための遅延タイマー(ms)
LATENCY_TIMER_MS = 1
# モードの切り替え後に待つ時間(秒)
MODE_SETTLE_TIME = 0.05

# MPSSEモードに対応したチップの種類(ftd2xxのデバイス種別) -> 名前
MPSSE_DEVICE_TYPES = {6: "FT2232H", 7: "FT4232H", 8: "FT232H"}
# デバイス一覧のflagsのうち、他のプログラムが開いていることを表すビット
FLAG_OPENED = 0x01

# 全ピンを離した状態(全ビット1 = 入力)
ALL_RELEASED = 0xFF

# リビジョン共通の配線
_COMMON_PINS = {
    "LEFT": "C0",
    "DOWN": "C1",
    "RIGHT": "C2",
    "UP": "C3",
    "A": "C4",
    "L": "D0",
    "R": "D1",
    "SELECT": "D2",
    "START": "D3",
    "POWER": "D4",
}
# リビジョン -> 入力名 -> ピン(バスとビット番号)。リビジョンで違うのは B / X / Y のみ
FTDI_PIN_MAPS = {
    "Rev1": {**_COMMON_PINS, "B": "C5", "X": "C6", "Y": "C7"},
    "Rev2": {**_COMMON_PINS, "B": "D6", "X": "D7", "Y": "D5"},
    "Rev3": {**_COMMON_PINS, "B": "C5", "X": "C6", "Y": "D5"},
}
# Data Formatの名前 -> リビジョン
FTDI_FORMATS = {f"{FTDI_FORMAT_PREFIX} ({rev})": rev for rev in FTDI_PIN_MAPS}

# 入力名 -> Button (STARTはPLUS、SELECTはMINUS、POWERはLCLICKの別名)
_BUTTONS = {
    "A": Button.A,
    "B": Button.B,
    "X": Button.X,
    "Y": Button.Y,
    "L": Button.L,
    "R": Button.R,
    "SELECT": Button.SELECT,
    "START": Button.START,
    "POWER": Button.POWER,
}
# Hat -> 押す十字キー(斜めは2つ同時)
_HAT_DIRECTIONS = {
    Hat.TOP: ("UP",),
    Hat.TOP_RIGHT: ("UP", "RIGHT"),
    Hat.RIGHT: ("RIGHT",),
    Hat.BTM_RIGHT: ("DOWN", "RIGHT"),
    Hat.BTM: ("DOWN",),
    Hat.BTM_LEFT: ("DOWN", "LEFT"),
    Hat.LEFT: ("LEFT",),
    Hat.TOP_LEFT: ("UP", "LEFT"),
    Hat.CENTER: (),
}


class FtdiError(Exception):
    """FTDI のデバイスを開けない・送れない場合の例外(文は、利用者に見せる日本語)"""

    pass


def get_pin_map(format_name: str) -> dict:
    """
    Data Format の名前(FTDI_FORMATS のキー)から、入力名 -> ピン("C5" など)の対応を返す。
    登録のない名前は KeyError
    """
    return FTDI_PIN_MAPS[FTDI_FORMATS[format_name]]


def encode_pin_states(buttons: int, hat: int, pin_map: dict) -> bytes:
    """
    入力状態を、送信する6バイト(Cバス・Dバスの値と方向)に変換する
    buttons: Buttonのビット列(Default形式のビット配置)
    hat: Hatの値
    pin_map: 入力名 -> ピン(get_pin_map の戻り値)
    割り当ての無い入力(HOME、ZL/ZR等)は無視する
    """
    pressed = [name for name, button in _BUTTONS.items() if buttons & int(button)]
    pressed += _HAT_DIRECTIONS.get(Hat(int(hat)), ())
    # 1 = 離している(入力)、0 = 押している(出力・Low)
    states = {"C": ALL_RELEASED, "D": ALL_RELEASED}
    for name in pressed:
        pin = pin_map.get(name)
        if pin is not None:
            states[pin[0]] &= ~(1 << int(pin[1])) & 0xFF
    c, d = states["C"], states["D"]
    # 値は離しているピンを1に、方向は押しているピンのみ出力(1)にする
    return bytes([SET_BITS_HIGH, c, ~c & 0xFF, SET_BITS_LOW, d, ~d & 0xFF])


RELEASED_DATA = encode_pin_states(0, Hat.CENTER, {})


class FtdiPort:
    """
    MPSSEモードで開いたFTDIデバイス(pyserialのポートと同じ write / isOpen / close を持つ)
    """

    def __init__(self, device: object, format_name: str, description: str = "") -> None:
        """
        device: ftd2xx.open で開いたデバイス(ftd2xx が無い環境でも読み込めるよう、型は object)
        format_name: Data Format の名前(FTDI_FORMATS のキー。登録のない名前は KeyError)
        description: 表示用の説明(チップの種類、COM ポート、シリアル番号)
        """
        self._device = device
        self.format_name = format_name
        self.pin_map = get_pin_map(format_name)
        self.description = description

    def setup(self) -> None:
        """
        MPSSEモードに切り替え、全ピンを離した状態にする
        (MPSSE の応答がない場合は FtdiError。ドライバーの例外は、そのまま出る)
        """
        dev = self._device
        dev.resetDevice()
        dev.setUSBParameters(65536, 65536)
        dev.setChars(0, 0, 0, 0)
        dev.setTimeouts(1000, 1000)
        dev.setLatencyTimer(LATENCY_TIMER_MS)
        dev.setBitMode(0x00, BITMODE_RESET)
        dev.setBitMode(0x00, BITMODE_MPSSE)
        time.sleep(MODE_SETTLE_TIME)
        dev.purge(PURGE_RX_TX)
        # 最初に全ピンを離した状態にする
        dev.write(RELEASED_DATA)
        self._check_mpsse()

    def _check_mpsse(self) -> None:
        """
        存在しないコマンドを送り、MPSSEのエラー応答が返ることを確認する(ピンの状態は変わらない)
        0.5 秒以内に応答がなければ FtdiError
        """
        dev = self._device
        dev.write(bytes([BAD_COMMAND]))
        response = b""
        deadline = time.perf_counter() + 0.5
        while time.perf_counter() < deadline and BAD_COMMAND_RESPONSE not in response:
            waiting = dev.getQueueStatus()
            if waiting:
                response += dev.read(waiting)
            else:
                time.sleep(0.005)
        if BAD_COMMAND_RESPONSE not in response:
            raise FtdiError(f"MPSSEモードの応答がありません (応答: {response.hex(' ') or 'なし'})")

    def write(self, data: bytes | list[int]) -> int:
        """
        データ(bytes、または 0 - 255 の数値の並び)を、そのまま送る。戻り値は、書き込んだバイト数。
        閉じた後と、送信に失敗した場合は FtdiError
        """
        if self._device is None:
            raise FtdiError("FTDIデバイスは開かれていません")
        try:
            return self._device.write(bytes(data))
        except Exception as e:
            raise FtdiError(f"FTDIデバイスへの送信に失敗しました: {e}") from e

    def isOpen(self) -> bool:
        """開いているか(close を呼ぶまで True)"""
        return self._device is not None

    def close(self) -> None:
        """
        全ピンを離した状態にしてから閉じる
        (ビットモードは戻さない。戻すとUARTの出力ピンが駆動されるため、入力のままにしておく)
        """
        dev, self._device = self._device, None
        if dev is None:
            return
        try:
            dev.write(RELEASED_DATA)
        except Exception as e:
            _logger.error(f"Failed to release the pins: {e}")
        try:
            dev.close()
        except Exception as e:
            _logger.error(f"Failed to close the FTDI device: {e}")


def list_devices() -> list[dict]:
    """
    接続中のFTDIデバイスの一覧(デバイスは開かない)
    要素は ftd2xx.getDeviceInfoDetail の戻り値(type、serial、flags などを持つ dict)。ftd2xx が無ければ空
    """
    if not FTDI_AVAILABLE:
        return []
    count = ftd2xx.createDeviceInfoList()
    return [ftd2xx.getDeviceInfoDetail(i, update=False) for i in range(count)]


def open_ftdi_port(com_port: int, format_name: str) -> FtdiPort:
    """
    COMポート番号に対応するFTDIデバイスをMPSSEモードで開く
    - 基板にシリアル番号が書き込まれていない場合があるため、MPSSE対応のデバイスを順に開いて
      COMポート番号を問い合わせ、一致するものを使う
    com_port: COM ポートの番号(COM3 なら 3)
    format_name: Data Format の名前(FTDI_FORMATS のキー)
    ftd2xx が無い、一致するデバイスが無い、MPSSE モードにできない場合は FtdiError
    """
    if not FTDI_AVAILABLE:
        raise FtdiError(f"ftd2xxを読み込めません ({FTDI_IMPORT_ERROR})。pip install ftd2xx でインストールしてください。")
    try:
        devices = list_devices()
    except Exception as e:
        raise FtdiError(f"FTDIデバイスの一覧を取得できません: {e}") from e

    others = []
    for index, info in enumerate(devices):
        type_name = MPSSE_DEVICE_TYPES.get(info["type"])
        if type_name is None:
            # MPSSE非対応(FT232R等)。開かない
            continue
        try:
            device = ftd2xx.open(index)
        except Exception as e:
            others.append(f"#{index} {type_name}: 開けません ({e})")
            continue
        try:
            port_number = device.getComPortNumber()
        except Exception:
            port_number = -1
        if port_number != com_port:
            device.close()
            others.append(f"#{index} {type_name}: COM{port_number}")
            continue
        serial = info["serial"].decode(errors="replace") or "なし"
        port = FtdiPort(device, format_name, f"{type_name} (COM{com_port}, シリアル番号: {serial})")
        try:
            port.setup()
        except Exception as e:
            port.close()
            raise FtdiError(f"{port.description} をMPSSEモードにできません: {e}") from e
        return port

    detail = f" (MPSSE対応のデバイス: {', '.join(others)})" if others else ""
    raise FtdiError(f"COM{com_port} に、MPSSEモードに対応したFTDIデバイス(FT232H等)が見つかりません{detail}")
