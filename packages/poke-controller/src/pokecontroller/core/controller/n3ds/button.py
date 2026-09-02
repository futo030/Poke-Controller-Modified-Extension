from enum import IntFlag, auto


class N3dsButton(IntFlag):
    """ニンテンドー3DSのボタンを表すフラグ.

    Attributes:
        A: Aボタン.
        B: Bボタン.
        X: Xボタン.
        Y: Yボタン.
        L: Lボタン.
        R: Rボタン.
        HOME: HOMEボタン.
        START: STARTボタン.
        SELECT: SELECTボタン.
        POWER: 電源ボタン.
    """

    A = auto()
    B = auto()
    X = auto()
    Y = auto()
    L = auto()
    R = auto()
    HOME = auto()
    START = auto()
    SELECT = auto()
    POWER = auto()
