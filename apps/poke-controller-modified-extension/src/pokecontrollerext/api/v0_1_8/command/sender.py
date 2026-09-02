import logging
import math
import time
from contextlib import contextmanager
from typing import Generator, Protocol

import serial
from pokecontroller.utils import platform

from pokecontrollerext.singletons.runtime.resources import (
    get_app_resources,
)

logger = logging.getLogger(__name__)


class BoolGettable(Protocol):
    def get(self) -> bool: ...


class PseudoBoolGetter:
    def get(self) -> bool:
        return False


class Sender:
    def __init__(
        self,
        is_show_serial: BoolGettable,
        if_print: bool = True,
    ) -> None:
        resources = get_app_resources()
        self._serial = resources.serial
        self.is_show_serial = is_show_serial

        self.before: str | list[int] | None = None
        self.L_holding = False
        self._L_holding = None
        self.R_holding = False
        self._R_holding = None
        self.is_print = if_print
        self.time_bef = time.perf_counter()
        self.time_aft = time.perf_counter()
        self.Buttons: list[str] = [
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
            "Button.LCLICK",  # noqa
            "Button.RCLICK",  # noqa
            "Button.HOME",
            "Button.CAPTURE",
        ]
        self.Hat = [
            "TOP",
            "TOP_RIGHT",
            "RIGHT",
            "BTM_RIGHT",
            "BTM",
            "BTM_LEFT",
            "LEFT",
            "TOP_LEFT",
            "CENTER",
        ]

    @property
    def ser(self) -> serial.Serial | None:
        return self._serial._serial

    def openSerial(  # noqa
        self,
        portNum: int | str,  # noqa
        portName: str | None = None,  # noqa
        baudrate: int = 9600,
    ) -> bool:
        if portName:
            name = portName
        elif platform.is_windows():
            name = f"COM{portNum}"
        elif platform.is_macos():
            name = f"/dev/tty.usbserial-{portNum}"
        elif platform.is_linux():
            name = f"/dev/ttyUSB{portNum}"
        else:
            logger.warning("Not supported OS")
            return False

        logger.info(f"connecting to {name}({baudrate})")
        try:
            self._serial.open(port_path=name, baud_rate=baudrate)
        except serial.serialutil.SerialException as e:
            logger.error("COM Port: can't be established")
            logger.error(f"{e}")
            return False

        return True

    def closeSerial(self) -> None:  # noqa
        logger.debug("Closing the serial communication")
        self._serial.close()

    def isOpened(self) -> bool:  # noqa
        logger.debug("Checking if serial communication is open")
        return self._serial.is_opened

    def writeRow(  # noqa
        self,
        row: str,
        is_show: bool = False,
    ) -> None:
        if not self._serial.is_opened:
            logger.error("Serial is not open")
            return

        if (
            is_show
            and (before := self.before) is not None
            and isinstance(before, str)
            and before != "end"
        ):
            output = before.split(" ")
            self.show_input(output)

        try:
            self.time_bef = time.perf_counter()

            self._serial.write_line(row)
            self.time_aft = time.perf_counter()
            self.before = row
        except serial.serialutil.SerialException as e:
            logger.error(f"Error : {e}")

        # Show sending serial data
        if self.is_show_serial.get():
            logger.debug(row)

    def writeList(  # noqa
        self,
        values: list[int],
        is_show: bool = False,
    ) -> None:
        if not self._serial.is_opened:
            logger.error("Serial port is not open")
            return

        try:
            self.time_bef = time.perf_counter()

            data = bytearray(values)
            self._serial.write(data)
            self.time_aft = time.perf_counter()
            self.before = values
        except serial.serialutil.SerialException as e:
            logger.error(f"Error : {e}")

        # Show sending serial data
        if self.is_show_serial.get():
            logger.debug(values)

    def writeRow_wo_perf_counter(  # noqa
        self,
        row: str,
        is_show: bool = False,
    ) -> None:
        if not self._serial.is_opened:
            logger.error("Serial port is not open")
            return

        try:
            self._serial.write_line(row)
        except serial.serialutil.SerialException as e:
            logger.error(f"Error : {e}")

        # Show sending serial data
        if self.is_show_serial.get():
            logger.debug(row)

    def show_input(self, output: list[str]) -> None:
        if not self.is_print:
            return

        lstick, rstick, buttons = self._parse_output(output=output)

        # stringify buttons and stick
        buttons_str = ", ".join(buttons) if buttons else None
        lstick_str: str | None = None
        if lstick is not None:
            lstick_str = f"Direction(Stick.LEFT, degree={lstick[0]:.0f}, magnification={lstick[1]:.2f})"
        rstick_str: str | None = None
        if rstick is not None:
            rstick_str = f"Direction(Stick.RIGHT, degree={rstick[0]:.0f}, magnification={rstick[1]:.2f})"

        # check has loggable states
        state_strs = tuple(
            s for s in (buttons_str, lstick_str, rstick_str) if s is not None
        )
        if not state_strs:
            return

        # log
        duration = self.time_aft - self.time_bef
        arg_str = (
            state_strs[0] if len(state_strs) == 1 else f"[{', '.join(state_strs)}]"
        )
        logger.debug(f"self.press({arg_str}, duration={duration:.2f})")

    def _parse_output(
        self,
        output: list[str],
    ) -> tuple[
        tuple[float, float] | None,  # lstick
        tuple[float, float] | None,  # rstick
        tuple[str, ...],  # buttons
    ]:
        overview = output[0]
        hat_raw = output[1]
        (_, using_rstick), (_, using_lstick), *buttons = tuple(
            (button, bool(int(overview, 16) >> i & 1))
            for i, button in enumerate(self.Buttons)
        )
        if (hat := self.Hat[int(hat_raw)]) != "CENTER":
            buttons.append((f"Hat.{str(hat)}", True))

        lstick = self._calc_output_stick(output[2:4]) if using_lstick else None
        rstick = self._calc_output_stick(output[4:6]) if using_rstick else None

        return lstick, rstick, tuple(button for (button, using) in buttons if using)

    # noinspection PyMethodMayBeStatic
    def _calc_output_stick(self, output_stick: list[str]) -> tuple[float, float] | None:
        x, y = [int(a, 16) for a in output_stick]
        if x == 128 and y == 128:
            return None
        return math.degrees(math.atan2(128 - y, x - 128)), math.sqrt(x**2 + y**2)


@contextmanager
def use_sender(
    if_print: bool = True,
) -> Generator[Sender, None, None]:
    sender = Sender(PseudoBoolGetter(), if_print)
    try:
        yield sender
    finally:
        sender.closeSerial()
