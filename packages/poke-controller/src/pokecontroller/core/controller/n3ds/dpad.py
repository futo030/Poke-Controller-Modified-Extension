from enum import IntEnum


class N3dsDpad(IntEnum):
    """ニンテンドー3DSの十字キーの方向を表す列挙型.

    Attributes:
        NEUTRAL: ニュートラル状態（入力なし）.
        LEFT: 左方向.
        DOWN: 下方向.
        RIGHT: 右方向.
        UP: 上方向.
    """

    NEUTRAL = 0
    LEFT = 1
    DOWN = 2
    RIGHT = 4
    UP = 8
