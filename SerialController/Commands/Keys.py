#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import TYPE_CHECKING, Sequence

import math
import time
from collections import OrderedDict
from enum import Enum, IntEnum, IntFlag, auto
import queue
from logging import getLogger, DEBUG, NullHandler

if TYPE_CHECKING:
    from Commands.Sender import Sender
    from Commands.transport import Transport

# ロガーの設定は1回だけ行う
# (SendFormat・Direction・Touchscreenは操作のたびに作られるため、
#  生成毎にaddHandlerするとハンドラが増え続けて送信が遅くなる)
_logger = getLogger(__name__)
_logger.addHandler(NullHandler())
_logger.setLevel(DEBUG)
_logger.propagate = True


class Button(IntFlag):
    """ボタン(値は、Default の形式で送るビット。| で組み合わせられる)。後ろの 4 つは 3DS 用の別名"""

    Y = auto()  # 1
    B = auto()  # 2
    A = auto()  # 3
    X = auto()  # 4
    L = auto()  # 5
    R = auto()  # 6
    ZL = auto()  # 7
    ZR = auto()  # 8
    MINUS = auto()  # 9
    PLUS = auto()  # 10
    LCLICK = auto()  # 11
    RCLICK = auto()  # 12
    HOME = auto()  # 13
    CAPTURE = auto()  # 14
    SELECT = MINUS  # for 3DS, 9
    START = PLUS  # for 3DS, 10
    POWER = LCLICK  # for 3DS, 11
    WIRELESS = RCLICK  # for 3DS, 12


# 3DS Controller用にビット位置を並び替えるためのdict
conversion_default_button = {
    Button.Y: Button.Y,
    Button.B: Button.B,
    Button.A: Button.A,
    Button.X: Button.X,
    Button.L: Button.L,
    Button.R: Button.R,
    Button.ZL: Button.ZL,
    Button.ZR: Button.ZR,
    Button.MINUS: Button.MINUS,
    Button.PLUS: Button.PLUS,
    Button.LCLICK: Button.LCLICK,
    Button.RCLICK: Button.RCLICK,
    Button.HOME: Button.HOME,
    Button.CAPTURE: Button.CAPTURE,
    Button.SELECT: Button.SELECT,
    Button.START: Button.START,
    Button.POWER: Button.POWER,
    Button.WIRELESS: Button.WIRELESS,
}

conversion_3ds_controller_button = {
    Button.A: 1,
    Button.B: 2,
    Button.X: 4,
    Button.Y: 8,
    Button.L: 16,
    Button.R: 32,
    Button.HOME: 64,
    Button.START: 128,
    Button.SELECT: 256,
    Button.POWER: 512,
    Button.MINUS: 256,
    Button.PLUS: 128,
    Button.LCLICK: 512,
    Button.RCLICK: 0,
    Button.ZL: 0,
    Button.ZR: 0,
    Button.CAPTURE: 0,
    Button.WIRELESS: 0,
}


class Hat(IntEnum):
    """十字キーの向き(0: 上 から時計回りに 7: 左上。8: 押していない)"""

    TOP = 0  # 8
    TOP_RIGHT = 1
    RIGHT = 2  # 4
    BTM_RIGHT = 3
    BTM = 4  # 2
    BTM_LEFT = 5
    LEFT = 6  # 1
    TOP_LEFT = 7
    CENTER = 8  # 0


convert_hat_default = range(0, 9)
convert_hat_3ds_controller = [8, 0, 4, 0, 2, 0, 1, 0, 0]


class InputSource(IntEnum):
    """
    シリアル送信の入力源(値が大きいほど優先度が高い)
    Hat・スティック・タッチは、倒されている入力源のうち優先度の高いものを採用する
    ボタンは全入力源の論理和を採用する
    """

    COMMAND = 0  # 自動化スクリプト
    KEYBOARD = 1  # pynput
    MOUSE = 2  # メイン画面のマウス操作(Software Controller, Switch Controller Simulatorを含む)
    PROCON = 3  # Proコントローラー


