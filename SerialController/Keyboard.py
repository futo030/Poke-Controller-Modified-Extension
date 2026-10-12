#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import configparser
import os
import sys
import threading

from pynput.keyboard import Key, Listener
from logging import getLogger, DEBUG, NullHandler
from typing import TYPE_CHECKING, Iterable

from Commands.Keys import Button, Direction, Hat
import KeyMap

if TYPE_CHECKING:
    from pynput.keyboard import KeyCode

    from Commands.Keys import KeyPress


# This handles keyboard interactions
# Alt キー(押している間は、キーボードでの操作をゲーム機に送らない)
ALT_KEYS = (Key.alt, Key.alt_l, Key.alt_r, Key.alt_gr)
# Ctrl キー(Alt と同じ扱い。Ctrl + F(出力画面の検索)や Ctrl + C(コピー)などの、画面の操作に使うため)
CTRL_KEYS = (Key.ctrl, Key.ctrl_l, Key.ctrl_r)
# 押している間は、ほかのキーをゲーム機に送らないキー
MODIFIER_KEYS = ALT_KEYS + CTRL_KEYS

# Windows の GetGUIThreadInfo の flags: メニューを操作中 / システムメニュー(タイトルバーのメニュー) / ポップアップのメニュー
_GUI_MENU_FLAGS = 0x00000004 | 0x00000008 | 0x00000010


def menu_is_open() -> bool:
    """
    アプリのメニューを、操作している間か(メニューバーを Alt で選んだ状態、開いたメニュー、右クリックのメニュー、タイトルバーのメニュー)。
    その間の矢印キーや Enter は、メニューの操作に使うので、ゲーム機には送らない。
    Windows だけで調べる(ほかの OS と、調べられなかった場合は False)。キーを押すたびに呼ぶので、Windows に 1 回尋ねるだけにしている
    """
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        from ctypes import wintypes

        class GUITHREADINFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD), ("flags", wintypes.DWORD), ("hwndActive", wintypes.HWND),
                ("hwndFocus", wintypes.HWND), ("hwndCapture", wintypes.HWND), ("hwndMenuOwner", wintypes.HWND),
                ("hwndMoveSize", wintypes.HWND), ("hwndCaret", wintypes.HWND), ("rcCaret", wintypes.RECT),
            ]

        info = GUITHREADINFO()
        info.cbSize = ctypes.sizeof(GUITHREADINFO)
        # 画面(tkinter)は、メインスレッドで動く
        if not ctypes.windll.user32.GetGUIThreadInfo(threading.main_thread().native_id, ctypes.byref(info)):
            return False
        return bool(info.flags & _GUI_MENU_FLAGS)
    except Exception:
        return False


class Keyboard:
    """
    キーボードのキーの押し・離しを受け取るクラス(このクラスは、受け取ったキーを表示するだけ)
    """

    def __init__(self):
        """キーの受け付け(pynput の Listener)を用意する(受け付けは listen で始める)"""
        self._logger = getLogger(__name__)
        self._logger.addHandler(NullHandler())
        self._logger.setLevel(DEBUG)
        self._logger.propagate = True

        self.listener = Listener(
            on_press=self.on_press,
            on_release=self.on_release)

    def listen(self) -> None:
        """キーの受け付けを始める(別スレッドで動く)"""
        self.listener.start()
        self._logger.debug('Keyboard control start')

    def stop(self) -> None:
        """キーの受け付けをやめる"""
        self.listener.stop()
        self._logger.debug('Keyboard control stop')

    def on_press(self, key: Key | KeyCode | None) -> None:
        """キーを押したとき: 押したキーを表示する(動作の確認用)"""
        try:
            print('alphanumeric key {0} pressed'.format(key.char))
        except AttributeError:
            print('special key {0} pressed'.format(key))

    def on_release(self, key: Key | KeyCode | None) -> None:
        """キーを離したとき: 離したキーを表示する(動作の確認用)"""
        print('{0} released'.format(key))


