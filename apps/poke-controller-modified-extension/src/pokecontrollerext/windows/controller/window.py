import logging
import tkinter as tk
from typing import Any

from pokecontroller.core import controller
from pokecontroller.core.controller import switch

from pokecontrollerext.singletons.runtime.resources import (
    get_app_resources,
)
from pokecontrollerext.widgets.window import Window

logger = logging.getLogger(__name__)

A = "A"
B = "B"
X = "X"
Y = "Y"
L = "L"
R = "R"
ZL = "ZL"
ZR = "ZR"
LSC = "LSC"
RSC = "RSC"
LSR = "LSR"
LSUR = "LSUR"
LSU = "LSU"
LSUL = "LSUL"
LSL = "LSL"
LSDL = "LSDL"
LSD = "LSD"
LSDR = "LSDR"
HR = "HR"
HUR = "HUR"
HU = "HU"
HUL = "HUL"
HL = "HL"
HDL = "HDL"
HD = "HD"
HDR = "HDR"
RSR = "RSR"
RSUR = "RSUR"
RSU = "RSU"
RSUL = "RSUL"
RSL = "RSL"
RSDL = "RSDL"
RSD = "RSD"
RSDR = "RSDR"
CAP = "CAP"
HOME = "HOME"
MIN = "MIN"
PLUS = "PLUS"
# @formatter:off (for PyCharm)
# fmt: off
BUTTONS_LAYOUT: list[list[str | tuple[str, int] | None]] = [
    [(ZL, 3), None, None, None, None, None, None, (ZR, 3), None, None],
    [(L , 3), None, None, None, None, None, None, (R , 3), None, None],
    [None   , None, None, MIN , None, None, PLUS, None   , None, None],
    [LSUL   , LSU , LSUR, None, CAP , HOME, None, None   , X   , None],
    [LSL    , LSC , LSR , None, None, None, None, Y      , None, A   ],
    [LSDL   , LSD , LSDR, None, None, None, None, None   , B   , None],
    [None   , None, None, None, None, None, None, None   , None, None],
    [None   , HUL , HU  , HUR , None, None, RSUL, RSU    , RSUR, None],
    [None   , HL  , None, HR  , None, None, RSL , RSC    , RSR , None],
    [None   , HDL , HD  , HDR , None, None, RSDL, RSD    , RSDR, None],
]
# fmt: on
# @formatter:on
LEFT_FRAME_COLUMNS = 5

STYLES = {
    "button": {
        "bg": "",
        "fg": "",
    },
    "frame": {
        "left": "#95f1ff",
        "right": "#ff6b6b",
    },
}