# FTDIのGPIOにボタンを直結した基板用のData Formatの名前の先頭
# (既存の"3DS Controller"の判定に一致しない名前にすること)
FTDI_FORMAT_PREFIX = "DS FT"


def is_ftdi_format(serial_data_format_name: str) -> bool:
    """
    FTDIのGPIOにボタンを直結した基板用のData Formatか
    """
    return serial_data_format_name.startswith(FTDI_FORMAT_PREFIX)


def _transport(serial_data_format_name: str) -> Transport:
    """
    送るデータの形式の送信方式(Commands/transport)を返す
    (送信方式の側がこのファイルを読み込むので、ここでは使うときに読み込む)
    """
    from Commands.transport import get_transport

    return get_transport(serial_data_format_name)


def get_button_conversion(serial_data_format_name: str) -> dict:
    """
    送信形式に応じたボタンのビット変換表を返す(Button -> 送るビット)
    """
    return _transport(serial_data_format_name).button_conversion


def convert_button_bits(bits: int, convert: dict = conversion_default_button) -> int:
    """
    Buttonのビット列を送信形式のビット列に変換する
    """
    ret = 0
    for i in range(bits.bit_length()):
        if bits >> i & 1:
            ret |= int(convert.get(Button(1 << i), 0))
    return ret


def revert_button_bits(bits: int, convert: dict = conversion_default_button) -> int:
    """
    送信形式のビット列をButtonのビット列に戻す(convert_button_bitsの逆。変換先が0のボタンは戻せない)
    """
    ret = 0
    for button, value in convert.items():
        if int(value) != 0 and bits & int(value):
            ret |= int(button)
    return ret


class Stick(Enum):
    """スティックの左右(Direction の 1 つ目の引数に渡す)"""

    LEFT = auto()
    RIGHT = auto()


class Tilt(Enum):
    """スティックが倒れている向き(R_ の付くものは右スティック)。離す軸を決めるのに使う"""

    UP = auto()
    RIGHT = auto()
    DOWN = auto()
    LEFT = auto()
    R_UP = auto()
    R_RIGHT = auto()
    R_DOWN = auto()
    R_LEFT = auto()


# direction value definitions
min = 0
center = 128
max = 255


