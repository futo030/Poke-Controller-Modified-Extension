import logging
import math
import time
from collections import OrderedDict
from dataclasses import dataclass
from enum import Enum, IntEnum, IntFlag, auto
from typing import Any, cast

from pokecontrollerext.api.v0_1_8.command.sender import Sender

logger = logging.getLogger(__name__)


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
conversion_default_button: dict[Button, Button] = {
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

conversion_3ds_controller_button: dict[Button, int] = {
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


convert_hat_default: list[Hat] = cast(list[Hat], [h for h in range(0, 9)])
convert_hat_3ds_controller: list[Hat] = cast(list[Hat], [8, 0, 4, 0, 2, 0, 1, 0, 0])


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


def _clamp(
    value: float,
    min_value: float,
    max_value: float,
) -> float:
    if value < min_value:
        return min_value
    elif value > max_value:
        return max_value
    else:
        return value


# This class handle L stick and R stick at any angles
class Direction:
    UP: "Direction"
    RIGHT: "Direction"
    DOWN: "Direction"
    LEFT: "Direction"
    UP_RIGHT: "Direction"
    DOWN_RIGHT: "Direction"
    DOWN_LEFT: "Direction"
    UP_LEFT: "Direction"
    R_UP: "Direction"
    R_RIGHT: "Direction"
    R_DOWN: "Direction"
    R_LEFT: "Direction"
    R_UP_RIGHT: "Direction"
    R_DOWN_RIGHT: "Direction"
    R_DOWN_LEFT: "Direction"
    R_UP_LEFT: "Direction"

    def __init__(
        self,
        stick: Stick,
        angle: int | tuple[int, int],
        magnification: float = 1.0,
        isDegree: bool = True,  # noqa
        showName: str | None = None,  # noqa
    ) -> None:
        self.stick = stick
        self.angle_for_show = angle
        self.showName = showName
        self.mag = _clamp(magnification, 0.0, 1.0)

        if isinstance(angle, tuple):
            # assuming (X, Y)
            self.x, self.y = angle
            self.showName = f"({self.x}, {self.y})"
            logger.debug(f"押し込み量 {self.showName}")
        else:
            # We set stick X and Y from 0 to 255, so they are calculated as below.
            theta = math.radians(angle) if isDegree else angle
            self.x = math.ceil(127.5 * math.cos(theta) * self.mag + 127.5)
            self.y = math.floor(127.5 * math.sin(theta) * self.mag + 127.5)

    def __repr__(self) -> str:
        if self.showName:
            return "<{}, {}>".format(self.stick, self.showName)
        else:
            return "<{}, {}[deg]>".format(self.stick, self.angle_for_show)

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Direction):
            return False

        if self.stick == other.stick and self.angle_for_show == other.angle_for_show:
            return True
        else:
            return False

    def getTilting(self) -> list[Tilt]:  # noqa
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


@dataclass
class Touchscreen:
    x: int
    y: int


# serial format
class SendFormat:
    def __init__(self) -> None:
        # This format structure needs to be the same as the one written in Joystick.c
        self.format: OrderedDict[str, int] = OrderedDict(
            [
                ("btn", 0),  # send the bit array for buttons
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

    def setButton(  # noqa
        self,
        btns: list[Button],
        convert: dict[Button, Button | int] | None = None,
    ) -> None:
        conv = convert if convert is not None else conversion_default_button
        for btn in btns:
            self.format["btn"] |= conv[btn]

    def unsetButton(  # noqa
        self,
        btns: list[Button],
        convert: dict[Button, Button | int] | None = None,
    ) -> None:
        conv = convert if convert is not None else conversion_default_button
        for btn in btns:
            self.format["btn"] &= ~conv[btn]

    def resetAllButtons(self) -> None:  # noqa
        self.format["btn"] = 0

    def setHat(  # noqa
        self,
        btns: list[Hat],
        convert: list[Hat] | None = None,
    ) -> None:
        if not convert:
            convert = convert_hat_default
        if not btns:
            self.format["hat"] = self.Hat_pos
        else:
            # takes only the first element
            self.format["hat"] = self.Hat_pos = convert[btns[0]]

    def unsetHat(  # noqa
        self,
        convert: list[Hat] | None = None,
    ) -> None:
        if not convert:
            convert = convert_hat_default

        # if self.Hat_pos is not Hat.CENTER:
        self.Hat_pos = convert[Hat.CENTER]
        self.format["hat"] = self.Hat_pos

    def setAnyDirection(  # noqa
        self,
        dirs: list[Direction],
        x_reverse: bool = False,
        y_reverse: bool = False,
    ) -> None:
        for d in dirs:
            if d.stick == Stick.LEFT:
                if self.format["lx"] != d.x or self.format["ly"] != 255 - d.y:
                    self.L_stick_changed = True

                self.format["lx"] = d.x if not x_reverse else 255 - d.x
                self.format["ly"] = (
                    255 - d.y if not y_reverse else d.y
                )  # NOTE: y axis directs under

            elif d.stick == Stick.RIGHT:
                if self.format["rx"] != d.x or self.format["ry"] != 255 - d.y:
                    self.R_stick_changed = True

                self.format["rx"] = d.x if not x_reverse else 255 - d.x
                self.format["ry"] = 255 - d.y if not y_reverse else d.y

    def unsetDirection(  # noqa
        self,
        dirs: list[Tilt],
    ) -> None:
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

    # Use this to fix another tilt to max when the other axis sets to 0
    def fixOtherAxis(  # noqa
        self,
        fix_target: int,
    ) -> int:
        if fix_target == center:
            return center
        else:
            return 0 if fix_target < center else 255

    def resetAllDirections(self) -> None:  # noqa
        self.format["lx"] = center
        self.format["ly"] = center
        self.format["rx"] = center
        self.format["ry"] = center
        self.L_stick_changed = True
        self.R_stick_changed = True
        self.Hat_pos = Hat.CENTER

    def setTouchscreen(  # noqa
        self,
        dirs: list[Touchscreen],
    ) -> None:
        if not dirs:
            pass
        else:
            self.format["sx"] = dirs[0].x  # takes only the first element
            self.format["sy"] = dirs[0].y  # takes only the first element

    def unsetTouchscreen(self) -> None:  # noqa
        self.format["sx"] = 0
        self.format["sy"] = 0

    def convert2str(self) -> str:
        lstick = ""
        rstick = ""

        # set bits array with stick flags
        send_btn = int(self.format["btn"]) << 2
        if self.L_stick_changed:
            send_btn |= 0x2
            lstick = (
                f"{format(self.format['lx'], 'x')} {format(self.format['ly'], 'x')}"
            )
        if self.R_stick_changed:
            send_btn |= 0x1
            rstick = (
                f"{format(self.format['rx'], 'x')} {format(self.format['ry'], 'x')}"
            )
        hat = str(int(self.format["hat"]))
        btns = format(send_btn, "#06x")

        str_format = f"{btns} {hat} {lstick} {rstick}"
        self.L_stick_changed = False
        self.R_stick_changed = False

        return str_format

    def convert2list(self) -> list[int]:
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

    def convert2list2(self) -> list[int]:
        """
        For 3DS Controller
        """
        header = 0xA1  # fixed value
        send_btn = int(self.format["btn"])
        send_hat = convert_hat_3ds_controller[int(self.format["hat"])]

        header2 = 0xA2  # fixed value
        send_lx = (
            self.format["lx"] if self.format["lx"] >= 128 else 127 - self.format["lx"]
        )
        send_ly = (
            self.format["ly"] if self.format["ly"] >= 128 else 127 - self.format["ly"]
        )

        state = [
            header,
            ((send_btn & 0xF) << 4) | send_hat,
            (send_btn >> 4) & 0x3F,
            header2,
            send_lx,
            send_ly,
        ]

        return state


ButtonLike = Button | Hat | Stick | Direction | Touchscreen


# handles serial input to Joystick.c
class KeyPress:
    serial_data_format_name = "Default"

    def __init__(self, ser: Sender):
        self.ed: float | None = None
        self.ser = ser
        self.format = SendFormat()
        self.holdButton: list[Button | Hat | Stick | Direction | Touchscreen] = []
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

        self.pushing2: dict[str, int] | None = None
        self._pushing: dict[str, int] | None = None
        self.NEUTRAL = dict(self.format.format)

        self.input_time_0 = time.perf_counter()
        self.input_time_1 = time.perf_counter()
        self.inputEnd_time_0 = time.perf_counter()
        self.was_neutral = True

    def init_hat(self) -> None:
        pass

    def input(
        self,
        btns: ButtonLike | list[ButtonLike],
        ifPrint: bool = True,  # noqa
    ) -> None:
        self._pushing = dict(self.format.format)
        if not isinstance(btns, list):
            btns = [btns]

        for btn in self.holdButton:
            if btn not in btns:
                btns.append(btn)
        if self.serial_data_format_name == "3DS Controller":
            self.format.setButton(
                [btn for btn in btns if type(btn) is Button],
                convert=conversion_3ds_controller_button,
            )
            self.format.setHat([btn for btn in btns if type(btn) is Hat])
            self.format.setAnyDirection([btn for btn in btns if type(btn) is Direction])
            self.ser.writeList(self.format.convert2list2())
        else:
            self.format.setButton([btn for btn in btns if type(btn) is Button])
            self.format.setHat([btn for btn in btns if type(btn) is Hat])
            self.format.setAnyDirection([btn for btn in btns if type(btn) is Direction])
            if self.serial_data_format_name == "Qingpi":
                self.format.setTouchscreen(
                    [btn for btn in btns if type(btn) is Touchscreen]
                )
                self.ser.writeList(self.format.convert2list())
            else:
                self.ser.writeRow(self.format.convert2str())
        self.input_time_0 = time.perf_counter()

    def inputEnd(  # noqa
        self,
        btns: ButtonLike | list[ButtonLike],
        ifPrint: bool = True,  # noqa
        unset_hat: bool = True,
        unset_Touchscreen: bool = True,  # noqa
    ) -> None:
        self.pushing2 = dict(self.format.format)

        self.ed = time.perf_counter()
        if not isinstance(btns, list):
            btns = [btns]

        # get tilting direction from angles
        tilts = []
        for d in [btn for btn in btns if type(btn) is Direction]:
            tiltings = d.getTilting()
            for tilting in tiltings:
                tilts.append(tilting)

        if self.serial_data_format_name == "3DS Controller":
            self.format.unsetButton(
                [btn for btn in btns if type(btn) is Button],
                convert=conversion_3ds_controller_button,
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
                if unset_Touchscreen or any(type(btn) is Touchscreen for btn in btns):
                    self.format.unsetTouchscreen()
                self.ser.writeList(self.format.convert2list())
            else:
                self.ser.writeRow(self.format.convert2str())

    def hold(self, btns: ButtonLike | list[ButtonLike]) -> None:
        if not isinstance(btns, list):
            btns = [btns]

        if any(type(btn) is Touchscreen for btn in btns):
            for touchscreen in [
                btn for btn in self.holdButton if type(btn) is Touchscreen
            ]:
                self.holdButton.remove(touchscreen)
        for btn in btns:
            if btn in self.holdButton:
                logger.warning(f"Warning: {btn} is already in holding state")
                return
            self.holdButton.append(btn)
        self.input(btns)

    def holdEnd(  # noqa
        self,
        btns: ButtonLike | list[ButtonLike],
    ) -> None:
        if not isinstance(btns, list):
            btns = [btns]

        for btn in btns:
            if type(btn) is Touchscreen:
                for touchscreen in [
                    b for b in self.holdButton if type(b) is Touchscreen
                ]:
                    self.holdButton.remove(touchscreen)
            elif btn in self.holdButton:
                self.holdButton.remove(btn)

        self.inputEnd(btns)

    def neutral(self) -> None:
        btns = self.holdButton
        self.holdButton = []
        self.inputEnd(btns, unset_hat=True, unset_Touchscreen=True)

    def end(self) -> None:
        if self.serial_data_format_name not in ["Qingpi", "3DS Controller"]:
            self.ser.writeRow("end")

    def serialcommand_direct_send(self, serialcommands: list, waittime: list) -> None:
        for wtime, row in zip(waittime, serialcommands):
            time.sleep(wtime)
            self.ser.writeRow_wo_perf_counter(row, is_show=False)
