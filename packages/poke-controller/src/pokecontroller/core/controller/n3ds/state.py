from pokecontroller.core.controller.button import ButtonState
from pokecontroller.core.controller.dpad import DpadState
from pokecontroller.core.controller.n3ds.dpad import N3dsDpad
from pokecontroller.core.controller.n3ds.touchscreen import N3dsTouchscreenState
from pokecontroller.core.controller.stick import (
    StickAxisRange,
    StickRange,
    StickState,
)

stick_range = StickRange(
    x=StickAxisRange(min=0, max=255, neutral=128),
    y=StickAxisRange(min=0, max=255, neutral=127),
)


class N3dsControllerState:
    """ニンテンドー3DSコントローラーの全体的な状態を管理するクラス.

    ボタン、十字キー、アナログスティック、タッチスクリーンの
    状態を統合して管理します。
    """

    def __init__(self) -> None:
        """N3dsControllerStateインスタンスを初期化します."""
        self._button = ButtonState()
        self._dpad = DpadState(neutral=N3dsDpad.NEUTRAL)
        self._stick = StickState(stick_range)
        self._touchscreen = N3dsTouchscreenState()

    @property
    def button(self) -> ButtonState:
        """ボタンの状態を取得します.

        Returns:
            ボタン状態管理オブジェクト.
        """
        return self._button

    @property
    def dpad(self) -> DpadState:
        """十字キーの状態を取得します.

        Returns:
            十字キー状態管理オブジェクト.
        """
        return self._dpad

    @property
    def stick(self) -> StickState:
        """アナログスティックの状態を取得します.

        Returns:
            アナログスティック状態管理オブジェクト.
        """
        return self._stick

    @property
    def touchscreen(self) -> N3dsTouchscreenState:
        """タッチスクリーンの状態を取得します.

        Returns:
            タッチスクリーン状態管理オブジェクト.
        """
        return self._touchscreen

    def reset(self) -> None:
        """すべての入力状態をリセットします."""
        self._button.reset()
        self._dpad.reset()
        self._stick.reset()
        self._touchscreen.reset()

    def clean(self) -> None:
        """スティックのis_dirtyフラグをクリアします."""
        self._stick.clean()
