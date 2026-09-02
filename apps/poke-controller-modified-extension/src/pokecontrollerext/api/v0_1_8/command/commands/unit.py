from abc import ABC
from time import sleep

from pokecontrollerext.api.v0_1_8.command.commands.base import (
    Command,
    PostProcess,
)
from pokecontrollerext.api.v0_1_8.command.keys import (
    Button,
    ButtonLike,
    Hat,
    KeyPress,
)
from pokecontrollerext.api.v0_1_8.command.sender import (
    Sender,
)


# Single button command
class UnitCommand(Command, ABC):
    def __init__(self) -> None:
        super().__init__()

    def start(
        self,
        ser: Sender,
        postProcess: PostProcess | None = None,
    ) -> None:
        self.isRunning = True
        self.key: KeyPress | None = KeyPress(ser)

    def end(self, ser: Sender) -> None:
        pass

    def wait(self, wait: float) -> None:
        sleep(wait)

    def press(self, btn: ButtonLike) -> None:
        if (key := self.key) is not None:
            key.input([btn])
            self.wait(0.1)
            key.inputEnd([btn])
        self.isRunning = False
        self.key = None


class A(UnitCommand):
    def __init__(self) -> None:
        super().__init__()

    def start(
        self,
        ser: Sender,
        postProcess: PostProcess | None = None,
    ) -> None:
        super().start(ser)
        self.press(Button.A)


class B(UnitCommand):
    def __init__(self) -> None:
        super().__init__()

    def start(
        self,
        ser: Sender,
        postProcess: PostProcess | None = None,
    ) -> None:
        super().start(ser)
        self.press(Button.B)


class X(UnitCommand):
    def __init__(self) -> None:
        super().__init__()

    def start(
        self,
        ser: Sender,
        postProcess: PostProcess | None = None,
    ) -> None:
        super().start(ser)
        self.press(Button.X)


class Y(UnitCommand):
    def __init__(self) -> None:
        super().__init__()

    def start(
        self,
        ser: Sender,
        postProcess: PostProcess | None = None,
    ) -> None:
        super().start(ser)
        self.press(Button.Y)


class L(UnitCommand):
    def __init__(self) -> None:
        super().__init__()

    def start(
        self,
        ser: Sender,
        postProcess: PostProcess | None = None,
    ) -> None:
        super().start(ser)
        self.press(Button.L)


class R(UnitCommand):
    def __init__(self) -> None:
        super().__init__()

    def start(
        self,
        ser: Sender,
        postProcess: PostProcess | None = None,
    ) -> None:
        super().start(ser)
        self.press(Button.R)


class ZL(UnitCommand):
    def __init__(self) -> None:
        super().__init__()

    def start(
        self,
        ser: Sender,
        postProcess: PostProcess | None = None,
    ) -> None:
        super().start(ser)
        self.press(Button.ZL)


class ZR(UnitCommand):
    def __init__(self) -> None:
        super().__init__()

    def start(
        self,
        ser: Sender,
        postProcess: PostProcess | None = None,
    ) -> None:
        super().start(ser)
        self.press(Button.ZR)


class MINUS(UnitCommand):
    def __init__(self) -> None:
        super().__init__()

    def start(
        self,
        ser: Sender,
        postProcess: PostProcess | None = None,
    ) -> None:
        super().start(ser)
        self.press(Button.MINUS)


class PLUS(UnitCommand):
    def __init__(self) -> None:
        super().__init__()

    def start(
        self,
        ser: Sender,
        postProcess: PostProcess | None = None,
    ) -> None:
        super().start(ser)
        self.press(Button.PLUS)


class LCLICK(UnitCommand):
    def __init__(self) -> None:
        super().__init__()

    def start(
        self,
        ser: Sender,
        postProcess: PostProcess | None = None,
    ) -> None:
        super().start(ser)
        self.press(Button.LCLICK)


class RCLICK(UnitCommand):
    def __init__(self) -> None:
        super().__init__()

    def start(
        self,
        ser: Sender,
        postProcess: PostProcess | None = None,
    ) -> None:
        super().start(ser)
        self.press(Button.RCLICK)


class HOME(UnitCommand):
    def __init__(self) -> None:
        super().__init__()

    def start(
        self,
        ser: Sender,
        postProcess: PostProcess | None = None,
    ) -> None:
        super().start(ser)
        self.press(Button.HOME)


class CAPTURE(UnitCommand):
    def __init__(self) -> None:
        super().__init__()

    def start(
        self,
        ser: Sender,
        postProcess: PostProcess | None = None,
    ) -> None:
        super().start(ser)
        self.press(Button.CAPTURE)


class UP(UnitCommand):
    def __init__(self) -> None:
        super().__init__()

    def start(
        self,
        ser: Sender,
        postProcess: PostProcess | None = None,
    ) -> None:
        super().start(ser)
        if (key := self.key) is not None:
            key.input(Hat.TOP)
            self.wait(0.1)
            key.input(Hat.CENTER)
        self.key = None


class UP_RIGHT(UnitCommand):
    def __init__(self) -> None:
        super().__init__()

    def start(
        self,
        ser: Sender,
        postProcess: PostProcess | None = None,
    ) -> None:
        super().start(ser)
        if (key := self.key) is not None:
            key.input(Hat.TOP_RIGHT)
            self.wait(0.1)
            key.input(Hat.CENTER)
        self.key = None


class RIGHT(UnitCommand):
    def __init__(self) -> None:
        super().__init__()

    def start(
        self,
        ser: Sender,
        postProcess: PostProcess | None = None,
    ) -> None:
        super().start(ser)
        if (key := self.key) is not None:
            key.input(Hat.RIGHT)
            self.wait(0.1)
            key.input(Hat.CENTER)
        self.key = None


class DOWN_RIGHT(UnitCommand):
    def __init__(self) -> None:
        super().__init__()

    def start(
        self,
        ser: Sender,
        postProcess: PostProcess | None = None,
    ) -> None:
        super().start(ser)
        if (key := self.key) is not None:
            key.input(Hat.BTM_RIGHT)
            self.wait(0.1)
            key.input(Hat.CENTER)
        self.key = None


class DOWN(UnitCommand):
    def __init__(self) -> None:
        super().__init__()

    def start(
        self,
        ser: Sender,
        postProcess: PostProcess | None = None,
    ) -> None:
        super().start(ser)
        if (key := self.key) is not None:
            key.input(Hat.BTM)
            self.wait(0.1)
            key.input(Hat.CENTER)
        self.key = None


class DOWN_LEFT(UnitCommand):
    def __init__(self) -> None:
        super().__init__()

    def start(
        self,
        ser: Sender,
        postProcess: PostProcess | None = None,
    ) -> None:
        super().start(ser)
        if (key := self.key) is not None:
            key.input(Hat.BTM_LEFT)
            self.wait(0.1)
            key.input(Hat.CENTER)
        self.key = None


class LEFT(UnitCommand):
    def __init__(self) -> None:
        super().__init__()

    def start(
        self,
        ser: Sender,
        postProcess: PostProcess | None = None,
    ) -> None:
        super().start(ser)
        if (key := self.key) is not None:
            key.input(Hat.LEFT)
            self.wait(0.1)
            key.input(Hat.CENTER)
        self.key = None


class UP_LEFT(UnitCommand):
    def __init__(self) -> None:
        super().__init__()

    def start(
        self,
        ser: Sender,
        postProcess: PostProcess | None = None,
    ) -> None:
        super().start(ser)
        if (key := self.key) is not None:
            key.input(Hat.TOP_LEFT)
            self.wait(0.1)
            key.input(Hat.CENTER)
        self.key = None
