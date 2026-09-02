#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from Commands.PythonCommandBase import PythonCommand

from Commands.Keys import Touchscreen
import numpy as np


class Qingpi_Touchscreen_sample(PythonCommand):
    NAME = "Qingpi_Touchscreen_sample"

    def __init__(self):
        super().__init__()

    def do(self):
        # 3DS Controllerでも使えます。
        center_x = 160
        center_y = 120
        r = 50
        for i in range(0, 360, 3):
            w = (2.0 * np.pi / 360.0) * i
            x = int(r * np.cos(w) + center_x)
            y = int(r * np.sin(w) + center_y)
            self.hold(Touchscreen(x, y), wait=0.1)

        self.holdEnd(Touchscreen(0, 0))
        self.finish()