# This regards a keyboard inputs as Switch controller
class SwitchKeyboardController(Keyboard):
    """
    キーボードのキーを、キーの対応(キーコンフィグ)に従って、コントローラーの入力として送るクラス
    SETTING_PATH: 設定ファイルの場所(プロファイルを切り替えるときに、クラスの値を書き換える)
    """

    # 入力欄に文字を打っている間など、キーをゲーム機に送らない間は True(suspend / resume で切り替える。全体で 1 つ)
    suspended = False

    SETTING_PATH = os.path.join(os.path.dirname(__file__), 'profiles', 'default', 'settings.ini')

    def __init__(self, keyPress: KeyPress | None, console: str = KeyMap.SWITCH):
        """
        keyPress: 入力を渡す先(シリアルポートに接続していない場合は None)
        console: キーの対応(キーコンフィグ)を使うゲーム機
        """
        super(SwitchKeyboardController, self).__init__()

        self._logger = getLogger(__name__)
        self._logger.addHandler(NullHandler())
        self._logger.setLevel(DEBUG)
        self._logger.propagate = True

        self.to_use = Button.A
        self.key = keyPress
        self.holding = []
        self.holdingDir = []
        self.holdingHatDir = []
        # 押している Alt キーと、Alt を押している間に押されたキー(離すまで、ゲーム機には送らない)
        self._alt_keys = set()
        self._ignored_keys = set()
        self.loadKeyMap(console)

        self._logger.debug('Initialization finished')

    def loadKeyMap(self, console: str = KeyMap.SWITCH) -> None:
        """
        設定ファイルから、キーの対応(キーコンフィグ)を読み込む
        console: キーの対応を使うゲーム機
        """
        self.setting = configparser.ConfigParser()
        self.setting.optionxform = str

        self._logger.debug('Loading Keyboard control key-map setting')
        if os.path.isfile(self.SETTING_PATH):
            self.setting.read(self.SETTING_PATH, encoding='utf-8')
        # ボタンと十字キーは、ゲーム機ごとのキーの対応を使う。左スティック(矢印キー)は共通
        keymap = KeyMap.load_keymap(self.setting, console)
        self.key_map_B = self._to_key_map((name, value) for name, value in keymap.items() if name.startswith("Button."))
        self.key_map_D = self._to_key_map(
            self.setting.items("KeyMap-Direction") if self.setting.has_section("KeyMap-Direction") else ()
        )
        self.key_map_H = self._to_key_map((name, value) for name, value in keymap.items() if name.startswith("Hat."))
        self.key_map = {**self.key_map_B, **self.key_map_D, **self.key_map_H}
        # self._logger.debug(self.key_map)

    def reloadKeyMap(self, console: str = KeyMap.SWITCH) -> None:
        """
        キー入力の受け付けを止めずに、キーの対応を読み直す。押したままのキーの入力は離す。
        (Macでは、画面の表示中に受け付けを開始し直せないため、受け付けは続けたままにする)
        console: キーの対応を使うゲーム機
        """
        self._releaseHolding()
        self.loadKeyMap(console)

    def _to_key_map(self, items: Iterable[tuple[str, str]]) -> dict:
        """
        (ボタンの名前, キー) の並びを、キー -> ボタン の辞書にする(読めないものは飛ばす)
        辞書のキーは、文字のキーなら1文字、それ以外は pynput の Key。値は Button / Hat / Direction
        """
        key_map = {}
        for name, value in items:
            try:
                key_map[value if len(value) == 1 else eval(str(value))] = eval(name)
            except Exception:
                self._logger.warning(f"Invalid key map is ignored: {name} = {value}")
        return key_map

    def stop(self) -> None:
        """キーの受け付けをやめ、押したままのキーの入力を離す"""
        super(SwitchKeyboardController, self).stop()
        # 押したまま停止した(フォーカスが外れた等)キーの入力を離す
        self._releaseHolding()

    def releaseAll(self) -> None:
        """押したままのキーの入力を、すべて離す(メニューの「すべての入力を離す」)"""
        self._releaseHolding()

    def suspend(self) -> None:
        """
        キーをゲーム機に送るのを、いったんやめる(入力欄に文字を打つ間など)。押したままのキーの入力は、離す。
        resume() を呼ぶまで続く(受け付けを作り直しても引き継ぐように、クラスで覚える)
        """
        SwitchKeyboardController.suspended = True
        # 今押しているキー(検索の欄を開いた Ctrl + F など)は、離すまで送らないままにする
        alt_keys, ignored_keys = self._alt_keys, self._ignored_keys
        self._releaseHolding()
        self._alt_keys, self._ignored_keys = alt_keys, ignored_keys

    @staticmethod
    def resume() -> None:
        """suspend() でやめていた、キーをゲーム機に送る動きを、元に戻す"""
        SwitchKeyboardController.suspended = False

    def _releaseHolding(self) -> None:
        """押したままのキーの記録を消し、この入力源の入力をすべて離す"""
        self._alt_keys = set()
        self._ignored_keys = set()
        self.holding = []
        self.holdingDir = []
        self.holdingHatDir = []
        if self.key is not None:
            self.key.release()

    @staticmethod
    def _menuIsOpen() -> bool:
        """メニューを操作している間か(menu_is_open。テストで差し替えられるように、ここを通す)"""
        return menu_is_open()

    @staticmethod
    def _keyId(key: Key | KeyCode) -> object:
        """
        キーを見分ける値(同じキーなら、Alt を押していても・離していても同じ値になるもの)
        戻り値: 仮想キーコード(int)。無ければ小文字にした文字、それも無ければキーそのもの
        """
        vk = getattr(key, 'vk', None)
        if vk is not None:
            return vk
        char = getattr(key, 'char', None)
        return char.lower() if isinstance(char, str) else key

    def _ignoresPress(self, key: Key | KeyCode) -> bool:
        """
        Alt を押している間のキーは、メニューを開く操作(Alt + F など)に使うので、ゲーム機には送らない。
        Alt を先に離しても、そのキーを離すまでは送らない(キーを押し続けている間の繰り返しで、送ってしまわないように)。
        Alt 自体にボタンを割り当てている場合は、これまでどおり送る。
        Ctrl も、Alt と同じ扱い(Ctrl + F、Ctrl + C などの、画面の操作に使うため)。
        入力欄に文字を打っている間(suspended)に押したキーも、送らない(離すまでは、打ち終わった後も送らない)。
        メニューを操作している間(Alt + F で開いた後に、Alt を離して押す矢印キーや Enter など)に押したキーも、同じ
        """
        if SwitchKeyboardController.suspended or self._menuIsOpen():
            self._ignored_keys.add(self._keyId(key))
            return True
        if key in MODIFIER_KEYS and key not in self.key_map:
            self._alt_keys.add(key)
            return True
        key_id = self._keyId(key)
        if self._alt_keys:
            self._ignored_keys.add(key_id)
        return key_id in self._ignored_keys

    def _ignoresRelease(self, key: Key | KeyCode) -> bool:
        """
        離したキーが、ゲーム機に送らないキー(Alt / Ctrl、それを押している間に押したキー、入力欄に打ったキー)かを返し、
        その記録を消す
        """
        if SwitchKeyboardController.suspended:
            self._alt_keys.discard(key)
            self._ignored_keys.discard(self._keyId(key))
            return True
        if key in MODIFIER_KEYS and key not in self.key_map:
            self._alt_keys.discard(key)
            return True
        key_id = self._keyId(key)
        if key_id in self._ignored_keys:
            self._ignored_keys.discard(key_id)
            return True
        return False

    def on_press(self, key: Key | KeyCode | None) -> None:
        """
        キーを押したとき(pynput のスレッドから呼ばれる): 対応するボタン・十字キー・左スティックの入力を送る
        (押し続けている間の繰り返しでは送り直さない。対応のないキーは何もしない)
        """
        # for debug (show row key data)
        # super().on_press(key)

        if key is not None and self._ignoresPress(key):
            return

        if key is None:
            print('unknown key has input')
            self._logger.warning('Unknown key has input')

        # self._logger.debug(f"key type is {type(key)}")
        # self._logger.debug(f"key  is '{type(key)}'")
        # self._logger.debug(f"holding is {self.holding}")

        try:
            _k = key.char
            key_type = (type(self.key_map[_k]))
        except AttributeError:
            try:
                _k = key
                key_type = (type(self.key_map[_k]))
            except KeyError:
                return
        except KeyError:
            # 対応のない文字のキー(Ctrl と一緒に押したときの制御文字を含む)は、何もしない
            return
        except Exception as e:
            self._logger.error("Key has not recognized")
            self._logger.error(type(e))
            self._logger.error(e)
            _k = None
            key_type = None

        try:
            # self._logger.debug(self.holding)
            if key_type is type(Button.A):
                # self._logger.debug("Button pushed")
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
                # self._logger.debug("Hat pushed")
                if _k in self.holding:
                    return
                for k in self.key_map.keys():
                    if _k == k:
                        self.key.input(self.key_map[_k])
                        self.holding.append(_k)
                        # self._logger.debug(f"stick: {key}")
            # elif key_type is type(Hat.TOP):
            #     self._logger.debug("Hat")
            #     if _k in self.holdingHatDir:
            #         return
            #     for k in self.key_map.keys():
            #         if _k == k:
            #             self.holdingHatDir.append(_k)
            #             self.inputDir(self.holdingHatDir)
            #             # self._logger.debug(f"stick: {key}")
            # self._logger.debug(f"k is {_k}")

        # for special keys
        except AttributeError:
            if key in self.holdingDir:
                return

            for k in self.key_map.keys():
                if key == k:
                    self.holdingDir.append(key)
                    self.inputDir(self.holdingDir)
                    # self._logger.debug(f"stick: {key}")

    def on_release(self, key: Key | KeyCode | None) -> None:
        """
        キーを離したとき(pynput のスレッドから呼ばれる): 対応する入力を離す
        (左スティックは、押しているキーが残っていれば、残りの方向を送り直す)
        """
        # self._logger.debug(f"key  is '{key}'")

        if key is not None and self._ignoresRelease(key):
            return

        if key is None:
            print('unknown key has released')
            self._logger.warning('Unknown key has input')
        try:
            _k = key.char
            key_type = (type(self.key_map[_k]))
        except AttributeError:
            try:
                _k = key
                key_type = (type(self.key_map[_k]))
            except KeyError:
                return
        except KeyError:
            # 対応のない文字のキー(Ctrl と一緒に押したときの制御文字を含む)は、何もしない
            return
        except Exception as e:
            self._logger.error("Key has not recognized")
            self._logger.error(type(e))
            self._logger.error(e)
            _k = None
            key_type = None

        try:
            if key_type is type(Button.A):
                # self._logger.debug("Button released")
                if _k in self.holding:
                    self.holding.remove(_k)
                    # if not self.holdingDir:
                    #     self.key.inputEnd(self.key_map[_k])
                    self.key.inputEnd(self.key_map[_k])
            elif key_type is type(Direction.LEFT):
                # self._logger.debug("Direction")
                if _k in self.holdingDir:
                    self.holdingDir.remove(_k)
                    if not self.holdingDir:
                        self.key.inputEnd(self.key_map[_k])
                        # self._logger.debug(f"holding {self.holdingDir}")
                    self.inputDir(self.holdingDir)
            elif key_type is type(Hat.TOP):
                # self._logger.debug(f"Hat released, {self.key_map[_k]}")
                if _k in self.holding:
                    self.holding.remove(_k)
                    # self._logger.debug("try")
                    # if not self.holdingDir:
                    #     self.key.inputEnd(self.key_map[_k], unset_hat=True)
                    self.key.inputEnd(self.key_map[_k], unset_hat=True)
            # elif key_type is type(Hat.TOP):
            #     if _k in self.holdingHatDir:
            #         self.holdingHatDir.remove(_k)
            #         if not self.holdingHatDir:
            #             self.key.inputEnd(self.key_map[_k])
            #             # self._logger.debug(f"holding {self.holdingDir}")
            #         self.inputDir(self.holdingHatDir)
            # Todo: Hat のリリース処理追加

            # self._logger.debug("done")
            # self._logger.debug(f"push out {self.key_map[key.char]}")

        except AttributeError as e:
            self._logger.debug(e)
            # if key in self.holdingDir:
            #     self.holdingDir.remove(key)
            #     if self.holdingDir == []:
            #         self.key.inputEnd(self.key_map[key])
            #         # self._logger.debug(f"holding {self.holdingDir}")
            #     self.inputDir(self.holdingDir)

    def inputDir(self, dirs: list) -> None:
        """
        押している方向のキーから、左スティックの入力を送る
        dirs: 押している方向のキー(押した順)。1つならその方向、2つ以上なら最後の2つを斜めの方向にして送る
        (最後の2つが斜めにならない組み合わせ(上と下、左と右など)の場合は、何も送らず、今の向きのままにする)
        """
        self._logger.debug(dirs)
        if len(dirs) == 0:
            return
        elif len(dirs) == 1:
            self.key.input(self.key_map[dirs[0]])
        elif len(dirs) > 1:
            valid_dirs = dirs[-2:]  # set only last 2 directions
            to_input = []
            if Key.up in valid_dirs:
                if Key.right in valid_dirs:
                    to_input.append(Direction.UP_RIGHT)
                elif Key.left in valid_dirs:
                    to_input.append(Direction.UP_LEFT)
            elif Key.down in valid_dirs:
                if Key.left in valid_dirs:
                    to_input.append(Direction.DOWN_LEFT)
                elif Key.right in valid_dirs:
                    to_input.append(Direction.DOWN_RIGHT)

            # if Key.up in valid_dirs:
            #     if Key.right in valid_dirs:
            #         to_input.append(Direction.UP_RIGHT)
            #     elif Key.left in valid_dirs:
            #         to_input.append(Direction.UP_LEFT)
            # elif Key.down in valid_dirs:
            #     if Key.left in valid_dirs:
            #         to_input.append(Direction.DOWN_LEFT)
            #     elif Key.right in valid_dirs:
            #         to_input.append(Direction.DOWN_RIGHT)
            if to_input:
                self.key.input(to_input)
