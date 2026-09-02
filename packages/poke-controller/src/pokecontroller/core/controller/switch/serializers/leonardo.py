from pokecontroller.core.controller.switch.state import (
    STICK_RANGE,
    SwitchControllerState,
)


class SwitchControllerStateSerializer:
    """Leonardo形式でSwitchコントローラー状態をシリアライズするクラス."""

    @staticmethod
    def serialize(state: SwitchControllerState) -> str:
        """コントローラー状態をLeonardo形式の文字列にシリアライズします.

        Args:
            state: シリアライズするコントローラー状態.

        Returns:
            シリアライズされた文字列.
        """
        # buttons
        buttons = state.button.value << 2

        # sticks
        y_max = STICK_RANGE.y.max
        lstick, rstick = ("", "")
        if state.lstick.is_dirty:
            buttons |= 0x2
            lstick = (
                f"{format(state.lstick.x, 'x')} {format(y_max - state.lstick.y, 'x')}"
            )
        if state.rstick.is_dirty:
            buttons |= 0x1
            rstick = (
                f"{format(state.rstick.x, 'x')} {format(y_max - state.rstick.y, 'x')}"
            )

        # dpad
        dpad = str(int(state.dpad.value))

        # contract
        serialized = f"{format(buttons, '#06x')} {dpad} {lstick} {rstick}"

        state.clean()
        return serialized
