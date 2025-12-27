from pokecontroller.core.controller.button import ButtonState
from pokecontroller.core.controller.stick import (
    StickAxisRange,
    StickRange,
    StickState,
)
from pokecontroller.core.controller.switch.dpad import (
    SwitchDpad,
    SwitchDpadState,
)

STICK_RANGE = StickRange(
    x=StickAxisRange(min=0, max=255, neutral=128),
    y=StickAxisRange(min=0, max=255, neutral=127),
)


class SwitchControllerState:
    """Nintendo Switchコントローラーの全体的な状態を管理するクラス.

    ボタン、十字キー、左右のアナログスティックの状態を統合して管理します。
    """

    def __init__(self) -> None:
        """SwitchControllerStateインスタンスを初期化します."""
        self._button = ButtonState()
        self._dpad = SwitchDpadState(neutral=SwitchDpad.NEUTRAL)
        self._lstick = StickState(STICK_RANGE)
        self._rstick = StickState(STICK_RANGE)

    @property
    def button(self) -> ButtonState:
        """ボタンの状態を取得します.

        Returns:
            ボタン状態管理オブジェクト.
        """
        return self._button

    @property
    def dpad(self) -> SwitchDpadState:
        """十字キーの状態を取得します.

        Returns:
            十字キー状態管理オブジェクト.
        """
        return self._dpad

    @property
    def lstick(self) -> StickState:
        """左アナログスティックの状態を取得します.

        Returns:
            左アナログスティック状態管理オブジェクト.
        """
        return self._lstick

    @property
    def rstick(self) -> StickState:
        """右アナログスティックの状態を取得します.

        Returns:
            右アナログスティック状態管理オブジェクト.
        """
        return self._rstick

    def reset(self) -> None:
        """すべての入力状態をリセットします."""
        self._button.reset()
        self._dpad.reset()
        self._lstick.reset()
        self._rstick.reset()

    def clean(self) -> None:
        """両方のスティックのis_dirtyフラグをクリアします."""
        self._lstick.clean()
        self._rstick.clean()
