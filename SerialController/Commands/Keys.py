#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import TYPE_CHECKING

import math
import time
from collections import OrderedDict
from enum import Enum, IntEnum, IntFlag, auto
import queue
from logging import getLogger, DEBUG, NullHandler

if TYPE_CHECKING:
    from Commands.Sender import Sender


class Button(IntFlag):
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


class Stick(Enum):
    LEFT = auto()
    RIGHT = auto()


class Tilt(Enum):
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
    def __init__(self):
        self._logger = getLogger(__name__)
        self._logger.addHandler(NullHandler())
        self._logger.setLevel(DEBUG)
        self._logger.propagate = True

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

    def setButton(self, btns, convert=conversion_default_button):
        for btn in btns:
            self.format["btn"] |= convert[btn]

    def unsetButton(self, btns, convert=conversion_default_button):
        for btn in btns:
            self.format["btn"] &= ~convert[btn]

    def resetAllButtons(self):
        self.format["btn"] = 0

    def setHat(self, btns, convert=convert_hat_default):
        # self._logger.debug(btns)
        if not btns:
            self.format["hat"] = self.Hat_pos
        else:
            self.Hat_pos = convert[btns[0]]
            self.format["hat"] = convert[btns[0]]  # takes only first element

    def unsetHat(self, convert=convert_hat_default):
        # if self.Hat_pos is not Hat.CENTER:
        self.Hat_pos = convert[Hat.CENTER]
        self.format["hat"] = self.Hat_pos

    def setAnyDirection(self, dirs, x_reverse=False, y_reverse=False):
        for dir in dirs:
            if dir.stick == Stick.LEFT:
                if self.format["lx"] != dir.x or self.format["ly"] != 255 - dir.y:
                    self.L_stick_changed = True

                self.format["lx"] = dir.x if not x_reverse else 255 - dir.x
                self.format["ly"] = 255 - dir.y if not y_reverse else dir.y  # NOTE: y axis directs under
            elif dir.stick == Stick.RIGHT:
                if self.format["rx"] != dir.x or self.format["ry"] != 255 - dir.y:
                    self.R_stick_changed = True

                self.format["rx"] = dir.x if not x_reverse else 255 - dir.x
                self.format["ry"] = 255 - dir.y if not y_reverse else dir.y

    def unsetDirection(self, dirs):
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
    def fixOtherAxis(self, fix_target):
        if fix_target == center:
            return center
        else:
            return 0 if fix_target < center else 255

    def resetAllDirections(self):
        self.format["lx"] = center
        self.format["ly"] = center
        self.format["rx"] = center
        self.format["ry"] = center
        self.L_stick_changed = True
        self.R_stick_changed = True
        self.Hat_pos = Hat.CENTER

    def setTouchscreen(self, dirs):
        if not dirs:
            pass
        else:
            self.format["sx"] = dirs[0].x  # takes only first element
            self.format["sy"] = dirs[0].y  # takes only first element

    def unsetTouchscreen(self):
        self.format["sx"] = 0
        self.format["sy"] = 0

    def convert2str(self):
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
            str_L = format(self.format["lx"], "x") + space + format(self.format["ly"], "x")
        if self.R_stick_changed:
            send_btn |= 0x1
            str_R = format(self.format["rx"], "x") + space + format(self.format["ry"], "x")
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

    def convert2list(self):
        """
        For Qingpi
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

    def convert2list2(self):
        """
        For 3DS Controller
        """
        header = 0xA1  # fixed value
        send_btn = int(self.format["btn"])
        send_hat = convert_hat_3ds_controller[int(self.format["hat"])]

        header2 = 0xA2  # fixed value
        send_lx = self.format["lx"] if self.format["lx"] >= 128 else 127 - self.format["lx"]
        send_ly = self.format["ly"] if self.format["ly"] >= 128 else 127 - self.format["ly"]

        state = [
            header,
            ((send_btn & 0xF) << 4) | send_hat,
            (send_btn >> 4) & 0x3F,
            header2,
            send_lx,
            send_ly,
        ]

        return state


# This class handle L stick and R stick at any angles
class Direction:
    def __init__(self, stick, angle, magnification=1.0, isDegree=True, showName=None):
        self._logger = getLogger(__name__)
        self._logger.addHandler(NullHandler())
        self._logger.setLevel(DEBUG)
        self._logger.propagate = True

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

    def __repr__(self):
        if self.showName:
            return "<{}, {}>".format(self.stick, self.showName)
        else:
            return "<{}, {}[deg]>".format(self.stick, self.angle_for_show)

    def __eq__(self, other):
        if not isinstance(other, Direction):
            return False

        if self.stick == other.stick and self.angle_for_show == other.angle_for_show:
            return True
        else:
            return False

    def __hash__(self) -> int:
        return hash((self.x, self.y, self.stick))

    def getTilting(self):
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
    def __init__(self, x, y):
        self._logger = getLogger(__name__)
        self._logger.addHandler(NullHandler())
        self._logger.setLevel(DEBUG)
        self._logger.propagate = True

        self.x = x
        self.y = y

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Touchscreen):
            return False

        return bool(
            self.x == other.x and self.y == other.y,
        )

    def __hash__(self) -> int:
        return hash((self.x, self.y))


# handles serial input to Joystick.c


class KeyPress:
    serial_data_format_name = "Default"

    def __init__(self, ser: Sender):
        self._logger = getLogger(__name__)
        self._logger.addHandler(NullHandler())
        self._logger.setLevel(DEBUG)
        self._logger.propagate = True

        self.q = queue.Queue()
        self.ser = ser
        self.format = SendFormat()
        self.holdButton = set()
        self.holdHat = Hat.CENTER
        self.holdLeftStick = False
        self.holdRightStick = False
        self.holdTouchscreen = False
        self.btn_name2 = ["LEFT", "RIGHT", "UP", "DOWN", "UP_LEFT", "UP_RIGHT", "DOWN_LEFT", "DOWN_RIGHT"]

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

    @property
    def holdButtons(self) -> ButtonsList:
        holdButtons: ButtonsList = list(self.holdButton)
        if self.holdHat != Hat.CENTER:
            holdButtons.append(self.holdHat)
        if self.holdLeftStick:
            holdButtons.append(self.holdLeftStick)
        if self.holdRightStick:
            holdButtons.append(self.holdRightStick)
        if self.holdTouchscreen:
            holdButtons.append(self.holdTouchscreen)
        return holdButtons

    def init_hat(self):
        pass

    def input(self, btns: Button | Hat | Stick | Direction, ifPrint=True):
        self._pushing = dict(self.format.format)
        if not isinstance(btns, list):
            btns = [btns]

        for btn in self.holdButtons:
            if btn not in btns:
                btns.append(btn)
        if self.serial_data_format_name == "3DS Controller":
            self.format.setButton(
                [btn for btn in btns if type(btn) is Button], convert=conversion_3ds_controller_button
            )
            self.format.setHat([btn for btn in btns if type(btn) is Hat])
            self.format.setAnyDirection([btn for btn in btns if type(btn) is Direction])
            self.ser.writeList(self.format.convert2list2())
        else:
            self.format.setButton([btn for btn in btns if type(btn) is Button])
            self.format.setHat([btn for btn in btns if type(btn) is Hat])
            self.format.setAnyDirection([btn for btn in btns if type(btn) is Direction])
            if self.serial_data_format_name == "Qingpi":
                self.format.setTouchscreen([btn for btn in btns if type(btn) is Touchscreen])
                self.ser.writeList(self.format.convert2list())
            else:
                self.ser.writeRow(self.format.convert2str())
        self.input_time_0 = time.perf_counter()

        # self._logger.debug(f": {list(map(str,self.format.format.values()))}")

    def inputEnd(self, btns: Button | Hat | Stick | Direction, ifPrint=True, unset_hat=True, unset_Touchscreen=True):
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

        if self.holdHat != Hat.CENTER and not any(isinstance(btn, Hat) for btn in btns):
            unset_hat = False
        if self.holdTouchscreen and not any(
            isinstance(btn, Touchscreen) for btn in btns
        ):
            unset_Touchscreen = False

        if self.serial_data_format_name == "3DS Controller":
            self.format.unsetButton(
                [btn for btn in btns if type(btn) is Button], convert=conversion_3ds_controller_button
            )
            if unset_hat:
                self.format.unsetHat()
            self.format.unsetDirection(tilts)
            self.ser.writeList(self.format.convert2list2())
        else:
            self.format.unsetButton([btn for btn in btns if type(btn) is Button])
            if unset_hat:
                self.format.unsetHat()
            self.format.unsetDirection(tilts)
            if self.serial_data_format_name == "Qingpi":
                if unset_Touchscreen or (True in [btn for btn in btns if type(btn) is Touchscreen]):
                    self.format.unsetTouchscreen()
                self.ser.writeList(self.format.convert2list())
            else:
                self.ser.writeRow(self.format.convert2str())

    def hold(self, btns: Button | Hat | Stick | Direction):
        if not isinstance(btns, list):
            btns = [btns]

        for btn in btns[:]:
            if isinstance(btn, Button):
                if btn in self.holdButton:
                    print(f"Warning: {btn.name} is already in holding state")
                    btns.remove(btn)
                else:
                    self.holdButton.add(btn)
            elif isinstance(btn, Hat):
                if btn == self.holdHat:
                    print(f"Warning: {btn.name} is already in holding state")
                    btns.remove(btn)
                else:
                    self.holdHat = btn
            elif isinstance(btn, Direction):
                if btn.stick == Stick.LEFT:
                    if btn == self.holdLeftStick:
                        print(f"Warning: {btn.name} is already in holding state")
                        btns.remove(btn)
                    else:
                        self.holdLeftStick = btn
                elif btn.stick == Stick.RIGHT:
                    if btn == self.holdRightStick:
                        print(f"Warning: {btn.name} is already in holding state")
                        btns.remove(btn)
                    else:
                        self.holdRightStick = btn
            elif isinstance(btn, Touchscreen):
                if btn == self.holdTouchscreen:
                    print(f"Warning: {btn.name} is already in holding state")
                    btns.remove(btn)
                else:
                    self.holdTouchscreen = btn
        if len(btns) > 0:
            self.input(btns)

    def holdEnd(self, btns: Button | Hat | Stick | Direction):
        if not isinstance(btns, list):
            btns = [btns]

        for btn in btns[:]:
            if isinstance(btn, Button):
                if btn in self.holdButton:
                    self.holdButton.remove(btn)
                else:
                    print(f"Warning: {btn.name} is not holding state")
                    btns.remove(btn)
            elif isinstance(btn, Hat):
                if btn == self.holdHat:
                    self.holdHat = Hat.CENTER
                else:
                    print(f"Warning: {btn.name} is not holding state")
                    btns.remove(btn)
            elif isinstance(btn, Direction):
                if btn.stick == Stick.LEFT:
                    if btn == self.holdLeftStick:
                        self.holdLeftStick = False
                    else:
                        print(f"Warning: {btn.name} is not holding state")
                        btns.remove(btn)
                elif btn.stick == Stick.RIGHT:
                    if btn == self.holdRightStick:
                        self.holdRightStick = False
                    else:
                        print(f"Warning: {btn.name} is not holding state")
                        btns.remove(btn)
            elif isinstance(btn, Touchscreen):
                if btn == self.holdTouchscreen:
                    self.holdTouchscreen = False
                else:
                    print(f"Warning: {btn.name} is not holding state")
                    btns.remove(btn)

        if len(btns) > 0:
            self.inputEnd(btns)

    def neutral(self):
        btns = self.holdButtons
        self.holdButton = set()
        self.holdHat = Hat.CENTER
        self.holdLeftStick = False
        self.holdRightStick = False
        self.holdTouchscreen = False
        self.inputEnd(btns, unset_hat=True, unset_Touchscreen=True)

    def end(self):
        if self.serial_data_format_name in ["Qingpi", "3DS Controller"]:
            pass
        else:
            self.ser.writeRow("end")

    def serialcommand_direct_send(self, serialcommands: list, waittime: list):
        for wtime, row in zip(waittime, serialcommands):
            time.sleep(wtime)
            self.ser.writeRow_wo_perf_counter(row, is_show=False)