# serial format
class SendFormat:
    """
    コントローラーの 1 つの状態(ボタン、十字キー、左右のスティック、タッチスクリーン)と、
    それを送るデータ(Default の行、Qingpi・3DS Controller の 11 バイト)へ直す処理
    """

    def __init__(self) -> None:
        """何も押していない状態で作る(スティックは中央の 128、タッチは 0)"""
        self._logger = _logger

        # This format structure needs to be the same as the one written in Joystick.c
        self.format = OrderedDict(
            [
                ("btn", 0),  # send bit array for buttons
                ("hat", Hat.CENTER),
                ("lx", center),
                ("ly", center),
                ("rx", center),
                ("ry", center),
                ("sx", 0),
                ("sy", 0),
            ]
        )

        self.L_stick_changed = False
        self.R_stick_changed = False
        self.Hat_pos = Hat.CENTER

    def setButton(self, btns: list[Button], convert: dict = conversion_default_button) -> None:
        """btns のボタンを押した状態にする(convert: Button -> 送るビット の対応)"""
        for btn in btns:
            self.format["btn"] |= convert[btn]

    def unsetButton(self, btns: list[Button], convert: dict = conversion_default_button) -> None:
        """btns のボタンを離した状態にする(convert: Button -> 送るビット の対応)"""
        for btn in btns:
            self.format["btn"] &= ~convert[btn]

    def resetAllButtons(self) -> None:
        """すべてのボタンを離した状態にする"""
        self.format["btn"] = 0

    def setHat(self, btns: list[Hat], convert: Sequence[int] = convert_hat_default) -> None:
        """
        十字キーを、btns の先頭の向きにする(2 つ目以降は使わない)。
        btns が空のときは、最後に設定した向きのままにする
        convert: Hat の値 -> 送る値 の対応
        """
        # self._logger.debug(btns)
        if not btns:
            self.format["hat"] = self.Hat_pos
        else:
            self.Hat_pos = convert[btns[0]]
            self.format["hat"] = convert[btns[0]]  # takes only first element

    def unsetHat(self, convert: Sequence[int] = convert_hat_default) -> None:
        """十字キーを、押していない状態にする(convert: Hat の値 -> 送る値 の対応)"""
        # if self.Hat_pos is not Hat.CENTER:
        self.Hat_pos = convert[Hat.CENTER]
        self.format["hat"] = self.Hat_pos

    def setAnyDirection(self, dirs: list[Direction], x_reverse: bool = False, y_reverse: bool = False) -> None:
        """
        スティックを、dirs の向きに倒した状態にする(左右は、それぞれの Direction の stick で決まる)

        Direction の y は上が大きいが、送る値は下が大きいので、Y は 255 から引いて入れる。
        x_reverse / y_reverse: True にすると、その軸の向きを逆にする
        変化の印(L_stick_changed / R_stick_changed)は、入れる値(逆にした後の値)が、今の値と違うときに立てる
        """
        for dir in dirs:
            x = dir.x if not x_reverse else 255 - dir.x
            y = 255 - dir.y if not y_reverse else dir.y  # NOTE: y axis directs under
            if dir.stick == Stick.LEFT:
                if self.format["lx"] != x or self.format["ly"] != y:
                    self.L_stick_changed = True

                self.format["lx"] = x
                self.format["ly"] = y
            elif dir.stick == Stick.RIGHT:
                if self.format["rx"] != x or self.format["ry"] != y:
                    self.R_stick_changed = True

                self.format["rx"] = x
                self.format["ry"] = y

    def unsetDirection(self, dirs: list[Tilt]) -> None:
        """
        dirs にある向きの軸を、中央に戻す(Direction.getTilting の戻り値を渡す)。
        戻した軸と同じスティックの、もう一方の軸は、倒れていれば端(0 か 255)に寄せる
        """
        if Tilt.UP in dirs or Tilt.DOWN in dirs:
            self.format["ly"] = center
            self.format["lx"] = self.fixOtherAxis(self.format["lx"])
            self.L_stick_changed = True
        if Tilt.RIGHT in dirs or Tilt.LEFT in dirs:
            self.format["lx"] = center
            self.format["ly"] = self.fixOtherAxis(self.format["ly"])
            self.L_stick_changed = True
        if Tilt.R_UP in dirs or Tilt.R_DOWN in dirs:
            self.format["ry"] = center
            self.format["rx"] = self.fixOtherAxis(self.format["rx"])
            self.R_stick_changed = True
        if Tilt.R_RIGHT in dirs or Tilt.R_LEFT in dirs:
            self.format["rx"] = center
            self.format["ry"] = self.fixOtherAxis(self.format["ry"])
            self.R_stick_changed = True

    # Use this to fix an either tilt to max when the other axis sets to 0
    def fixOtherAxis(self, fix_target: int) -> int:
        """軸の値を、中央ならそのまま、中央より小さければ 0、大きければ 255 にして返す"""
        if fix_target == center:
            return center
        else:
            return 0 if fix_target < center else 255

    def resetAllDirections(self) -> None:
        """左右のスティックを中央に戻す(覚えている十字キーの向きも、押していない状態に戻す)"""
        self.format["lx"] = center
        self.format["ly"] = center
        self.format["rx"] = center
        self.format["ry"] = center
        self.L_stick_changed = True
        self.R_stick_changed = True
        self.Hat_pos = Hat.CENTER

    def setTouchscreen(self, dirs: list[Touchscreen]) -> None:
        """タッチの位置を、dirs の先頭の位置にする(空なら変えない。2 つ目以降は使わない)"""
        if not dirs:
            pass
        else:
            self.format["sx"] = dirs[0].x  # takes only first element
            self.format["sy"] = dirs[0].y  # takes only first element

    def unsetTouchscreen(self) -> None:
        """タッチを離した状態(0, 0)にする"""
        self.format["sx"] = 0
        self.format["sy"] = 0

    def convert2str(self) -> str:
        """
        今の状態を、Default の形式の行にする(行末の改行は付けない)

        "ボタン(16 進 4 桁) 十字キー [左X 左Y] [右X 右Y]" の形。ボタンは 2 ビット左へずらし、
        下位 2 ビットに「左スティックを送る(0x2)」「右スティックを送る(0x1)」の印を入れる。
        スティックは、変化の印(L_stick_changed / R_stick_changed)が立っている側だけを付け、印は下ろす
        """
        str_format = ""
        str_L = ""
        str_R = ""
        str_Hat = ""
        space = " "

        # set bits array with stick flags
        send_btn = int(self.format["btn"]) << 2
        # send_btn |= 0x3
        if self.L_stick_changed:
            send_btn |= 0x2
            str_L = (
                format(self.format["lx"], "x") + space + format(self.format["ly"], "x")
            )
        if self.R_stick_changed:
            send_btn |= 0x1
            str_R = (
                format(self.format["rx"], "x") + space + format(self.format["ry"], "x")
            )
        # if self.Hat_changed:
        str_Hat = str(int(self.format["hat"]))
        # format(send_btn, 'x') + \
        # print(hex(send_btn))
        str_format = (
            format(send_btn, "#06x")
            + (space + str_Hat)
            + (space + str_L if self.L_stick_changed else "")
            + (space + str_R if self.R_stick_changed else "")
        )

        self.L_stick_changed = False
        self.R_stick_changed = False

        # print(str_format)
        return str_format  # the last space is not needed

    def convert2list(self) -> list[int]:
        """
        For Qingpi
        (11 個の数値: 0xAB、ボタン 2、十字キー、左X、左Y、右X・右Y は中央で固定、タッチX 2、タッチY)
        """
        header = 0xAB  # fixed value
        send_btn = int(self.format["btn"])
        send_hat = int(self.format["hat"])
        send_lstick_x = self.format["lx"]
        send_lstick_y = self.format["ly"]
        send_touch_x = int(self.format["sx"])
        send_touch_y = int(self.format["sy"])

        state = [
            header,
            send_btn & 0xFF,
            (send_btn >> 8) & 0xFF,
            send_hat,
            send_lstick_x,
            send_lstick_y,
            center,
            center,
            send_touch_x & 0xFF,
            (send_touch_x >> 8) & 0xFF,
            send_touch_y,
        ]

        return state

    def convert2list2(self, mode: int = 0) -> list[int]:
        """
        For 3DS Controller
        mode: 0(FW:-x.3), 1(FW:x.4-)
        (11 個の数値: 0xA1、ボタンと十字キー 2、0xA2、左X、左Y、0xB2、タッチの有無、タッチX 2、タッチY)
        """
        header = 0xA1  # fixed value
        send_btn = int(self.format["btn"])
        send_hat = convert_hat_3ds_controller[int(self.format["hat"])]

        header2 = 0xA2  # fixed value
        if mode == 0:
            # FW:-x.3
            send_lx = (
                self.format["lx"]
                if self.format["lx"] >= 128
                else 127 - self.format["lx"]
            )
            send_ly = (
                self.format["ly"]
                if self.format["ly"] >= 128
                else 127 - self.format["ly"]
            )
        else:
            # FW:x.4-
            send_lx = 255 - self.format["lx"]
            send_ly = 255 - self.format["ly"]

        header3 = 0xB2
        send_touch_x = int(self.format["sx"])
        send_touch_y = int(self.format["sy"])
        touchon = 0
        if send_touch_x != 0 or send_touch_y != 0:
            touchon = 1

        state = [
            header,
            ((send_btn & 0xF) << 4) | send_hat,
            (send_btn >> 4) & 0x3F,
            header2,
            send_lx,
            send_ly,
            header3,
            touchon,
            (send_touch_x >> 8) & 0xFF,
            send_touch_x & 0xFF,
            send_touch_y,
        ]

        return state


