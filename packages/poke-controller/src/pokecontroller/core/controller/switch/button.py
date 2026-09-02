from enum import IntFlag, auto


class SwitchButton(IntFlag):
    """Nintendo Switchのボタンを表すフラグ.

    Attributes:
        Y: Yボタン.
        B: Bボタン.
        A: Aボタン.
        X: Xボタン.
        L: Lボタン.
        R: Rボタン.
        ZL: ZLボタン.
        ZR: ZRボタン.
        MINUS: マイナスボタン.
        PLUS: プラスボタン.
        LS: 左スティック押し込み.
        RS: 右スティック押し込み.
        HOME: HOMEボタン.
        CAPTURE: キャプチャーボタン.
    """

    Y = auto()
    B = auto()
    A = auto()
    X = auto()
    L = auto()
    R = auto()
    ZL = auto()
    ZR = auto()
    MINUS = auto()
    PLUS = auto()
    LS = auto()
    RS = auto()
    HOME = auto()
    CAPTURE = auto()
