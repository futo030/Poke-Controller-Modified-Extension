import logging
from typing import Any

from pokecontroller.core.controller import StickTilt
from pokecontroller.core.controller.switch.button import SwitchButton
from pokecontroller.core.controller.switch.dpad import SwitchDpad
from pokecontroller.core.controller.switch.serializers.leonardo import (
    SwitchControllerStateSerializer,
)
from pokecontroller.core.controller.switch.state import SwitchControllerState
from pokecontroller.core.serial import Serial
from pokecontroller.utils import platform

if not platform.is_macos():
    from pynput.keyboard import Key, Listener

logger = logging.getLogger(__name__)

KEYMAP_JSON_ACTIONS: dict[str, dict[str, Any]] = {
    "button": {
        "y": SwitchButton.Y,
        "b": SwitchButton.B,
        "x": SwitchButton.X,
        "a": SwitchButton.A,
        "l": SwitchButton.L,
        "r": SwitchButton.R,
        "zl": SwitchButton.ZL,
        "zr": SwitchButton.ZR,
        "minus": SwitchButton.MINUS,
        "plus": SwitchButton.PLUS,
        "lclick": SwitchButton.LS,
        "rclick": SwitchButton.RS,
        "home": SwitchButton.HOME,
        "capture": SwitchButton.CAPTURE,
    },
    "direction": {
        "right": StickTilt.RIGHT,
        "up": StickTilt.UP,
        "left": StickTilt.LEFT,
        "down": StickTilt.DOWN,
        "up_right": StickTilt.UP | StickTilt.RIGHT,
        "up_left": StickTilt.UP | StickTilt.LEFT,
        "down_right": StickTilt.DOWN | StickTilt.RIGHT,
        "down_left": StickTilt.DOWN | StickTilt.LEFT,
    },
    "dpad": {
        "right": SwitchDpad.RIGHT,
        "up": SwitchDpad.UP,
        "left": SwitchDpad.LEFT,
        "down": SwitchDpad.DOWN,
        "up_right": SwitchDpad.UP_RIGHT,
        "up_left": SwitchDpad.UP_LEFT,
        "down_right": SwitchDpad.DOWN_RIGHT,
        "down_left": SwitchDpad.DOWN_LEFT,
        "neutral": SwitchDpad.NEUTRAL,
    },
}


def parse_keymap_json(key_map_json: dict[str, dict[str, str]]) -> dict[Key | str, Any]:
    """キーマップJSONを解析してキーとアクションのマッピングを生成します.

    Args:
        key_map_json: キーマップ設定のJSON辞書.

    Returns:
        キーとアクションのマッピング辞書.
    """
    parsed: dict[Key | str, Any] = {}
    for kind, value in key_map_json.items():
        for action, key in value.items():
            if not isinstance(action, str):
                continue
            if len(key) == 1:
                parsed[key] = KEYMAP_JSON_ACTIONS[kind][action]
            else:
                if key.isdigit():
                    parsed[key] = KEYMAP_JSON_ACTIONS[kind][action]
                else:
                    parsed[getattr(Key, key)] = KEYMAP_JSON_ACTIONS[kind][action]
    return parsed


class SwitchKeyboard:
    """キーボード入力をSwitchコントローラー入力に変換するクラス.

    キーボードイベントをリスニングし、設定されたキーマップに基づいて
    Switchコントローラーの入力に変換してシリアルポートに送信します。
    """

    def __init__(self, serial: Serial, keymap: dict[Key | str, Any]) -> None:
        """SwitchKeyboardインスタンスを初期化します.

        Args:
            serial: シリアル通信インスタンス.
            keymap: キーとアクションのマッピング辞書.
        """
        self._serial = serial
        self._keymap = keymap

        self._state = SwitchControllerState()
        self._listener: Listener | None = None
        self._current_direction: int = 0

    def start(self) -> None:
        """キーボードリスナーを開始します.

        キーボードイベントの監視を開始し、入力の変換を有効にします。
        """
        logger.info("Starting Keyboard Controller")

        if self._listener is not None:
            return

        self._listener = Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self._listener.start()
        logger.info("Started Keyboard Controller")

    def stop(self) -> None:
        """キーボードリスナーを停止します.

        キーボードイベントの監視を停止し、入力の変換を無効にします。
        """
        logger.info("Stopping Keyboard Controller")

        if (listener := self._listener) is None:
            return
        listener.stop()
        listener.join()
        self._listener = None
        logger.info("Stopped Keyboard Controller")

    def _on_press(self, key: Key) -> None:
        logger.debug(f"on_press: {key}")
        action = self._get_action(key)
        if action is None:
            logger.debug(f"on_press: action is None")
            return

        if isinstance(action, SwitchButton):
            logger.debug(f"on_press: SwitchButton {action}")
            self._state.button.push([action])
        elif isinstance(action, SwitchDpad):
            logger.debug(f"on_press: SwitchDpad {action}")
            self._state.dpad.add(action)
        elif isinstance(action, StickTilt):
            logger.debug(f"on_press: StickTilt {action}")
            self._current_direction |= action
            self._state.lstick.tilt_full(self._current_direction)
        self._send_state()

    def _on_release(self, key: Key) -> None:
        logger.debug(f"on_release: {key}")
        action = self._get_action(key)
        if action is None:
            logger.debug(f"on_release: action is None")
            return

        if isinstance(action, SwitchButton):
            logger.debug(f"on_release: SwitchButton: {action}")
            self._state.button.release([action])
        elif isinstance(action, SwitchDpad):
            logger.debug(f"on_release: SwitchDpad: {action}")
            self._state.dpad.sub(action)
        elif isinstance(action, StickTilt):
            logger.debug(f"on_release: StickTilt: {action}")
            self._current_direction &= ~action
            self._state.lstick.tilt_full(self._current_direction)
        self._send_state()

    def _get_action(self, key: Key) -> Any | None:
        if key is None:
            logger.debug(f"_get_action: key is None")
            return None
        if hasattr(key, "char") and key.char in self._keymap:
            logger.debug(f"_get_action: key has char: {key.char}")
            return self._keymap[key.char]
        elif key in self._keymap:
            logger.debug(f"_get_action: key is in keymap: {key}")
            return self._keymap[key]
        logger.debug(f"_get_action: key not found")
        return None

    def _send_state(self) -> None:
        serialized = SwitchControllerStateSerializer.serialize(self._state)
        self._serial.write_line(serialized)