# This class handle L stick and R stick at any angles
class Direction:
    """
    スティックを倒す向きと量(左右どちらのスティックでも、好きな角度で表せる)。
    Direction.UP、Direction.R_LEFT などの、よく使う向きは、このクラスの下で定義している
    """

    def __init__(
        self,
        stick: Stick,
        angle: float | tuple[int, int],
        magnification: float = 1.0,
        isDegree: bool = True,
        showName: str | None = None,
    ) -> None:
        """
        stick: 左右どちらのスティックか
        angle: 角度(0 が右、90 が上)。(X, Y) の組を渡すと、その値(0 - 255。Y は上が大きい)をそのまま使う
        magnification: 倒す量(0.0 - 1.0。範囲の外は、端の値にする)。(X, Y) を渡した場合は使わない
        isDegree: angle の単位(True: 度、False: ラジアン)
        showName: 表示に使う名前(None: 角度を表示する)
        """
        self._logger = _logger

        self.stick = stick
        self.angle_for_show = angle
        self.showName = showName
        if magnification > 1.0:
            self.mag = 1.0
        elif magnification < 0:
            self.mag = 0.0
        else:
            self.mag = magnification

        if isinstance(angle, tuple):
            # assuming (X, Y)
            self.x = angle[0]
            self.y = angle[1]
            self.showName = "(" + str(self.x) + ", " + str(self.y) + ")"
            print("押し込み量", self.showName)
        else:
            angle = math.radians(angle) if isDegree else angle

            # We set stick X and Y from 0 to 255, so they are calculated as below.
            # X = 127.5*cos(theta) + 127.5
            # Y = 127.5*sin(theta) + 127.5
            self.x = math.ceil(127.5 * math.cos(angle) * self.mag + 127.5)
            self.y = math.floor(127.5 * math.sin(angle) * self.mag + 127.5)

    def __repr__(self) -> str:
        """表示用の文字列("<Stick.LEFT, UP>" や "<Stick.LEFT, 30[deg]>")"""
        if self.showName:
            return "<{}, {}>".format(self.stick, self.showName)
        else:
            return "<{}, {}[deg]>".format(self.stick, self.angle_for_show)

    def __eq__(self, other: object) -> bool:
        """同じスティックで、渡された角度(または (X, Y))が同じなら等しい(倒す量は比べない)"""
        if not isinstance(other, Direction):
            return False

        if self.stick == other.stick and self.angle_for_show == other.angle_for_show:
            return True
        else:
            return False

    def getTilting(self) -> list[Tilt]:
        """倒れている向きの一覧(X と Y の軸ごと。中央の軸は入らない)"""
        tilting = []
        if self.stick == Stick.LEFT:
            if self.x < center:
                tilting.append(Tilt.LEFT)
            elif self.x > center:
                tilting.append(Tilt.RIGHT)

            if self.y < center - 1:
                tilting.append(Tilt.DOWN)
            elif self.y > center - 1:
                tilting.append(Tilt.UP)
        elif self.stick == Stick.RIGHT:
            if self.x < center:
                tilting.append(Tilt.R_LEFT)
            elif self.x > center:
                tilting.append(Tilt.R_RIGHT)

            if self.y < center - 1:
                tilting.append(Tilt.R_DOWN)
            elif self.y > center - 1:
                tilting.append(Tilt.R_UP)
        return tilting


