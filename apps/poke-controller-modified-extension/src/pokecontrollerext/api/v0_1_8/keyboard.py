import configparser
import logging
import os

from pynput.keyboard import Key, KeyCode, Listener

from pokecontrollerext.api.v0_1_8.command.keys import (
    Button,
    Direction,
    Hat,
    KeyPress,
    Stick,
    Touchscreen,
)

logger = logging.getLogger(__name__)


# This handles keyboard interactions
class Keyboard:
    def __init__(self) -> None:
        self.listener = Listener(on_press=self.on_press, on_release=self.on_release)

    def listen(self) -> None:
        self.listener.start()
        logger.debug("Keyboard control start")

    def stop(self) -> None:
        self.listener.stop()
        logger.debug("Keyboard control stop")

    def on_press(self, key: KeyCode) -> None:
        try:
            logger.debug("alphanumeric key {0} pressed".format(key.char))
        except AttributeError:
            logger.error("special key {0} pressed".format(key))

    def on_release(self, key: KeyCode) -> None:
        logger.debug("{0} released".format(key))


# This regards a keyboard inputs as Switch controller
class SwitchKeyboardController(Keyboard):
    SETTING_PATH = os.path.join(
        os.path.dirname(__file__), "profiles", "default", "settings.ini"
    )

    def __init__(self, keyPress: KeyPress) -> None:
        super(SwitchKeyboardController, self).__init__()

        self.to_use = Button.A
        self.setting = configparser.ConfigParser()
        self.setting.optionxform = str  # type: ignore[assignment, method-assign]

        logger.debug("Loading Keyboard control key-map setting")
        if os.path.isfile(self.SETTING_PATH):
            self.setting.read(self.SETTING_PATH, encoding="utf-8")
        self.key = keyPress
        self.holding: list[str] = []
        self.holdingDir: list[Direction] = []
        self.key_map_B = {
            (i[1] if len(i[1]) == 1 else eval(str(i[1]))): eval(i[0])
            for i in self.setting.items("KeyMap-Button")
        }
        self.key_map_D = {
            (i[1] if len(i[1]) == 1 else eval(str(i[1]))): eval(i[0])
            for i in self.setting.items("KeyMap-Direction")
        }
        self.key_map_H = {
            (i[1] if len(i[1]) == 1 else eval(str(i[1]))): eval(i[0])
            for i in self.setting.items("KeyMap-Hat")
        }
        self.key_map = {**self.key_map_B, **self.key_map_D, **self.key_map_H}

        logger.debug("Initialization finished")

    def on_press(self, key: str | KeyCode | Direction | None) -> None:
        if key is None:
            logger.warning("Unknown key has input")

        try:
            _k = key.char  # type: ignore[union-attr]
            key_type = type(self.key_map[_k])
        except AttributeError:
            try:
                _k = key
                key_type = type(self.key_map[_k])
            except KeyError:
                return
        except Exception as e:
            logger.error("Key has not recognized")
            logger.error(type(e))
            logger.error(e)
            _k = None
            key_type = None

        try:
            if key_type is type(Button.A):
                if _k in self.holding:
                    return
                for k in self.key_map.keys():
                    if _k == k:
                        self.key.input(self.key_map[_k])
                        self.holding.append(_k)
            elif key_type is type(Direction.LEFT):
                if _k in self.holdingDir:
                    return
                for k in self.key_map.keys():
                    if _k == k:
                        self.holdingDir.append(_k)
                        self.inputDir(self.holdingDir)
            elif key_type is type(Hat.TOP):
                if _k in self.holding:
                    return
                for k in self.key_map.keys():
                    if _k == k:
                        self.key.input(self.key_map[_k])
                        self.holding.append(_k)

        # for special keys
        except AttributeError:
            if key in self.holdingDir:
                return

            for k in self.key_map.keys():
                if key == k:
                    self.holdingDir.append(key)  # type: ignore[arg-type]
                    self.inputDir(self.holdingDir)
                    # self._logger.debug(f"stick: {key}")

    def on_release(
        self,
        key: KeyCode,
    ) -> None:
        if key is None:
            logger.warning("Unknown key has input")
        try:
            _k = key.char
            key_type = type(self.key_map[_k])
        except AttributeError:
            try:
                _k = key
                key_type = type(self.key_map[_k])
            except KeyError:
                return
        except Exception as e:
            logger.error("Key has not recognized")
            logger.error(type(e))
            logger.error(e)
            _k = None
            key_type = None

        try:
            if key_type is type(Button.A):
                if _k in self.holding:
                    self.holding.remove(_k)
                    self.key.inputEnd(self.key_map[_k])
            elif key_type is type(Direction.LEFT):
                if _k in self.holdingDir:
                    self.holdingDir.remove(_k)
                    if not self.holdingDir:
                        self.key.inputEnd(self.key_map[_k])
                    self.inputDir(self.holdingDir)
            elif key_type is type(Hat.TOP):
                if _k in self.holding:
                    self.holding.remove(_k)
                    self.key.inputEnd(self.key_map[_k], unset_hat=True)

        except AttributeError as e:
            logger.debug(e)

    def inputDir(self, dirs: list[Direction]) -> None:
        logger.debug(dirs)
        if len(dirs) == 0:
            return
        elif len(dirs) == 1:
            self.key.input(self.key_map[dirs[0]])
        elif len(dirs) > 1:
            valid_dirs = dirs[-2:]  # set only last 2 directions
            to_input: list[Button | Hat | Stick | Direction | Touchscreen] = []
            if Key.up in valid_dirs:
                if (d := Direction.UP_RIGHT) and Key.right in valid_dirs:
                    to_input.append(d)
                elif (d := Direction.UP_LEFT) and Key.left in valid_dirs:
                    to_input.append(d)
            elif Key.down in valid_dirs:
                if (d := Direction.DOWN_LEFT) and Key.left in valid_dirs:
                    to_input.append(d)
                elif (d := Direction.DOWN_RIGHT) and Key.right in valid_dirs:
                    to_input.append(d)
            self.key.input(to_input)
