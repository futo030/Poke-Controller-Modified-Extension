import logging
import platform
import tkinter as tk
from typing import Any

from pokecontroller.core import controller
from pokecontroller.core.controller import switch

from pokecontrollerext.singletons.app.model import get_app_model
from pokecontrollerext.singletons.runtime.resources import (
    get_app_resources,
)
from pokecontrollerext.widgets.frame import Frame
from pokecontrollerext.widgets.labelframe import Labelframe

A = "A"
B = "B"
X = "X"
Y = "Y"
L = "L"
R = "R"
ZL = "ZL"
ZR = "ZR"
LC = "L-C"
RC = "R-C"
LSL = "←"
LSU = "↑"
LSR = "→"
LSD = "↓"
CAP = "CAP"
HOME = "HOME"
MIN = "-"
PLUS = "+"
# @formatter:off (for PyCharm)
# fmt: off
BUTTONS_LAYOUT: list[list[str | None]] = [
    [ZL  , None, None, None, None, ZR  ],
    [L   , LC  , MIN , PLUS, X   , R   ],
    [None, LSU , None, Y   , None, A   ],
    [LSL , None, LSR , None, B   , None],
    [None, LSD , CAP , HOME, RC  , None],
]
# fmt: on
# @formatter:on
LEFT_FRAME_COLUMNS = 3

# ボタンの色
BUTTON_COLORS = {
    "bg": "#343434" if platform.system() == "Windows" else None,
    "fg": "#FFFFFF" if platform.system() == "Windows" else None,
}

logger = logging.getLogger(__name__)