NEUTRAL = (128, 127)
"""
スティックが中心にあることを表します。
丸め誤差の関係で"80 80"になるのは`(128, 127)`です。
"""

# Left stick for ease of use
Direction.UP = Direction(Stick.LEFT, 90, showName="UP")
Direction.RIGHT = Direction(Stick.LEFT, 0, showName="RIGHT")
Direction.DOWN = Direction(Stick.LEFT, -90, showName="DOWN")
Direction.LEFT = Direction(Stick.LEFT, -180, showName="LEFT")
Direction.UP_RIGHT = Direction(Stick.LEFT, 45, showName="UP_RIGHT")
Direction.DOWN_RIGHT = Direction(Stick.LEFT, -45, showName="DOWN_RIGHT")
Direction.DOWN_LEFT = Direction(Stick.LEFT, -135, showName="DOWN_LEFT")
Direction.UP_LEFT = Direction(Stick.LEFT, 135, showName="UP_LEFT")
# Right stick for ease of use
Direction.R_UP = Direction(Stick.RIGHT, 90, showName="UP")
Direction.R_RIGHT = Direction(Stick.RIGHT, 0, showName="RIGHT")
Direction.R_DOWN = Direction(Stick.RIGHT, -90, showName="DOWN")
Direction.R_LEFT = Direction(Stick.RIGHT, -180, showName="LEFT")
Direction.R_UP_RIGHT = Direction(Stick.RIGHT, 45, showName="UP_RIGHT")
Direction.R_DOWN_RIGHT = Direction(Stick.RIGHT, -45, showName="DOWN_RIGHT")
Direction.R_DOWN_LEFT = Direction(Stick.RIGHT, -135, showName="DOWN_LEFT")
Direction.R_UP_LEFT = Direction(Stick.RIGHT, 135, showName="UP_LEFT")


