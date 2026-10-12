#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
設定の編集: ショートカット、目隠し(Mask)、タッチスクリーンの範囲、キーコンフィグ、
コントローラーの本体の色、通知先(Discord / LINE)

画面(tkinter)には触れない。変更できない場合は EditError(メッセージは、そのまま表示できる文)を送出する。
"""
from __future__ import annotations

import configparser
import os
from logging import getLogger, DEBUG, NullHandler
from typing import TYPE_CHECKING, Any, Callable

import ControllerColors
import KeyMap
import Profile
from DiscordNotify import (
    DEFAULT_WEBHOOK,
    RECEIVE_SECTION,
    Discord_Notify,
    check_webhook_name,
    is_default_webhook_set,
    load_setting,
    next_webhook_name,
    save_setting,
    webhook_names,
)
from LineNotify import Line_Notify
from Mask import DEFAULT_MASK_COLOR, MASK_SHAPES, Mask, draw_masks, hex_to_bgr, load_masks, save_masks
from services import geometry
from services.settings_store import AppSettings

if TYPE_CHECKING:
    from pynput.keyboard import Key, KeyCode

    from services.app_core import AppCore

_logger = getLogger(__name__)
_logger.addHandler(NullHandler())
_logger.setLevel(DEBUG)
_logger.propagate = True

SERIAL_CONTROLLER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 目隠しの書き出し先
MASK_DIR = os.path.join(SERIAL_CONTROLLER_DIR, "Masks")
MASK_EXTENSION = ".json"
# 目隠しとして追加する範囲の、最小の大きさ(これより小さい範囲は追加しない)
MASK_MIN_SIZE = 2
# ショートカットが未設定のときの値
SHORTCUT_NONE = "None"
SHORTCUT_EMPTY = "(empty)"
DISCORD_FIELDS = ("webhook_url", "username", "avatar_url")


class EditError(Exception):
    """設定を変更できない(メッセージは、そのまま表示できる文)"""


def check_file_name(name: str) -> str:
    """
    ファイルの名前として使えるかを確かめて、前後の空白を除いた名前を返す(フォルダは指定できない)
    """
    name = str(name).strip()
    if name.lower().endswith(MASK_EXTENSION):
        name = name[: -len(MASK_EXTENSION)]
    if name == "" or name in (".", "..") or any(character in name for character in '\\/:*?"<>|\r\n\0'):
        raise EditError('ファイルの名前に使えない文字があります。(\\ / : * ? " < > | は使えません)')
    return name


def is_valid_key(text: object) -> bool:
    """
    キーコンフィグのキーとして保存できる文字か(文字でない値は False)。
    - 1文字(文字のキー)
    - "Key.名前"(pynput の特殊キーの名前)
    - 数字だけ(どのキーにも当たらない値。未設定を表す)
    設定ファイルのキーは、読み込むときにプログラムとして評価されるので、この形以外は保存しない
    """
    if not isinstance(text, str) or text == "":
        return False
    if len(text) == 1:
        return True
    if text.isdigit():
        return True
    if text.startswith("Key."):
        try:
            from pynput.keyboard import Key
        except Exception:
            return False
        return text[4:] in Key.__members__
    return False


class EditorService:
    """
    ショートカット・目隠し・タッチスクリーンの範囲・キーコンフィグ・本体の色・通知先の編集。
    番号や座標は、画面(JSON など)から届くので、型を決めずに受け取り(Any)、数値に変えてから使う
    """

    def __init__(self, core: AppCore):
        """
        core: アプリ本体(AppCore)
        """
        self.core = core
        self._key_listener = None

    def _done(self, topic: str = "settings") -> None:
        """設定を保存して、変更を知らせる(topic: 変わったものの名前)"""
        self.core.settings.save()
        self.core._notify(topic)

    # ================================================================ ショートカット

    def shortcuts(self) -> list:
        """ショートカットの一覧: [{"num": 番号(1～), "class": 種別("None" は未設定), "name": コマンド名}, ...]"""
        settings = self.core.settings
        return [
            {"num": num, "class": settings.command_class_dict[str(num)], "name": settings.command_name_dict[str(num)]}
            for num in range(1, AppSettings.SHORTCUT_NUM + 1)
        ]

    def _shortcut_number(self, num: Any) -> int:
        """ショートカットの番号を、整数にして返す(1 ～ SHORTCUT_NUM でない場合は EditError)"""
        try:
            num = int(num)
        except (TypeError, ValueError):
            num = 0
        if not 1 <= num <= AppSettings.SHORTCUT_NUM:
            raise EditError(f"ショートカットの番号は 1 ～ {AppSettings.SHORTCUT_NUM} です。")
        return num

    def set_shortcut(self, num: Any, command_type: str, name: str) -> None:
        """
        ショートカットに、コマンドを割り当てて保存する。
        num: 番号(1～)、command_type: 種別("Python" / "Mcu")、name: コマンド名。一覧に無いコマンドは EditError
        """
        num = self._shortcut_number(num)
        core = self.core
        from services import command_catalog, command_service

        command_type, error = command_catalog.find_named_command(
            command_type, name, core.command_names(command_service.PYTHON), core.command_names(command_service.MCU)
        )
        if command_type is None:
            raise EditError(f"shortcut {error}")
        core.settings.command_class_dict[str(num)] = command_type
        core.settings.command_name_dict[str(num)] = name
        self._done()

    def clear_shortcut(self, num: Any) -> None:
        """ショートカットの割り当てを消して保存する"""
        num = self._shortcut_number(num)
        self.core.settings.command_class_dict[str(num)] = SHORTCUT_NONE
        self.core.settings.command_name_dict[str(num)] = SHORTCUT_EMPTY
        self._done()

    def start_shortcut(self, num: Any) -> bool:
        """ショートカットに割り当てたコマンドを開始する。開始できたかを返す(未設定の場合は False)"""
        num = self._shortcut_number(num)
        settings = self.core.settings
        command_type = settings.command_class_dict[str(num)]
        if command_type == SHORTCUT_NONE:
            print(f"shortcut command ({num}) is not assigned.")
            return False
        return self.core.start_command(command_type, settings.command_name_dict[str(num)])

    # ================================================================ 目隠し(Mask)

    def masks_state(self) -> dict:
        """目隠しの一覧・表示の設定・選べる形・書き出したファイルの名前(JSON にできる値だけ)"""
        settings = self.core.settings
        return {
            "items": [
                {"shape": m.shape, "x1": m.x1, "y1": m.y1, "x2": m.x2, "y2": m.y2, "color": m.color, "enabled": m.enabled}
                for m in self.core.masks
            ],
            "show": bool(settings.is_show_mask),
            "apply_to_capture": bool(settings.is_mask_apply_to_capture),
            "shapes": list(MASK_SHAPES),
            "files": self.mask_files(),
        }

    def _masks_changed(self) -> None:
        """目隠しの変更を、設定とカメラ(キャプチャーに目隠しを描くか)に反映して保存する"""
        core = self.core
        core.settings.masks = [mask.to_text() for mask in core.masks]
        if core.settings.is_show_mask and core.settings.is_mask_apply_to_capture:
            core.camera.capture_filter = lambda frame: draw_masks(frame, core.masks)
        else:
            core.camera.capture_filter = None
        self._done()

    def _mask(self, index: Any) -> Mask:
        """その番号(0 始まり)の目隠しを返す(無い場合は EditError)"""
        try:
            index = int(index)
        except (TypeError, ValueError):
            index = -1
        if not 0 <= index < len(self.core.masks):
            raise EditError("その目隠しはありません。")
        return self.core.masks[index]

    def _clamp_mask(self, x1: Any, y1: Any, x2: Any, y2: Any) -> tuple | None:
        """
        座標を整数に丸め、左上・右下の順にそろえて、カメラ画像の中に収める。収めた結果が空になる場合は None
        (数値として読めない場合は EditError)
        """
        try:
            x1, y1, x2, y2 = (int(round(float(v))) for v in (x1, y1, x2, y2))
        except (TypeError, ValueError):
            raise EditError("目隠しの座標は数値で指定してください。")
        x1, x2 = min(x1, x2), max(x1, x2)
        y1, y2 = min(y1, y2), max(y1, y2)
        return geometry.clamp_area(x1, y1, x2, y2, *self.core.camera.capture_size)

    def add_mask(self, shape: str, x1: Any, y1: Any, x2: Any, y2: Any) -> None:
        """
        目隠しを足す(座標は、カメラ画像の上の値)
        shape: 形(MASK_SHAPES のどれか)。形が違う場合と、範囲が小さすぎる場合は EditError
        """
        if shape not in MASK_SHAPES:
            raise EditError(f"目隠しの形に指定できない値です: {shape}")
        area = self._clamp_mask(x1, y1, x2, y2)
        if area is None or area[2] - area[0] < MASK_MIN_SIZE or area[3] - area[1] < MASK_MIN_SIZE:
            raise EditError("Mask: 範囲が小さすぎるため、追加しませんでした。")
        self.core.masks.append(Mask(shape, *area, DEFAULT_MASK_COLOR, True))
        self._masks_changed()

    def update_mask(self, index: Any, values: dict) -> None:
        """
        目隠しを変更する。values: 変更する項目(shape / x1 / y1 / x2 / y2 / color / enabled)
        """
        mask = self._mask(index)
        if "shape" in values:
            if values["shape"] not in MASK_SHAPES:
                raise EditError(f"目隠しの形に指定できない値です: {values['shape']}")
            mask.shape = values["shape"]
        if "color" in values:
            color = ControllerColors.normalize_color(values["color"])
            if color is None:
                raise EditError(f"色として読めません: {values['color']}")
            hex_to_bgr(color)
            mask.color = color.lower()
        if "enabled" in values:
            mask.enabled = bool(values["enabled"])
        if any(name in values for name in ("x1", "y1", "x2", "y2")):
            area = self._clamp_mask(*(values.get(name, getattr(mask, name)) for name in ("x1", "y1", "x2", "y2")))
            if area is None:
                raise EditError("Mask: 範囲が空になるため、変更しませんでした。")
            mask.x1, mask.y1, mask.x2, mask.y2 = area
        self._masks_changed()

    def delete_mask(self, index: Any) -> None:
        """その番号(0 始まり)の目隠しを消す"""
        mask = self._mask(index)
        self.core.masks.remove(mask)
        self._masks_changed()

    def set_mask_options(self, show: bool | None = None, apply_to_capture: bool | None = None) -> None:
        """
        目隠しを表示するか(show)と、キャプチャーにも描くか(apply_to_capture)を変える(None の項目は変えない)
        """
        settings = self.core.settings
        if show is not None:
            settings.is_show_mask = bool(show)
        if apply_to_capture is not None:
            settings.is_mask_apply_to_capture = bool(apply_to_capture)
        self._masks_changed()

    def mask_files(self) -> list:
        """書き出した目隠しのファイルの名前の一覧(拡張子なし。フォルダーが無ければ空)"""
        try:
            names = sorted(os.listdir(MASK_DIR), key=str.lower)
        except OSError:
            return []
        return [name[: -len(MASK_EXTENSION)] for name in names if name.lower().endswith(MASK_EXTENSION)]

    def save_mask_file(self, name: str) -> None:
        """
        今の目隠しを、Masks フォルダーのファイルに書き出す(name: 拡張子なしの名前)。
        目隠しが無い場合、名前が使えない場合、書き出せない場合は EditError
        """
        core = self.core
        if not core.masks:
            raise EditError("書き出す目隠しがありません。")
        name = check_file_name(name)
        path = os.path.join(MASK_DIR, name + MASK_EXTENSION)
        try:
            os.makedirs(MASK_DIR, exist_ok=True)
            save_masks(path, core.masks)
        except OSError as e:
            _logger.error(f"Failed to save masks: {e}")
            raise EditError(f"書き出せませんでした。({e})")
        print(f"Mask: {len(core.masks)}個の目隠しを書き出しました。({path})")
        core._notify("settings")

    def load_mask_file(self, name: str, replace: bool) -> None:
        """
        ファイルから目隠しを読み込む。replace: 今の目隠しと置き換える(False なら、今の目隠しに追加する)
        """
        core = self.core
        name = check_file_name(name)
        path = os.path.join(MASK_DIR, name + MASK_EXTENSION)
        try:
            masks = load_masks(path)
        except (OSError, ValueError) as e:
            _logger.error(f"Failed to load masks: {e}")
            raise EditError(f"読み込めませんでした。({e})")
        if replace:
            core.masks.clear()
        core.masks.extend(masks)
        print(f"Mask: {len(masks)}個の目隠しを読み込みました。({path})")
        self._masks_changed()

    # ================================================================ タッチスクリーンの範囲

    def touchscreen_area(self) -> list | None:
        """
        タッチスクリーンの範囲(カメラ画像の上の座標 [start_x, start_y, end_x, end_y]。決まっていない場合は None)
        """
        ratio = self.core.touchscreen_ratio()
        if ratio is None:
            return None
        return list(geometry.ratio_to_area(ratio, *self.core.camera.capture_size))

    def set_touchscreen_area(self, start_x: Any, start_y: Any, end_x: Any, end_y: Any) -> None:
        """
        タッチスクリーンの範囲を、カメラ画像の上の座標で決めて保存する(プレビュー上の座標の設定も合わせる)。
        数値として読めない場合と、範囲が空になる場合は EditError
        """
        core = self.core
        settings = core.settings
        try:
            values = [int(round(float(v))) for v in (start_x, start_y, end_x, end_y)]
        except (TypeError, ValueError):
            raise EditError("Touch Screen: 座標は数値で指定してください。")
        capture_width, capture_height = core.camera.capture_size
        area = geometry.clamp_area(*values, capture_width, capture_height)
        if area is None:
            raise EditError("Touch Screen: End は Start より大きい値にしてください。")
        ratio = geometry.area_to_ratio(area, capture_width, capture_height)
        settings.touchscreen_ratio = geometry.ratio_to_text(ratio)
        # これまでのウィンドウの画面は、プレビュー上の座標でも範囲を持っているので、同じ範囲になるよう合わせる
        try:
            show_width, show_height = map(int, settings.show_size.lower().split("x"))
        except ValueError:
            show_width = show_height = 0
        if show_width > 0 and show_height > 0:
            (
                settings.touchscreen_start_x,
                settings.touchscreen_start_y,
                settings.touchscreen_end_x,
                settings.touchscreen_end_y,
            ) = geometry.ratio_to_area(ratio, show_width, show_height)
        print(f"Touchscreen Area (Capture Size): ({area[0]}, {area[1]}), ({area[2]}, {area[3]})")
        self._done()

    # ================================================================ キーコンフィグ

    def _read_setting_file(self) -> configparser.ConfigParser:
        """設定ファイルを、今の内容で読み直して返す(ファイルが無ければ空)"""
        setting = configparser.ConfigParser()
        setting.optionxform = str
        if os.path.isfile(AppSettings.SETTING_PATH):
            setting.read(AppSettings.SETTING_PATH, encoding="utf-8")
        return setting

    def keymaps(self) -> dict:
        """
        ゲーム機ごとのキーの対応と、画面に並べるボタン
        """
        setting = self._read_setting_file()
        return {
            "consoles": list(KeyMap.CONSOLES),
            "current": self.core.keyboard_console(),
            "buttons": {console: [list(map(list, column)) for column in KeyMap.BUTTONS[console]] for console in KeyMap.CONSOLES},
            "keymaps": {console: KeyMap.load_keymap(setting, console) for console in KeyMap.CONSOLES},
        }

    def save_keymaps(self, keymaps: dict) -> None:
        """
        キーの対応を保存し、キーボード操作中なら読み直す。
        keymaps: ゲーム機の名前 -> {ボタンの名前: キー}(変えるものだけでよい)
        使えないキーがある場合や、同じキーを複数のボタンに割り当てている場合は EditError
        """
        if not isinstance(keymaps, dict):
            raise EditError("キーコンフィグの内容が正しくありません。")
        setting = self._read_setting_file()
        complete = {}
        messages = []
        for console in KeyMap.CONSOLES:
            keymap = KeyMap.load_keymap(setting, console)
            given = keymaps.get(console, {})
            left, right = KeyMap.BUTTONS[console]
            used = {}
            for text, name in (*left, *right):
                if isinstance(given, dict) and name in given:
                    if not is_valid_key(given[name]):
                        raise EditError(f"{console}: {text} に使えないキーです: {given[name]}")
                    keymap[name] = given[name]
                used.setdefault(keymap[name], []).append(text)
            messages += [f"{console}: キー「{value}」 → {' / '.join(texts)}" for value, texts in used.items() if len(texts) > 1]
            complete[console] = keymap
        if messages:
            raise EditError("同じキーが複数のボタンに割り当てられています。設定は適用されません。\n" + "\n".join(messages))
        if Profile.is_read_only():
            # 同じプロファイルで2つ目以降に起動した場合は、ファイルには保存せず、起動している間だけ使う
            for console, keymap in complete.items():
                KeyMap.set_session_keymap(console, keymap)
        else:
            # 他の設定を古い内容で上書きしないよう、読み直したファイルの、キーの対応だけを書き換える
            for console, keymap in complete.items():
                KeyMap.store_keymap(setting, console, keymap)
            with open(AppSettings.SETTING_PATH, "w", encoding="utf-8") as file:
                setting.write(file)
            # 設定を保存するときに、キーの対応を古い内容で上書きしないよう、読み込み済みの内容も合わせる
            for console, keymap in complete.items():
                KeyMap.store_keymap(self.core.settings.setting, console, keymap)
        if self.core.keyboard is not None:
            self.core.keyboard.reloadKeyMap(self.core.keyboard_console())
        print("キーコンフィグを保存しました。")

    def start_key_capture(self, on_key: Callable[[str], None]) -> None:
        """
        次に押されたキーを1つ読み取り、on_key(キーの名前) を呼ぶ(PC のキー入力を読む)
        on_key は、キー入力を読むスレッドから呼ばれる
        """
        from pynput.keyboard import Listener

        self.stop_key_capture()

        def on_press(key: Key | KeyCode | None) -> bool | None:
            """キーが押されたときに呼ばれる。False を返すと、読み取りが終わる(名前の無いキーは、読み飛ばして続ける)"""
            char = getattr(key, "char", None)
            text = char if char else str(key)
            if text.startswith("<"):
                # 名前の付いていないキー(保存しても読み込めない)は使わない
                return None
            self._key_listener = None
            on_key(text)
            return False

        self._key_listener = Listener(on_press=on_press)
        self._key_listener.start()

    def stop_key_capture(self) -> None:
        """キーの読み取りをやめる(読み取っていなければ何もしない)"""
        listener, self._key_listener = self._key_listener, None
        if listener is not None:
            listener.stop()

    # ================================================================ コントローラーの本体の色

    def colors_state(self) -> dict:
        """コントローラーの種類ごとの、色の項目・今の色・プリセット(JSON にできる値だけ)"""
        types = []
        for controller_type, info in ControllerColors.CONTROLLER_TYPES.items():
            presets = [{"name": name, "colors": dict(colors)} for name, colors in info["presets"]]
            presets += [{"name": name, "colors": dict(colors)} for name, colors in ControllerColors.list_user_presets(controller_type)]
            types.append(
                {
                    "name": controller_type,
                    "keys": [list(key) for key in info["keys"]],
                    "colors": ControllerColors.get_colors(controller_type),
                    "presets": presets,
                }
            )
        return {"types": types}

    def set_controller_colors(self, controller_type: str, colors: dict) -> None:
        """
        コントローラーの本体の色を変えて保存する。colors: 項目のキー -> 色(その種類に無いキーは無視する)。
        種類が違う場合と、色として読めない値がある場合は EditError
        """
        if controller_type not in ControllerColors.CONTROLLER_TYPES:
            raise EditError(f"コントローラーの種類に指定できない値です: {controller_type}")
        if not isinstance(colors, dict):
            raise EditError("色の指定が正しくありません。")
        current = ControllerColors.get_colors(controller_type)
        for key, value in colors.items():
            if key not in current:
                continue
            color = ControllerColors.normalize_color(value)
            if color is None:
                raise EditError(f"色として読めません: {value}")
            current[key] = color
        ControllerColors.set_colors(controller_type, current)
        core = self.core
        core.settings.controller_colors = ControllerColors.settings_texts()
        # 表示中の Software-Controller を、新しい色で作り直す
        core.set_softcon_layout(core.settings.software_controller_layout)
        core.set_simulator_layout(core.settings.controller_layout)
        self._done()

    # ================================================================ 通知先(Discord / LINE)

    def discord_state(self, selected: str | None = None) -> dict:
        """
        Discord の通知先の一覧と、選んだ通知先の内容(Webhook URL を含むので、操作している画面にだけ渡すこと)
        selected: 内容を返す通知先の名前(None や、登録されていない名前のときは、新しく作る通知先の名前にする)
        """
        setting = load_setting(Discord_Notify.DISCORD_SETTING_PATH)
        names = webhook_names(setting)
        default_set = is_default_webhook_set(setting)
        if selected is None or selected not in names:
            # 既定の通知先が未設定の間は、既定の通知先を設定する
            selected = next_webhook_name(names) if default_set else DEFAULT_WEBHOOK
        values = {key: setting.get(selected, key, fallback="") if setting.has_section(selected) else "" for key in DISCORD_FIELDS}
        return {"names": names, "selected": selected, "values": values, "default_set": default_set, "default_name": DEFAULT_WEBHOOK}

    def save_discord(self, name: str, values: dict) -> dict:
        """
        Discord の通知先を保存して、保存した後の状態(discord_state)を返す。
        values: DISCORD_FIELDS の項目。名前が使えない場合と、Webhook URL が空の場合は EditError
        """
        name = str(name).strip()
        setting = load_setting(Discord_Notify.DISCORD_SETTING_PATH)
        if not is_default_webhook_set(setting):
            # 既定の通知先は必ず作る(未設定の間は、名前を変えられない)
            name = DEFAULT_WEBHOOK
        error = check_webhook_name(name)
        webhook_url = str(values.get("webhook_url", "")).strip() if isinstance(values, dict) else ""
        if error is None and webhook_url == "":
            error = "Webhook URL を入力してください。"
        if error is not None:
            raise EditError(error)
        if not setting.has_section(RECEIVE_SECTION):
            # 新しく作るファイルは、起動時に作られるものと同じ構成にする
            setting[RECEIVE_SECTION] = {"channel_id": "", "token": ""}
        setting[name] = {key: str(values.get(key, "")).strip().replace("\n", "").replace("\r", "") for key in DISCORD_FIELDS}
        save_setting(Discord_Notify.DISCORD_SETTING_PATH, setting)
        _logger.debug(f"Assign Discord Webhook Setting: {name}")
        print(f"Discordの通知先 [{name}] を保存しました。")
        return self.discord_state(name)

    def delete_discord(self, name: str) -> dict:
        """Discord の通知先を消して、消した後の状態を返す(既定の通知先と、登録されていない名前は EditError)"""
        name = str(name).strip()
        if name == DEFAULT_WEBHOOK:
            raise EditError(f"{DEFAULT_WEBHOOK} は削除できません。")
        setting = load_setting(Discord_Notify.DISCORD_SETTING_PATH)
        if name not in webhook_names(setting):
            raise EditError(f"通知先「{name}」は登録されていません。")
        setting.remove_section(name)
        save_setting(Discord_Notify.DISCORD_SETTING_PATH, setting)
        _logger.debug(f"Delete Discord Webhook Setting: {name}")
        print(f"Discordの通知先 [{name}] を削除しました。")
        return self.discord_state()

    def line_token_is_set(self) -> bool:
        """LINE のトークンが保存されているか(値そのものは返さない)"""
        path = Line_Notify.LINE_TOKEN_PATH
        if not os.path.isfile(path):
            return False
        setting = load_setting(path)
        return setting.get("LINE", "token", fallback="") not in ("", "paste_your_token_here")

    def save_line_token(self, token: str) -> None:
        """LINE のトークンを、プロファイルのファイルに保存する(空や、改行を含む場合は EditError)"""
        token = str(token).strip()
        if token == "" or any(character in token for character in "\r\n"):
            raise EditError("LINE のトークンを入力してください。")
        path = Line_Notify.LINE_TOKEN_PATH
        token_file = configparser.ConfigParser(comment_prefixes="#", allow_no_value=True)
        token_file["LINE"] = {"token": token}
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as file:
            token_file.write(file)
        os.chmod(path=path, mode=0o777)
        print("LINE のトークンを保存しました。")
