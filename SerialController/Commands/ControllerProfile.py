#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PCに接続したコントローラーの入力を、Switchのボタン・Hat・スティックに変換するための設定(プロファイル)

プロファイルは ControllerProfiles フォルダにJSONファイルとして置く(書式は ControllerProfiles/README.md を参照)。
Switch Proコントローラー用のプロファイルは組み込みで持っており、同じ名前のJSONファイルがあればそちらを優先する。

ボタン番号の確認:
    python -m Commands.ControllerProfile --probe
"""
from __future__ import annotations

import json
import os
import re
import sys
import threading
from dataclasses import dataclass, field
from logging import getLogger, DEBUG, NullHandler
from typing import TYPE_CHECKING

from Commands.Keys import Button, Hat

if TYPE_CHECKING:
    import pygame

_logger = getLogger(__name__)
_logger.addHandler(NullHandler())
_logger.setLevel(DEBUG)
_logger.propagate = True

# プロファイルを置くフォルダ
CONTROLLER_PROFILE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ControllerProfiles")
# プロファイルに一致する最初のコントローラーを使う
AUTO_DEVICE = "Auto"
# スティックの中心付近を無視する範囲の初期値(-1.0～1.0の軸の値に対する半径)
DEFAULT_DEADZONE = 0.35
# 軸をボタンとして扱う場合の、押したとみなすしきい値の初期値
DEFAULT_AXIS_THRESHOLD = 0.5
# pygame(SDL)のjoystickを使う処理を同時に1つだけにするためのロック
# (コントローラー一覧の取得とProControllerのスレッドが、互いの初期化・解放を壊さないようにする)
JOYSTICK_LOCK = threading.Lock()

# 組み込みのSwitch Proコントローラー用プロファイル(従来の固定の割り当て)
SWITCH_PRO_PROFILE = {
    "name": "Switch Pro Controller",
    "match": ["Pro Controller"],
    "buttons": {
        "A": 0,
        "B": 1,
        "X": 2,
        "Y": 3,
        "MINUS": 4,
        "HOME": 5,
        "PLUS": 6,
        "LCLICK": 7,
        "RCLICK": 8,
        "L": 9,
        "R": 10,
        "CAPTURE": 15,
        "ZL": {"axis": 4, "threshold": 0.0},
        "ZR": {"axis": 5, "threshold": 0.0},
    },
    "hat": {"type": "buttons", "up": 11, "down": 12, "left": 13, "right": 14},
    "sticks": {"lx": 0, "ly": 1, "rx": 2, "ry": 3},
    "deadzone": DEFAULT_DEADZONE,
}

# プロファイルに書けるSwitchのボタン名(3DS用の別名は除く)
BUTTON_NAMES = ("Y", "B", "A", "X", "L", "R", "ZL", "ZR", "MINUS", "PLUS", "LCLICK", "RCLICK", "HOME", "CAPTURE")
HAT_DIRECTIONS = ("up", "right", "down", "left")
STICK_AXES = ("lx", "ly", "rx", "ry")

# 上下左右の組み合わせ(上=1, 右=2, 下=4, 左=8)からHatの値への変換(ありえない組み合わせは中央)
_HAT_FROM_BITS = {
    0: Hat.CENTER,
    1: Hat.TOP,
    2: Hat.RIGHT,
    3: Hat.TOP_RIGHT,
    4: Hat.BTM,
    6: Hat.BTM_RIGHT,
    8: Hat.LEFT,
    9: Hat.TOP_LEFT,
    12: Hat.BTM_LEFT,
}


class ControllerProfileError(ValueError):
    """プロファイルの書式の誤りや、コントローラーが見つからない場合の例外(文は、利用者に見せる日本語)"""

    pass


@dataclass(frozen=True)
class InputRef:
    """
    コントローラーの物理的な入力1つ(ボタン、または軸の片側)
    """

    kind: str  # "button" | "axis"
    index: int
    threshold: float = DEFAULT_AXIS_THRESHOLD  # 軸のみ
    direction: int = 1  # 軸のみ。-1なら軸を負の方向に倒したときに押したとみなす

    def pressed(self, joystick: pygame.joystick.JoystickType) -> bool:
        """今、押されているか(コントローラーにない番号は、押されていない扱い)"""
        if self.kind == "button":
            return self.index < joystick.get_numbuttons() and bool(joystick.get_button(self.index))
        if self.index >= joystick.get_numaxes():
            return False
        return joystick.get_axis(self.index) * self.direction > self.threshold

    def describe(self) -> str:
        """警告文に使う表し方("button 3" / "axis 4")"""
        if self.kind == "button":
            return f"button {self.index}"
        return f"axis {self.index}"


@dataclass(frozen=True)
class StickAxis:
    """スティックの 1 つの軸(index: コントローラーの軸の番号。invert: 向きを逆にするか)"""

    index: int
    invert: bool = False


@dataclass
class ControllerProfile:
    """
    コントローラー 1 種類の割り当て(Switch のボタン・十字キー・スティックが、コントローラーのどの入力か)

    name: プロファイルの名前
    match: コントローラーの名前に含まれる文字列(どれかが含まれれば、このプロファイルを使う)
    buttons: Button -> 入力
    sticks: "lx" / "ly" / "rx" / "ry" -> 軸
    deadzone: スティックの中心付近を無視する範囲(0 以上 1 未満)
    """

    name: str
    match: list[str]
    buttons: dict[Button, InputRef]
    # hat_type が "hat" の場合は hat_index を、"buttons" の場合は hat_inputs を使う
    hat_type: str
    hat_index: int = 0
    hat_inputs: dict[str, InputRef] = field(default_factory=dict)
    sticks: dict[str, StickAxis] = field(default_factory=dict)
    deadzone: float = DEFAULT_DEADZONE
    path: str | None = None  # 組み込みの場合はNone

    def matches(self, joystick_name: str) -> bool:
        """コントローラーの名前が、このプロファイルの対象か(match のどれかを含むか。大文字と小文字は区別しない)"""
        name = joystick_name.lower()
        return any(m.lower() in name for m in self.match)

    def check(self, joystick: pygame.joystick.JoystickType) -> list[str]:
        """
        接続中のコントローラーに存在しない番号を指定していないか確認する(警告文のリストを返す)
        """
        warnings = []
        num_buttons, num_axes, num_hats = joystick.get_numbuttons(), joystick.get_numaxes(), joystick.get_numhats()
        refs = [(f"buttons.{b.name}", r) for b, r in self.buttons.items()]
        refs += [(f"hat.{d}", r) for d, r in self.hat_inputs.items()]
        for where, ref in refs:
            limit = num_buttons if ref.kind == "button" else num_axes
            if ref.index >= limit:
                warnings.append(f"{where}: {ref.describe()} はありません")
        for where, stick in self.sticks.items():
            if stick.index >= num_axes:
                warnings.append(f"sticks.{where}: axis {stick.index} はありません")
        if self.hat_type == "hat" and self.hat_index >= num_hats:
            warnings.append(f"hat: hat {self.hat_index} はありません")
        return warnings

    def read(self, joystick: pygame.joystick.JoystickType) -> tuple[int, int, list[int]]:
        """
        コントローラーの現在の入力を読み取り、(Defaultのボタンビット, Hatの値, [lx, ly, rx, ry]) を返す
        スティックは0～255(中心128)、yは下が大きい
        """
        buttons = 0
        for button, ref in self.buttons.items():
            if ref.pressed(joystick):
                buttons |= int(button)
        return buttons, int(self._read_hat(joystick)), self._read_sticks(joystick)

    def _read_hat(self, joystick: pygame.joystick.JoystickType) -> Hat:
        """十字キーの今の向きを読み取る(ありえない組み合わせ(上と下など)は、中央)"""
        if self.hat_type == "hat":
            if self.hat_index >= joystick.get_numhats():
                return Hat.CENTER
            x, y = joystick.get_hat(self.hat_index)  # yは上が正
            up, right, down, left = y > 0, x > 0, y < 0, x < 0
        else:
            up, right, down, left = (
                d in self.hat_inputs and self.hat_inputs[d].pressed(joystick) for d in HAT_DIRECTIONS
            )
        bits = (1 if up else 0) | (2 if right else 0) | (4 if down else 0) | (8 if left else 0)
        return _HAT_FROM_BITS.get(bits, Hat.CENTER)

    def _axis(self, joystick: pygame.joystick.JoystickType, key: str) -> float:
        """スティックの軸(key: "lx" など)の今の値(-1.0～1.0。反転の指定を反映する。割り当てがなければ 0.0)"""
        stick = self.sticks.get(key)
        if stick is None or stick.index >= joystick.get_numaxes():
            return 0.0
        value = joystick.get_axis(stick.index)
        return -value if stick.invert else value

    def _read_sticks(self, joystick: pygame.joystick.JoystickType) -> list[int]:
        """左右のスティックを読み取り、[lx, ly, rx, ry](0～255)で返す(deadzone の内側は、中央の 128)"""
        values = []
        for kx, ky in (("lx", "ly"), ("rx", "ry")):
            x, y = self._axis(joystick, kx), self._axis(joystick, ky)
            if (x**2 + y**2) ** 0.5 < self.deadzone:
                values += [128, 128]
            else:
                values += [map_axis(x), map_axis(y)]
        return values


def map_axis(val: float) -> int:
    """
    軸の値(-1.0～1.0)を0～255に変換する
    """
    val = min(max(round(val, 3), -1.0), 1.0)
    return int((val + 1) * 255 / 2)


def _parse_int(value: object, where: str) -> int:
    """
    value が 0 以上の整数なら、そのまま返す。違えば ControllerProfileError
    value: JSON から読んだ値(型を、ここで確かめる)。where: エラーの文に入れる、項目の場所
    """
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ControllerProfileError(f"{where}: 0以上の整数を指定してください ({value!r})")
    return value


def _parse_ref(value: object, where: str) -> InputRef:
    """
    整数ならボタン番号、{"axis": n, "threshold": t, "direction": ±1} なら軸、{"button": n} ならボタン
    (value は JSON から読んだ値。書式が違えば ControllerProfileError)
    """
    if isinstance(value, dict):
        if "axis" in value:
            direction = value.get("direction", 1)
            if direction not in (1, -1):
                raise ControllerProfileError(f"{where}.direction: 1 か -1 を指定してください ({direction!r})")
            threshold = value.get("threshold", DEFAULT_AXIS_THRESHOLD)
            if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
                raise ControllerProfileError(f"{where}.threshold: 数値を指定してください ({threshold!r})")
            return InputRef("axis", _parse_int(value["axis"], f"{where}.axis"), float(threshold), direction)
        if "button" in value:
            return InputRef("button", _parse_int(value["button"], f"{where}.button"))
        raise ControllerProfileError(f"{where}: button または axis を指定してください")
    return InputRef("button", _parse_int(value, where))


def _parse_stick(value: object, where: str) -> StickAxis:
    """
    整数なら軸番号、{"axis": n, "invert": bool} なら向きの反転も指定する
    (value は JSON から読んだ値。書式が違えば ControllerProfileError)
    """
    if isinstance(value, dict):
        invert = value.get("invert", False)
        if not isinstance(invert, bool):
            raise ControllerProfileError(f"{where}.invert: true か false を指定してください ({invert!r})")
        return StickAxis(_parse_int(value.get("axis"), f"{where}.axis"), invert)
    return StickAxis(_parse_int(value, where))


def parse_profile(data: dict, path: str | None = None) -> ControllerProfile:
    """
    JSON から読んだ内容(data)を、プロファイルにする。書式が違えば ControllerProfileError
    path: 読んだファイルのパス(プロファイルに覚えさせる。組み込みの場合は None)
    """
    if not isinstance(data, dict):
        raise ControllerProfileError("プロファイルはJSONのオブジェクトで書いてください")
    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ControllerProfileError(f"name: 名前を指定してください ({name!r})")
    match = data.get("match", [])
    if isinstance(match, str):
        match = [match]
    if not isinstance(match, list) or not all(isinstance(m, str) and m for m in match):
        raise ControllerProfileError("match: コントローラー名に含まれる文字列のリストを指定してください")

    buttons = {}
    for key, value in (data.get("buttons") or {}).items():
        if key not in BUTTON_NAMES:
            raise ControllerProfileError(f"buttons: 不明なボタン名です ({key}). 使える名前: {', '.join(BUTTON_NAMES)}")
        buttons[Button[key]] = _parse_ref(value, f"buttons.{key}")

    hat = data.get("hat") or {"type": "hat", "index": 0}
    hat_type = hat.get("type")
    hat_index = 0
    hat_inputs = {}
    if hat_type == "hat":
        hat_index = _parse_int(hat.get("index", 0), "hat.index")
    elif hat_type == "buttons":
        for d in HAT_DIRECTIONS:
            if d in hat:
                hat_inputs[d] = _parse_ref(hat[d], f"hat.{d}")
    else:
        raise ControllerProfileError(f"hat.type: 'hat' か 'buttons' を指定してください ({hat_type!r})")

    sticks = {}
    for key, value in (data.get("sticks") or {}).items():
        if key not in STICK_AXES:
            raise ControllerProfileError(f"sticks: 不明な軸名です ({key}). 使える名前: {', '.join(STICK_AXES)}")
        sticks[key] = _parse_stick(value, f"sticks.{key}")

    deadzone = data.get("deadzone", DEFAULT_DEADZONE)
    if isinstance(deadzone, bool) or not isinstance(deadzone, (int, float)) or not 0 <= deadzone < 1:
        raise ControllerProfileError(f"deadzone: 0以上1未満の数値を指定してください ({deadzone!r})")

    return ControllerProfile(
        name=name.strip(),
        match=match,
        buttons=buttons,
        hat_type=hat_type,
        hat_index=hat_index,
        hat_inputs=hat_inputs,
        sticks=sticks,
        deadzone=float(deadzone),
        path=path,
    )


def load_profile_file(path: str) -> ControllerProfile:
    """
    JSON ファイルからプロファイルを読み込む。
    JSON や、プロファイルの書式が違えば ControllerProfileError。ファイルを開けなければ OSError
    """
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ControllerProfileError(f"JSONの書式が正しくありません (line {e.lineno}): {e.msg}") from e
    return parse_profile(data, path)


def load_profiles(profile_dir: str = CONTROLLER_PROFILE_DIR) -> tuple[list[ControllerProfile], list[str]]:
    """
    プロファイルを読み込み、(プロファイルのリスト, エラーメッセージのリスト) を返す
    - JSONファイルのプロファイルを名前順に並べ、最後に組み込みのプロファイルを置く(自動選択はこの順に照合する)
    - 組み込みと同じ名前のJSONファイルがあれば、JSONファイルを優先する
    """
    profiles: dict[str, ControllerProfile] = {}
    errors = []
    if os.path.isdir(profile_dir):
        for filename in sorted(os.listdir(profile_dir)):
            if not filename.lower().endswith(".json"):
                continue
            path = os.path.join(profile_dir, filename)
            try:
                profile = load_profile_file(path)
            except (OSError, ControllerProfileError) as e:
                errors.append(f"{filename}: {e}")
                continue
            if profile.name in profiles:
                errors.append(f"{filename}: '{profile.name}' は {os.path.basename(profiles[profile.name].path)} と同じ名前のため無視します")
                continue
            profiles[profile.name] = profile
    result = sorted(profiles.values(), key=lambda p: p.name.lower())
    builtin = parse_profile(SWITCH_PRO_PROFILE)
    if builtin.name not in profiles:
        result.append(builtin)
    for e in errors:
        _logger.warning(f"Controller profile error: {e}")
    return result, errors


def ref_to_json(ref: InputRef) -> int | dict:
    """入力を、JSON に書く形にする(ボタンは番号、軸は {"axis": ..., "threshold": ...} の dict)。_parse_ref の逆"""
    if ref.kind == "button":
        return ref.index
    data = {"axis": ref.index, "threshold": round(ref.threshold, 3)}
    if ref.direction != 1:
        data["direction"] = ref.direction
    return data


def profile_to_dict(profile: ControllerProfile) -> dict:
    """
    プロファイルをJSONに書き出せる形にする(parse_profileの逆)
    """
    buttons = {}
    for name in BUTTON_NAMES:
        ref = profile.buttons.get(Button[name])
        if ref is not None:
            buttons[name] = ref_to_json(ref)
    if profile.hat_type == "hat":
        hat = {"type": "hat", "index": profile.hat_index}
    else:
        hat = {"type": "buttons"}
        for d in HAT_DIRECTIONS:
            if d in profile.hat_inputs:
                hat[d] = ref_to_json(profile.hat_inputs[d])
    sticks = {}
    for key in STICK_AXES:
        stick = profile.sticks.get(key)
        if stick is not None:
            sticks[key] = {"axis": stick.index, "invert": True} if stick.invert else stick.index
    return {
        "name": profile.name,
        "match": list(profile.match),
        "buttons": buttons,
        "hat": hat,
        "sticks": sticks,
        "deadzone": profile.deadzone,
    }


def save_profile(profile: ControllerProfile, path: str) -> None:
    """
    プロファイルをJSONファイルに保存する(書き込みに失敗しても元のファイルを壊さないよう、一時ファイルから置き換える)
    """
    data = profile_to_dict(profile)
    # 保存する内容が読み込めることを確認する
    parse_profile(data, path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp_path, path)


def profile_filename(joystick_name: str) -> str:
    """
    コントローラーの名前から、新しく作るプロファイルのファイル名を作る
    """
    safe = re.sub(r"[^0-9A-Za-z_-]+", "_", joystick_name).strip("_")
    return (safe or "Controller") + ".json"


def profile_file_for(
    joystick_name: str, profiles: list[ControllerProfile], profile_dir: str = CONTROLLER_PROFILE_DIR
) -> tuple[str, ControllerProfile | None, bool]:
    """
    コントローラーの設定を保存するファイルを決め、(パス, 元にするプロファイル, ファイルが既にあるか) を返す
    - 名前が一致するJSONファイルのプロファイルがあれば、そのファイルを更新する
    - なければ名前から新しいファイルを作る(組み込みのプロファイルに一致すれば、その割り当てを元にする)
    """
    for profile in profiles:
        if profile.path is not None and profile.matches(joystick_name):
            return profile.path, profile, True
    base = next((p for p in profiles if p.matches(joystick_name)), None)
    path = os.path.join(profile_dir, profile_filename(joystick_name))
    return path, base, os.path.exists(path)


def find_profile(profiles: list[ControllerProfile], name: str) -> ControllerProfile | None:
    """名前が name のプロファイルを返す(なければ None)"""
    for profile in profiles:
        if profile.name == name:
            return profile
    return None


def default_profile(profiles: list[ControllerProfile]) -> ControllerProfile:
    """
    名前が一致するプロファイルがない場合に使うプロファイル(Switch Proコントローラー用)
    """
    return find_profile(profiles, SWITCH_PRO_PROFILE["name"]) or profiles[-1]


def select_profile(joystick_name: str, profiles: list[ControllerProfile]) -> tuple[ControllerProfile, str | None]:
    """
    コントローラーの名前に一致するプロファイルを選び、(プロファイル, 注意メッセージ) を返す
    """
    for profile in profiles:
        if profile.matches(joystick_name):
            return profile, None
    fallback = default_profile(profiles)
    return fallback, f"'{joystick_name}' に一致するプロファイルがないため '{fallback.name}' を使います"


def device_label(index: int, name: str) -> str:
    """
    コンボボックスに表示するコントローラーの名前(同じ種類のコントローラーは番号で区別する)
    """
    return f"{index}: {name}"


def parse_device_label(label: str) -> tuple[int, str] | None:
    """
    device_labelで作った文字列を (番号, 名前) に戻す(Autoや書式が違う場合はNone)
    """
    index, sep, name = label.partition(": ")
    if not sep or not index.isdigit() or not name:
        return None
    return int(index), name


def list_joystick_names() -> list[str]:
    """
    接続中のコントローラーの名前を番号順に返す
    (呼ぶたびにjoystickモジュールを初期化し直して最新の接続状態を読み、終わったら解放する)
    初期化に1秒ほどかかるので、GUIのスレッドからは呼ばないこと
    """
    import pygame

    with JOYSTICK_LOCK:
        pygame.joystick.quit()
        pygame.joystick.init()
        try:
            return [pygame.joystick.Joystick(i).get_name() for i in range(pygame.joystick.get_count())]
        finally:
            pygame.joystick.quit()


def select_device(
    joystick_names: list[str], profiles: list[ControllerProfile], device: str = AUTO_DEVICE
) -> tuple[int, ControllerProfile, list[str]]:
    """
    使うコントローラーの番号とプロファイルを決め、(番号, プロファイル, 注意メッセージのリスト) を返す
    - Auto: いずれかのプロファイルに名前が一致する、番号が最も小さいコントローラーを使う(なければ0番)
    - コントローラー指定(device_labelの文字列): 番号と名前が一致するコントローラーを使う。
      番号が変わっていれば、同じ名前のコントローラーのうち最初のものを使う
    プロファイルはコントローラーの名前から自動で選ぶ
    コントローラーが 1 つもない、指定の書式が違う、指定のものが接続されていない場合は ControllerProfileError
    """
    if not joystick_names:
        raise ControllerProfileError("コントローラーが接続されていません")
    notes = []
    if device == AUTO_DEVICE:
        matched = [i for i, name in enumerate(joystick_names) if any(p.matches(name) for p in profiles)]
        index = matched[0] if matched else 0
    else:
        parsed = parse_device_label(device)
        if parsed is None:
            raise ControllerProfileError(f"コントローラーの指定が正しくありません ({device})")
        index, name = parsed
        if index >= len(joystick_names) or joystick_names[index] != name:
            if name not in joystick_names:
                raise ControllerProfileError(f"'{device}' が接続されていません")
            index = joystick_names.index(name)
            notes.append(f"'{device}' の番号が変わったため、{device_label(index, name)} を使います")
    profile, note = select_profile(joystick_names[index], profiles)
    if note is not None:
        notes.append(note)
    return index, profile, notes


def probe() -> None:
    """
    接続中のコントローラーの入力の変化を表示する(プロファイルを書くときのボタン番号の確認用)
    """
    import time

    import pygame

    pygame.init()
    count = pygame.joystick.get_count()
    if count == 0:
        print("コントローラーが接続されていません")
        return
    joysticks = [pygame.joystick.Joystick(i) for i in range(count)]
    for i, js in enumerate(joysticks):
        js.init()
        print(
            f"[{i}] {js.get_name()}  buttons={js.get_numbuttons()} axes={js.get_numaxes()} hats={js.get_numhats()}"
        )
    print("入力の変化を表示します (Ctrl+Cで終了)")
    last = {}
    try:
        while True:
            pygame.event.pump()
            for i, js in enumerate(joysticks):
                state = {}
                for b in range(js.get_numbuttons()):
                    state[f"button {b}"] = js.get_button(b)
                for a in range(js.get_numaxes()):
                    state[f"axis {a}"] = round(js.get_axis(a), 1)
                for h in range(js.get_numhats()):
                    state[f"hat {h}"] = js.get_hat(h)
                for key, value in state.items():
                    if last.get((i, key)) != value:
                        if (i, key) in last:
                            print(f"[{i}] {key}: {value}")
                        last[(i, key)] = value
            time.sleep(0.01)
    except KeyboardInterrupt:
        pass
    finally:
        pygame.quit()


if __name__ == "__main__":
    if "--probe" in sys.argv[1:]:
        probe()
    else:
        profiles, errors = load_profiles()
        for p in profiles:
            print(f"{p.name}  match={p.match}  ({p.path or '組み込み'})")
        for e in errors:
            print(f"エラー: {e}")