class Touchscreen:
    """タッチスクリーンを押す位置(タッチスクリーンを送れる形式でだけ使われる)"""

    def __init__(self, x: int, y: int) -> None:
        """x, y: 押す位置(3DS の下画面の座標。x は 1 - 320、y は 1 - 240。(0, 0) は、押していない)"""
        self._logger = _logger

        self.x = x
        self.y = y


def _same_input(a: object, b: object) -> bool:
    """
    同じ入力か(種類も比べる)。
    Button と Hat は数値として比べられるため、Button.B と Hat.RIGHT (どちらも 2) のように、
    種類が違っても == では等しくなる組み合わせがある
    """
    return type(a) is type(b) and a == b


def _contains_input(inputs: list, target: object) -> bool:
    """inputs の中に、target と同じ入力(種類も同じ)があるか"""
    return any(_same_input(item, target) for item in inputs)


# handles serial input to Joystick.c


class KeyPress:
    """
    1 つの入力源(コマンド、キーボード、マウスなど)の入力を、Sender へ渡すクラス。

    押す・離す・ホールドの操作を受けて、この入力源の状態(SendFormat)を作り、Sender に渡す
    (ほかの入力源との合成と、送るデータへの変換は、Sender が行う)。
    serial_data_format_name は、今の Data Format の名前(すべての KeyPress で共通)
    """

    serial_data_format_name = "Default"

    def __init__(self, ser: Sender, source: InputSource = InputSource.COMMAND) -> None:
        """
        ser: 送る相手
        source: 入力源の種類(ほかの入力源と同時に操作したときの優先度になる)
        """
        self._logger = _logger

        self.q = queue.Queue()
        self.ser = ser
        # 入力源(他の入力源と同時に操作された場合の優先度に使う)
        self.source = source
        self.format = SendFormat()
        self.holdButton = []
        self.btn_name2 = [
            "LEFT",
            "RIGHT",
            "UP",
            "DOWN",
            "UP_LEFT",
            "UP_RIGHT",
            "DOWN_LEFT",
            "DOWN_RIGHT",
        ]

        self.pushing_to_show = None
        self.pushing = None
        self.pushing2 = None
        self._pushing = None
        self._chk_neutral = None
        self.NEUTRAL = dict(self.format.format)

        self.input_time_0 = time.perf_counter()
        self.input_time_1 = time.perf_counter()
        self.inputEnd_time_0 = time.perf_counter()
        self.was_neutral = True

    def init_hat(self) -> None:
        """何もしない(以前の版との互換のために残してある)"""
        pass

    def input(self, btns: Button | Hat | Direction | Touchscreen | list, ifPrint: bool = True) -> None:
        """
        btns を押した状態(スティックは倒した状態)にして送る。ホールド中の入力も、一緒に押す

        btns: Button、Hat、Direction、Touchscreen、または、それらのリスト
              (Touchscreen は、タッチスクリーンを送れる形式でだけ使われる)
        ifPrint: 使わない
        """
        self._pushing = dict(self.format.format)
        # ホールド中のボタンを足すので、呼び出し元のリストは書き換えずにコピーを使う
        # (書き換えると、同じリストを渡したinputEndで、ホールド中のボタンまで離してしまう)
        btns = list(btns) if isinstance(btns, list) else [btns]

        for btn in self.holdButton:
            if not _contains_input(btns, btn):
                btns.append(btn)
        # ボタンのビットの並びと、タッチスクリーンを送れるかは、送るデータの形式で決まる
        transport = _transport(self.serial_data_format_name)
        self.format.setButton([btn for btn in btns if type(btn) is Button], convert=transport.button_conversion)
        self.format.setHat([btn for btn in btns if type(btn) is Hat])
        self.format.setAnyDirection([btn for btn in btns if type(btn) is Direction])
        if transport.has_touchscreen:
            self.format.setTouchscreen([btn for btn in btns if type(btn) is Touchscreen])
        self._send()
        self.input_time_0 = time.perf_counter()

        # self._logger.debug(f": {list(map(str,self.format.format.values()))}")

    def inputEnd(
        self,
        btns: Button | Hat | Direction | Touchscreen | list,
        ifPrint: bool = True,
        unset_hat: bool = True,
        unset_Touchscreen: bool = True,
    ) -> None:
        """
        btns を離した状態(スティックは、倒していた軸を中央)にして送る

        btns: Button、Hat、Direction、Touchscreen、または、それらのリスト
        ifPrint: 使わない
        unset_hat: 十字キーも離すか(True では、btns に Hat がなくても離す。
                   ただし、Hat をホールド中で、btns に Hat がない場合は、離さない)
        unset_Touchscreen: タッチも離すか(True では、btns に Touchscreen がなくても離す。
                   ただし、タッチをホールド中で、btns に Touchscreen がない場合は、離さない)。
                   False でも、btns に Touchscreen があれば離す
        """
        # self._logger.debug(f"input end: {btns}")
        self.pushing2 = dict(self.format.format)

        self.ed = time.perf_counter()
        if not isinstance(btns, list):
            btns = [btns]
        # self._logger.debug(btns)

        # get tilting direction from angles
        tilts = []
        for dir in [btn for btn in btns if type(btn) is Direction]:
            tiltings = dir.getTilting()
            for tilting in tiltings:
                tilts.append(tilting)
        # self._logger.debug(tilts)

        # ホールド中のHatは、Hat以外を離す場合(ホールド中のpress/holdEnd)には離さない
        if any(type(btn) is Hat for btn in self.holdButton) and not any(type(btn) is Hat for btn in btns):
            unset_hat = False
        # ホールド中のタッチも同様に、タッチ以外を離す場合には離さない
        if any(type(btn) is Touchscreen for btn in self.holdButton) and not any(
            type(btn) is Touchscreen for btn in btns
        ):
            unset_Touchscreen = False

        transport = _transport(self.serial_data_format_name)
        self.format.unsetButton([btn for btn in btns if type(btn) is Button], convert=transport.button_conversion)
        if unset_hat:
            self.format.unsetHat()
        self.format.unsetDirection(tilts)
        if transport.has_touchscreen:
            # 離す一覧にタッチがあれば、unset_Touchscreen が False でも離す
            if unset_Touchscreen or any(type(btn) is Touchscreen for btn in btns):
                self.format.unsetTouchscreen()
        self._send()

    def _send(self) -> None:
        """
        この入力源の状態をSenderに渡す
        (他の入力源の状態との合成・送信形式への変換はSenderが行う)
        """
        self.ser.send_state(self, self.source, self.format.format)

    def release(self) -> None:
        """
        この入力源の入力を全て離し、他の入力源の状態のみを送信する
        """
        self.holdButton = []
        self.format = SendFormat()
        self.ser.release(self)

    def hold(self, btns: Button | Hat | Direction | Touchscreen | list) -> None:
        """
        btns を押したまま(ホールド)にして送る。holdEnd で離すまで、ほかの input / inputEnd でも押したままになる

        btns: Button、Hat、Direction、Touchscreen、または、それらのリスト。
              すでにホールド中のものは、警告を表示して飛ばす。Touchscreen は、前のタッチと入れ替える
        """
        if not isinstance(btns, list):
            btns = [btns]

        flag_isTouchscreen = False
        for btn in btns:
            if type(btn) is Touchscreen:
                flag_isTouchscreen = True
        if flag_isTouchscreen:
            for btn in self.holdButton:
                if type(btn) is Touchscreen:
                    self.holdButton.remove(btn)
        for btn in btns:
            if _contains_input(self.holdButton, btn):
                # ホールド済みのものは飛ばし、残りはホールドして送信する
                # (ここで抜けると、先に追加した分がホールド扱いのまま送信されない)
                name = getattr(btn, "name", btn)
                print(f"Warning: {name} is already in holding state")
                self._logger.warning(f"Warning: {name} is already in holding state")
                continue

            self.holdButton.append(btn)
        self.input(btns)

    def holdEnd(self, btns: Button | Hat | Direction | Touchscreen | list) -> None:
        """
        ホールド中の btns を離して送る

        btns: Button、Hat、Direction、Touchscreen、または、それらのリスト。
              ホールドしていないものは、警告を表示して、離す入力だけを送る。
              Touchscreen は、位置に関わらず、ホールド中のタッチを離す
        """
        if not isinstance(btns, list):
            btns = [btns]

        flag_isTouchscreen = False
        for btn in btns:
            if type(btn) is not Touchscreen:
                if not _contains_input(self.holdButton, btn):
                    # ホールドしていないものは、離す入力だけを送る(ホールド中の他の入力は残す)
                    name = getattr(btn, "name", btn)
                    print(f"Warning: {name} is not in holding state")
                    self._logger.warning(f"Warning: {name} is not in holding state")
                    continue
                # 種類も同じものを1つだけ外す(list.remove は Button.B と Hat.RIGHT を区別しない)
                index = next(i for i, held in enumerate(self.holdButton) if _same_input(held, btn))
                del self.holdButton[index]
            else:
                flag_isTouchscreen = True
        if flag_isTouchscreen:
            for btn in self.holdButton:
                if type(btn) is Touchscreen:
                    self.holdButton.remove(btn)

        self.inputEnd(btns)

    def holdChange(self, btns: Button | Hat | Direction | Touchscreen | list) -> None:
        """
        ホールド中のスティックの向き・倒し量、Hatの向き、タッチの位置を、離さずに切り替える
        (holdEnd→holdでは一度ニュートラルが送信されるため)
        同じスティック・Hat・タッチをホールドしていない場合はholdと同じ
        btns: Button、Hat、Direction、Touchscreen、または、それらのリスト(ホールド中の Button は、そのまま)
        """
        if not isinstance(btns, list):
            btns = [btns]

        for btn in btns:
            if type(btn) is Direction:
                self.holdButton = [b for b in self.holdButton if not (type(b) is Direction and b.stick == btn.stick)]
            elif type(btn) is Hat:
                self.holdButton = [b for b in self.holdButton if type(b) is not Hat]
            elif type(btn) is Touchscreen:
                self.holdButton = [b for b in self.holdButton if type(b) is not Touchscreen]
            elif _contains_input(self.holdButton, btn):
                continue
            self.holdButton.append(btn)
        self.input(list(btns))

    def neutral(self) -> None:
        """ホールド中の入力をすべて離して送る(十字キーとタッチも離す)"""
        btns = self.holdButton
        self.holdButton = []
        self.inputEnd(btns, unset_hat=True, unset_Touchscreen=True)

    def end(self) -> None:
        """コマンドの終わりに、この入力源の入力をすべて離す(下のとおり、形式によっては "end" の行を送る)"""
        # 他の入力源(手動操作)が残っている場合は、この入力源の分だけ離す
        # 残っていない場合は従来通り"end"を送る(Default形式のみ。送る行は、送信方式が決める)
        end_row = _transport(self.serial_data_format_name).end_row
        self.holdButton = []
        self.format = SendFormat()
        self.ser.release(self, end_row=end_row)

    def serialcommand_direct_send(self, serialcommands: list, waittime: list) -> None:
        """
        行を、合成を経由せずに、順に送る(Default の形式の行を、自分で組み立てて送る場合に使う)

        serialcommands: 送る行(文字列)のリスト
        waittime: それぞれの行を送る前に待つ秒数のリスト(短い方の長さまで送る)
        """
        for wtime, row in zip(waittime, serialcommands):
            time.sleep(wtime)
            self.ser.writeRow_wo_perf_counter(row, is_show=False)
