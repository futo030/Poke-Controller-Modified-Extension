import logging
from time import sleep

import numpy as np

from pokecontrollerext.api.v0_1_8.command.commands.base import (
    Command,
    PostProcess,
)
from pokecontrollerext.api.v0_1_8.command.keys import (
    ButtonLike,
    Direction,
    KeyPress,
    Stick,
)
from pokecontrollerext.api.v0_1_8.command.sender import (
    Sender,
)

logger = logging.getLogger(__name__)


class StickCommand(Command):
    def __init__(self) -> None:
        super().__init__()
        self.key: KeyPress | None = None

    def start(
        self,
        ser: Sender,
        postProcess: PostProcess | None = None,
    ) -> None:
        self.isRunning = True
        self.key = KeyPress(ser)

    def end(self, ser: Sender) -> None:
        self.isRunning = True
        self.key = KeyPress(ser)

    # do nothing at wait time(s)
    def wait(self, wait: float) -> None:
        sleep(wait)

    def press(self, btn: ButtonLike) -> None:
        if (keys := self.key) is None:
            raise RuntimeError(
                "Stick command not started. Call start() before press()."
            )
        keys.input([btn])
        self.wait(0.1)
        keys.inputEnd([btn])
        self.isRunning = False
        self.key = None

    # press button at duration times(s)
    def stick(
        self,
        stick: Direction,
        duration: float = 0.015,
        wait: float = 0,
    ) -> None:
        if (keys := self.key) is None:
            raise RuntimeError(
                "Stick command not started. Call start() before stick()."
            )
        keys.input(stick, ifPrint=False)
        # print(buttons)
        self.wait(duration)
        self.wait(wait)

    def stick_end(self, stick: Direction = Direction(Stick.LEFT, 0)) -> None:
        if (keys := self.key) is None:
            raise RuntimeError(
                "Stick command not started. Call start() before stick_end()."
            )
        keys.inputEnd(stick)


class StickLeft(StickCommand):
    def __init__(self, ser: Sender) -> None:
        super().__init__()
        self.ser = ser
        self.key: KeyPress | None = None

    def start(
        self,
        ser: Sender,
        postprocess: PostProcess | None = None,
    ) -> None:
        super().start(ser)
        self.key = KeyPress(ser)
        logger.debug("Start RightStick Serial Connection")

    def LStick(
        self,
        angle: float,
        r: float = 1.0,
        duration: float = 0.015,
    ) -> None:
        if (keys := self.key) is None:
            raise RuntimeError(
                "StickLeft command not started. Call start() before LStick()."
            )
        keys.ser.writeRow(
            f"3 8 {hex(int(128 + r * 127.5 * np.cos(np.deg2rad(angle))))} {hex(int(128 - r * 127.5 * np.sin(np.deg2rad(angle))))} 80 80",
            is_show=False,
        )

    def end(self, ser: Sender) -> None:
        super().end(ser)
        self.stick_end(stick=Direction(Stick.LEFT, 0))


class StickRight(StickCommand):
    def __init__(self) -> None:
        super().__init__()
        self.key: KeyPress | None = None

    def start(
        self,
        ser: Sender,
        postProcess: PostProcess | None = None,
    ) -> None:
        super().start(ser)
        self.key = KeyPress(ser)
        logger.debug("Start RightStick Serial Connection")

    def RStick(
        self,
        angle: float,
        r: float = 1.0,
        duration: float = 0.015,
    ) -> None:
        if (keys := self.key) is None:
            raise RuntimeError(
                "StickRight command not started. Call start() before RStick()."
            )
        keys.ser.writeRow(
            f"3 8 80 80 {hex(int(128 + r * 127.5 * np.cos(np.deg2rad(angle))))} {hex(int(128 - r * 127.5 * np.sin(np.deg2rad(angle))))}",
            is_show=False,
        )

    def end(self, ser: Sender) -> None:
        super().end(ser)
        self.stick_end(stick=Direction(Stick.RIGHT, 0))