class ControllerPane(Frame):
    BUTTON_CONFIGS: dict[str, dict[str, Any]] = {
        A: {
            "text": "A",
            "pressed": lambda self: self._controller.buttons.push(
                buttons=[switch.SwitchButton.A],
            ),
            "released": lambda self: self._controller.buttons.release(
                buttons=[switch.SwitchButton.A],
            ),
        },
        B: {
            "text": "B",
            "pressed": lambda self: self._controller.buttons.push(
                buttons=[switch.SwitchButton.B],
            ),
            "released": lambda self: self._controller.buttons.release(
                buttons=[switch.SwitchButton.B],
            ),
        },
        X: {
            "text": "X",
            "pressed": lambda self: self._controller.buttons.push(
                buttons=[switch.SwitchButton.X],
            ),
            "released": lambda self: self._controller.buttons.release(
                buttons=[switch.SwitchButton.X],
            ),
        },
        Y: {
            "text": "Y",
            "pressed": lambda self: self._controller.buttons.push(
                buttons=[switch.SwitchButton.Y],
            ),
            "released": lambda self: self._controller.buttons.release(
                buttons=[switch.SwitchButton.Y],
            ),
        },
        L: {
            "text": "L",
            "pressed": lambda self: self._controller.buttons.push(
                buttons=[switch.SwitchButton.L],
            ),
            "released": lambda self: self._controller.buttons.release(
                buttons=[switch.SwitchButton.L],
            ),
        },
        R: {
            "text": "R",
            "pressed": lambda self: self._controller.buttons.push(
                buttons=[switch.SwitchButton.R],
            ),
            "released": lambda self: self._controller.buttons.release(
                buttons=[switch.SwitchButton.R],
            ),
        },
        ZL: {
            "text": "ZL",
            "pressed": lambda self: self._controller.buttons.push(
                buttons=[switch.SwitchButton.ZL],
            ),
            "released": lambda self: self._controller.buttons.release(
                buttons=[switch.SwitchButton.ZL],
            ),
        },
        ZR: {
            "text": "ZR",
            "pressed": lambda self: self._controller.buttons.push(
                buttons=[switch.SwitchButton.ZR],
            ),
            "released": lambda self: self._controller.buttons.release(
                buttons=[switch.SwitchButton.ZR],
            ),
        },
        LC: {
            "text": "L-C",
            "pressed": lambda self: self._controller.buttons.push(
                buttons=[switch.SwitchButton.LS],
            ),
            "released": lambda self: self._controller.buttons.release(
                buttons=[switch.SwitchButton.LS],
            ),
        },
        RC: {
            "text": "R-C",
            "pressed": lambda self: self._controller.buttons.push(
                buttons=[switch.SwitchButton.RS],
            ),
            "released": lambda self: self._controller.buttons.release(
                buttons=[switch.SwitchButton.RS],
            ),
        },
        LSR: {
            "text": "→",
            "pressed": lambda self: self._controller.lstick.tilt_full(
                tilt=controller.StickTilt.RIGHT,
            ),
            "released": lambda self: self._controller.lstick.to_neutral(),
        },
        LSU: {
            "text": "↑",
            "pressed": lambda self: self._controller.lstick.tilt_full(
                tilt=controller.StickTilt.UP,
            ),
            "released": lambda self: self._controller.lstick.to_neutral(),
        },
        LSL: {
            "text": "←",
            "pressed": lambda self: self._controller.lstick.tilt_full(
                tilt=controller.StickTilt.LEFT,
            ),
            "released": lambda self: self._controller.lstick.to_neutral(),
        },
        LSD: {
            "text": "↓",
            "pressed": lambda self: self._controller.lstick.tilt_full(
                tilt=controller.StickTilt.DOWN,
            ),
            "released": lambda self: self._controller.lstick.to_neutral(),
        },
        CAP: {
            "text": "CAP",
            "pressed": lambda self: self._controller.buttons.push(
                buttons=[switch.SwitchButton.CAPTURE],
            ),
            "released": lambda self: self._controller.buttons.release(
                buttons=[switch.SwitchButton.CAPTURE],
            ),
        },
        HOME: {
            "text": "HOME",
            "pressed": lambda self: self._controller.buttons.push(
                buttons=[switch.SwitchButton.HOME],
            ),
            "released": lambda self: self._controller.buttons.release(
                buttons=[switch.SwitchButton.HOME],
            ),
        },
        MIN: {
            "text": "-",
            "pressed": lambda self: self._controller.buttons.push(
                buttons=[switch.SwitchButton.MINUS],
            ),
            "released": lambda self: self._controller.buttons.release(
                buttons=[switch.SwitchButton.MINUS],
            ),
        },
        PLUS: {
            "text": "+",
            "pressed": lambda self: self._controller.buttons.push(
                buttons=[switch.SwitchButton.PLUS],
            ),
            "released": lambda self: self._controller.buttons.release(
                buttons=[switch.SwitchButton.PLUS],
            ),
        },
    }

    def __init__(self, master: tk.Misc, *args: Any, **kwargs: Any) -> None:
        super().__init__(master, *args, **kwargs)

        resources = get_app_resources()
        self._controller = switch.SwitchController(serial=resources.serial)
        self._app_model = get_app_model()

        self.build_ui()

    def build_ui(self) -> None:
        labelframe = Labelframe(self, text="Software-Controller")

        # Wrapper Frame
        wrapper = Frame(labelframe)

        # Left
        left_frame = tk.Frame(wrapper, bg="#56ccf2")
        left_buttons = [bs[:LEFT_FRAME_COLUMNS] for bs in BUTTONS_LAYOUT]
        self._build_grid_frame(left_frame, left_buttons)

        # Right
        right_frame = tk.Frame(wrapper, bg="#e9514e")
        right_buttons = [bs[LEFT_FRAME_COLUMNS:] for bs in BUTTONS_LAYOUT]
        self._build_grid_frame(right_frame, right_buttons)

        # Layout
        left_frame.pack(expand=False, fill=tk.BOTH, side=tk.LEFT)
        right_frame.pack(expand=False, fill=tk.BOTH, side=tk.LEFT)
        wrapper.pack(expand=False, fill=tk.Y, anchor=tk.CENTER)
        labelframe.pack(expand=False, fill=tk.BOTH)

    def _build_grid_frame(
        self,
        frame: tk.Frame,
        button_matrix: list[list[str | None]],
    ) -> None:
        for row, buttons in enumerate(button_matrix):
            for column, button in enumerate(buttons):
                if button is None:
                    continue

                config = self.BUTTON_CONFIGS[button]
                b = tk.Button(
                    frame,
                    text=config["text"],
                    width=4,
                )
                if bg := BUTTON_COLORS.get("bg"):
                    b.config(bg=bg, highlightbackground=bg)
                if fg := BUTTON_COLORS.get("fg"):
                    b.config(fg=fg)

                def on_pressed(_: tk.Event, btn: str | None = button) -> None:
                    if btn is not None:
                        self._on_button_pressed(btn)

                def on_released(_: tk.Event, btn: str | None = button) -> None:
                    if btn is not None:
                        self._on_button_released(btn)

                b.bind("<ButtonPress>", func=on_pressed, add="")
                b.bind("<ButtonRelease>", func=on_released, add="")
                b.grid(row=row, column=column, padx=2, pady=2, sticky=tk.NSEW)

    def _on_button_pressed(self, button: str) -> None:
        logger.info(f"Button {button} pressed")
        self.BUTTON_CONFIGS[button]["pressed"](self)
        self._controller.send_state()

    def _on_button_released(self, button: str) -> None:
        logger.info(f"Button {button} released")
        self.BUTTON_CONFIGS[button]["released"](self)
        self._controller.send_state()