class ControllerWindow(Window):
    BUTTON_CONFIGS: dict[str, dict[str, Any]] = {
        A: {
            "text": "A",
            "pressed": lambda self: self._controller.buttons.push(
                buttons=[switch.SwitchButton.A]
            ),
            "released": lambda self: self._controller.buttons.release(
                buttons=[switch.SwitchButton.A]
            ),
        },
        B: {
            "text": "B",
            "pressed": lambda self: self._controller.buttons.push(
                buttons=[switch.SwitchButton.B]
            ),
            "released": lambda self: self._controller.buttons.release(
                buttons=[switch.SwitchButton.B]
            ),
        },
        X: {
            "text": "X",
            "pressed": lambda self: self._controller.buttons.push(
                buttons=[switch.SwitchButton.X]
            ),
            "released": lambda self: self._controller.buttons.release(
                buttons=[switch.SwitchButton.X]
            ),
        },
        Y: {
            "text": "Y",
            "pressed": lambda self: self._controller.buttons.push(
                buttons=[switch.SwitchButton.Y]
            ),
            "released": lambda self: self._controller.buttons.release(
                buttons=[switch.SwitchButton.Y]
            ),
        },
        L: {
            "text": "L",
            "pressed": lambda self: self._controller.buttons.push(
                buttons=[switch.SwitchButton.L]
            ),
            "released": lambda self: self._controller.buttons.release(
                buttons=[switch.SwitchButton.L]
            ),
        },
        R: {
            "text": "R",
            "pressed": lambda self: self._controller.buttons.push(
                buttons=[switch.SwitchButton.R]
            ),
            "released": lambda self: self._controller.buttons.release(
                buttons=[switch.SwitchButton.R]
            ),
        },
        ZL: {
            "text": "ZL",
            "pressed": lambda self: self._controller.buttons.push(
                buttons=[switch.SwitchButton.ZL]
            ),
            "released": lambda self: self._controller.buttons.release(
                buttons=[switch.SwitchButton.ZL]
            ),
        },
        ZR: {
            "text": "ZR",
            "pressed": lambda self: self._controller.buttons.push(
                buttons=[switch.SwitchButton.ZR]
            ),
            "released": lambda self: self._controller.buttons.release(
                buttons=[switch.SwitchButton.ZR]
            ),
        },
        LSC: {
            "text": "L-C",
            "pressed": lambda self: self._controller.buttons.push(
                buttons=[switch.SwitchButton.LS]
            ),
            "released": lambda self: self._controller.buttons.release(
                buttons=[switch.SwitchButton.LS]
            ),
        },
        RSC: {
            "text": "R-C",
            "pressed": lambda self: self._controller.buttons.push(
                buttons=[switch.SwitchButton.RS]
            ),
            "released": lambda self: self._controller.buttons.release(
                buttons=[switch.SwitchButton.RS]
            ),
        },
        LSR: {
            "text": "→",
            "pressed": lambda self: self._controller.lstick.tilt_full(
                tilt=controller.StickTilt.RIGHT
            ),
            "released": lambda self: self._controller.lstick.to_neutral(),
        },
        LSUR: {
            "text": "↗",
            "pressed": lambda self: self._controller.lstick.tilt_full(
                tilt=controller.StickTilt.UP | controller.StickTilt.RIGHT
            ),
            "released": lambda self: self._controller.lstick.to_neutral(),
        },
        LSU: {
            "text": "↑",
            "pressed": lambda self: self._controller.lstick.tilt_full(
                tilt=controller.StickTilt.UP
            ),
            "released": lambda self: self._controller.lstick.to_neutral(),
        },
        LSUL: {
            "text": "↖",
            "pressed": lambda self: self._controller.lstick.tilt_full(
                tilt=controller.StickTilt.UP | controller.StickTilt.LEFT
            ),
            "released": lambda self: self._controller.lstick.to_neutral(),
        },
        LSL: {
            "text": "←",
            "pressed": lambda self: self._controller.lstick.tilt_full(
                tilt=controller.StickTilt.LEFT
            ),
            "released": lambda self: self._controller.lstick.to_neutral(),
        },
        LSDL: {
            "text": "↙",
            "pressed": lambda self: self._controller.lstick.tilt_full(
                tilt=controller.StickTilt.DOWN | controller.StickTilt.LEFT
            ),
            "released": lambda self: self._controller.lstick.to_neutral(),
        },
        LSD: {
            "text": "↓",
            "pressed": lambda self: self._controller.lstick.tilt_full(
                tilt=controller.StickTilt.DOWN
            ),
            "released": lambda self: self._controller.lstick.to_neutral(),
        },
        LSDR: {
            "text": "↘",
            "pressed": lambda self: self._controller.lstick.tilt_full(
                tilt=controller.StickTilt.DOWN | controller.StickTilt.RIGHT
            ),
            "released": lambda self: self._controller.lstick.to_neutral(),
        },
        HR: {
            "text": "→",
            "pressed": lambda self: self._controller.dpad.push(
                dpad=switch.SwitchDpad.RIGHT
            ),
            "released": lambda self: self._controller.dpad.reset(),
        },
        HUR: {
            "text": "↗",
            "pressed": lambda self: self._controller.dpad.push(
                dpad=switch.SwitchDpad.UP_RIGHT
            ),
            "released": lambda self: self._controller.dpad.reset(),
        },
        HU: {
            "text": "↑",
            "pressed": lambda self: self._controller.dpad.push(
                dpad=switch.SwitchDpad.UP
            ),
            "released": lambda self: self._controller.dpad.reset(),
        },
        HUL: {
            "text": "↖",
            "pressed": lambda self: self._controller.dpad.push(
                dpad=switch.SwitchDpad.UP_LEFT
            ),
            "released": lambda self: self._controller.dpad.reset(),
        },
        HL: {
            "text": "←",
            "pressed": lambda self: self._controller.dpad.push(
                dpad=switch.SwitchDpad.LEFT
            ),
            "released": lambda self: self._controller.dpad.reset(),
        },
        HDL: {
            "text": "↙",
            "pressed": lambda self: self._controller.dpad.push(
                dpad=switch.SwitchDpad.DOWN_LEFT
            ),
            "released": lambda self: self._controller.dpad.reset(),
        },
        HD: {
            "text": "↓",
            "pressed": lambda self: self._controller.dpad.push(
                dpad=switch.SwitchDpad.DOWN
            ),
            "released": lambda self: self._controller.dpad.reset(),
        },
        HDR: {
            "text": "↘",
            "pressed": lambda self: self._controller.dpad.push(
                dpad=switch.SwitchDpad.DOWN_RIGHT
            ),
            "released": lambda self: self._controller.dpad.reset(),
        },
        RSR: {
            "text": "→",
            "pressed": lambda self: self._controller.rstick.tilt_full(
                tilt=controller.StickTilt.RIGHT
            ),
            "released": lambda self: self._controller.rstick.to_neutral(),
        },
        RSUR: {
            "text": "↗",
            "pressed": lambda self: self._controller.rstick.tilt_full(
                tilt=controller.StickTilt.UP | controller.StickTilt.RIGHT
            ),
            "released": lambda self: self._controller.rstick.to_neutral(),
        },
        RSU: {
            "text": "↑",
            "pressed": lambda self: self._controller.rstick.tilt_full(
                tilt=controller.StickTilt.UP
            ),
            "released": lambda self: self._controller.rstick.to_neutral(),
        },
        RSUL: {
            "text": "↖",
            "pressed": lambda self: self._controller.rstick.tilt_full(
                tilt=controller.StickTilt.UP | controller.StickTilt.LEFT
            ),
            "released": lambda self: self._controller.rstick.to_neutral(),
        },
        RSL: {
            "text": "←",
            "pressed": lambda self: self._controller.rstick.tilt_full(
                tilt=controller.StickTilt.LEFT
            ),
            "released": lambda self: self._controller.rstick.to_neutral(),
        },
        RSDL: {
            "text": "↙",
            "pressed": lambda self: self._controller.rstick.tilt_full(
                tilt=controller.StickTilt.DOWN | controller.StickTilt.LEFT
            ),
            "released": lambda self: self._controller.rstick.to_neutral(),
        },
        RSD: {
            "text": "↓",
            "pressed": lambda self: self._controller.rstick.tilt_full(
                tilt=controller.StickTilt.DOWN
            ),
            "released": lambda self: self._controller.rstick.to_neutral(),
        },
        RSDR: {
            "text": "↘",
            "pressed": lambda self: self._controller.rstick.tilt_full(
                tilt=controller.StickTilt.DOWN | controller.StickTilt.RIGHT
            ),
            "released": lambda self: self._controller.rstick.to_neutral(),
        },
        CAP: {
            "text": "CAP",
            "pressed": lambda self: self._controller.buttons.push(
                buttons=[switch.SwitchButton.CAPTURE]
            ),
            "released": lambda self: self._controller.buttons.release(
                buttons=[switch.SwitchButton.CAPTURE]
            ),
        },
        HOME: {
            "text": "HOME",
            "pressed": lambda self: self._controller.buttons.push(
                buttons=[switch.SwitchButton.HOME]
            ),
            "released": lambda self: self._controller.buttons.release(
                buttons=[switch.SwitchButton.HOME]
            ),
        },
        MIN: {
            "text": "-",
            "pressed": lambda self: self._controller.buttons.push(
                buttons=[switch.SwitchButton.MINUS]
            ),
            "released": lambda self: self._controller.buttons.release(
                buttons=[switch.SwitchButton.MINUS]
            ),
        },
        PLUS: {
            "text": "+",
            "pressed": lambda self: self._controller.buttons.push(
                buttons=[switch.SwitchButton.PLUS]
            ),
            "released": lambda self: self._controller.buttons.release(
                buttons=[switch.SwitchButton.PLUS]
            ),
        },
    }

    def __init__(
        self,
        master: tk.Misc,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(master, *args, **kwargs)

        resources = get_app_resources()
        self._controller = switch.SwitchController(serial=resources.serial)

        self.title("Switch Controller Simulator")
        self.build_ui()
        self.resizable(False, False)

    def build_ui(self) -> None:
        # Left
        left_frame = tk.Frame(self, relief=tk.FLAT, padx=8, bg=STYLES["frame"]["left"])
        left_buttons = [bs[:LEFT_FRAME_COLUMNS] for bs in BUTTONS_LAYOUT]
        self._build_grid_frame(left_frame, left_buttons)

        # Right
        right_frame = tk.Frame(
            self, relief=tk.FLAT, padx=8, bg=STYLES["frame"]["right"]
        )
        right_buttons = [bs[LEFT_FRAME_COLUMNS:] for bs in BUTTONS_LAYOUT]
        self._build_grid_frame(right_frame, right_buttons)

        left_frame.pack(expand=False, fill=tk.BOTH, side=tk.LEFT)
        right_frame.pack(expand=False, fill=tk.BOTH, side=tk.LEFT)
        logger.info("Controller window built.")

    def _build_grid_frame(
        self,
        frame: tk.Frame,
        button_matrix: list[list[str | tuple[str, int] | None]],
    ) -> None:
        is_previous_row_empty = False
        for row, buttons in enumerate(button_matrix):
            for column, button_config in enumerate(buttons):
                if button_config is None:
                    continue
                if isinstance(button_config, tuple):
                    button, colspan = button_config
                else:
                    button, colspan = button_config, 1

                config = self.BUTTON_CONFIGS[button]
                b = tk.Button(
                    frame,
                    text=config["text"],
                    width=4 * (2 * colspan - 1),
                )
                if bg := STYLES["button"].get("bg"):
                    b.config(bg=bg, highlightbackground=bg)
                if fg := STYLES["button"].get("fg"):
                    b.config(fg=fg)

                def on_pressed(_: tk.Event, btn: str | None = button) -> None:
                    if btn is not None:
                        self._on_button_pressed(btn)

                def on_released(_: tk.Event, btn: str | None = button) -> None:
                    if btn is not None:
                        self._on_button_released(btn)

                b.bind("<ButtonPress>", func=on_pressed, add="")
                b.bind("<ButtonRelease>", func=on_released, add="")

                pady = (24, 2) if is_previous_row_empty else (2, 2)
                b.grid(row=row, column=column, columnspan=colspan, padx=2, pady=pady)

            is_previous_row_empty = all(button is None for button in buttons)

    def _on_button_pressed(self, button: str) -> None:
        logger.info(f"Button {button} pressed.")
        self.BUTTON_CONFIGS[button]["pressed"](self)
        self._controller.send_state()

    def _on_button_released(self, button: str) -> None:
        logger.info(f"Button {button} released.")
        self.BUTTON_CONFIGS[button]["released"](self)
        self._controller.send_state()
