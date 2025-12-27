import math
from dataclasses import dataclass
from enum import IntFlag, auto
from typing import Self

from pokecontroller.utils.math import clamp


class StickTilt(IntFlag):
    """アナログスティックの傾き方向を表すフラグ.

    Attributes:
        UP: 上方向への傾き.
        RIGHT: 右方向への傾き.
        DOWN: 下方向への傾き.
        LEFT: 左方向への傾き.
    """

    UP = auto()
    RIGHT = auto()
    DOWN = auto()
    LEFT = auto()


@dataclass(kw_only=True, frozen=True)
class StickAxisRange:
    """アナログスティックの軸の範囲を表すデータクラス.

    Attributes:
        min: 軸の最小値.
        max: 軸の最大値.
        neutral: ニュートラル位置の値.
    """

    min: int
    max: int
    neutral: int

    def clamp(self, value: int) -> int:
        """値を軸の範囲内に制限します.

        Args:
            value: 制限する値.

        Returns:
            min以上max以下に制限された値.
        """
        return clamp(value, self.min, self.max)


@dataclass(kw_only=True, frozen=True)
class StickRange:
    """アナログスティックのX軸とY軸の範囲を表すデータクラス.

    Attributes:
        x: X軸の範囲.
        y: Y軸の範囲.
    """

    x: StickAxisRange
    y: StickAxisRange


@dataclass
class StickPolar:
    """極座標でアナログスティックの位置を表すデータクラス.

    Attributes:
        degree: 角度（度数法）. 0度は右方向.
        r: 半径（0.0〜1.0）. デフォルトは1.0.
    """

    degree: float
    r: float = 1.0

    @classmethod
    def of(cls, degree: float, r: float = 1.0) -> Self:
        """極座標インスタンスを正規化して生成します.

        Args:
            degree: 角度（度数法）.
            r: 半径（0.0〜1.0の範囲に制限されます）.

        Returns:
            正規化されたStickPolarインスタンス.
        """
        return cls(degree % 360, clamp(r, 0.0, 1.0))

    def to_xy(self, stick_range: StickRange) -> tuple[int, int]:
        """極座標をXY座標に変換します.

        Args:
            stick_range: スティックの範囲情報.

        Returns:
            (x, y)のタプル. 各値はスティックの範囲内の整数値.
        """
        theta = math.radians(self.degree)
        x_center = (stick_range.x.max - stick_range.x.min) / 2
        y_center = (stick_range.y.max - stick_range.y.min) / 2
        x = math.ceil(x_center * math.cos(theta) * self.r + x_center)
        y = math.floor(y_center * math.sin(theta) * self.r + y_center)
        return x, y


class StickState:
    """アナログスティックの状態を管理するクラス.

    スティックの位置をXY座標で管理し、極座標による設定や
    傾き方向による操作をサポートします。
    """

    _tilt_coefficient = {
        tilt: coefficient
        for coefficient, tilt in enumerate(
            (
                # LDRU
                0b0010,  # RIGHT
                0b0011,  # UP|RIGHT
                0b0001,  # UP
                0b1001,  # UP|LEFT
                0b1000,  # LEFT
                0b1100,  # DOWN|LEFT
                0b0100,  # DOWN
                0b0110,  # DOWN|RIGHT
            )
        )
    }

    def __init__(
        self,
        stick_range: StickRange,
    ) -> None:
        """StickStateインスタンスを初期化します.

        Args:
            stick_range: スティックの範囲情報.
        """
        self._range = stick_range
        self._x = stick_range.x.neutral
        self._y = stick_range.y.neutral
        self._is_dirty = False

    @property
    def x(self) -> int:
        """スティックのX座標を取得します.

        Returns:
            現在のX座標値.
        """
        return self._x

    @property
    def y(self) -> int:
        """スティックのY座標を取得します.

        Returns:
            現在のY座標値.
        """
        return self._y

    @property
    def is_dirty(self) -> bool:
        """スティックの状態が変更されたかどうかを取得します.

        Returns:
            状態が変更された場合はTrue、それ以外はFalse.
        """
        return self._is_dirty

    @classmethod
    def from_polar(cls, stick_range: StickRange, degree: float, r: float = 1.0) -> Self:
        """極座標からStickStateインスタンスを生成します.

        Args:
            stick_range: スティックの範囲情報.
            degree: 角度（度数法）.
            r: 半径（0.0〜1.0）. デフォルトは1.0.

        Returns:
            指定された極座標に設定されたStickStateインスタンス.
        """
        self = cls(stick_range)
        self.tilt_by_polar(degree, r)
        return self

    def set_xy(self, x: int, y: int) -> None:
        """スティックの位置をXY座標で設定します.

        Args:
            x: X座標値（範囲内に自動的に制限されます）.
            y: Y座標値（範囲内に自動的に制限されます）.
        """
        self._set_xy(
            x=self._range.x.clamp(x),
            y=self._range.y.clamp(y),
        )

    def to_neutral(self) -> None:
        """スティックをニュートラル位置に戻します."""
        self._set_xy(
            x=self._range.x.neutral,
            y=self._range.y.neutral,
        )

    def reset(self) -> None:
        """スティックの状態をリセットします.

        to_neutral()と同じ動作をします。
        """
        self.to_neutral()

    def clean(self) -> None:
        """is_dirtyフラグをクリアします."""
        self._is_dirty = False

    def tilt_by_polar(self, degree: float, r: float = 1.0) -> None:
        """極座標でスティックを傾けます.

        Args:
            degree: 角度（度数法）.
            r: 半径（0.0〜1.0）. デフォルトは1.0.
        """
        polar = StickPolar.of(degree, r)
        self.set_xy(*polar.to_xy(self._range))

    def tilt_full(self, tilt: int) -> None:
        """指定された方向にスティックを最大限傾けます.

        Args:
            tilt: StickTiltフラグの組み合わせ.
        """
        coefficient = self._tilt_coefficient.get(tilt, None)
        if coefficient is None:
            self._set_xy(self._range.x.neutral, self._range.y.neutral)
        else:
            self.tilt_by_polar(45.0 * coefficient)

    def negate_tilt(self, tilts: list[StickTilt]) -> None:
        """指定された方向の傾きを打ち消します.

        Args:
            tilts: 打ち消す傾き方向のリスト.
        """
        x, y = self._x, self._y
        for tilt in tilts:
            if tilt == StickTilt.LEFT and x < self._range.x.neutral:
                x = self._range.x.neutral
            elif tilt == StickTilt.RIGHT and x > self._range.x.neutral:
                x = self._range.x.neutral
            elif tilt == StickTilt.DOWN and y < self._range.y.neutral:
                y = self._range.y.neutral
            elif tilt == StickTilt.UP and y > self._range.y.neutral:
                y = self._range.y.neutral
        self._set_xy(x, y)

    def get_tiltings(self) -> list[StickTilt]:
        """現在のスティックの傾き方向を取得します.

        Returns:
            現在の傾き方向を表すStickTiltのリスト.
        """
        tiltings = []
        if self._x < self._range.x.neutral:
            tiltings.append(StickTilt.LEFT)
        elif self._x > self._range.x.neutral:
            tiltings.append(StickTilt.RIGHT)
        if self._y < self._range.y.neutral:
            tiltings.append(StickTilt.DOWN)
        elif self._y > self._range.y.neutral:
            tiltings.append(StickTilt.UP)
        return tiltings

    def _set_xy(self, x: int, y: int) -> None:
        if self._x != x or self._y != y:
            self._x = x
            self._y = y
            self._is_dirty = True
