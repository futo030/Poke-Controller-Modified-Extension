#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
コントローラーのプロファイル(ボタンの割り当て)を作る手順

Switchのボタン・十字キー・スティックを1つずつ示し、対応するコントローラーの入力を押してもらって割り当てる
- JoystickMonitor: 別スレッドでコントローラーの状態を読み続ける(pygameの初期化に1秒ほどかかるため)
- SetupSession: 入力の検出と割り当ての管理

画面(tkinter)には触れない。画面は ControllerSetup.py(tkinter 版)と、Web ブラウザ版の画面が持つ
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from logging import getLogger, DEBUG, NullHandler

from Commands.ControllerProfile import (
    BUTTON_NAMES,
    DEFAULT_DEADZONE,
    HAT_DIRECTIONS,
    JOYSTICK_LOCK,
    STICK_AXES,
    ControllerProfile,
    ControllerProfileError,
    InputRef,
    StickAxis,
    select_device,
)
from Commands.Keys import Button

_logger = getLogger(__name__)
_logger.addHandler(NullHandler())
_logger.setLevel(DEBUG)
_logger.propagate = True

# コントローラーの状態を読む間隔(秒)
MONITOR_INTERVAL = 0.01
# ウィンドウが状態を確認する間隔(ms)
POLL_INTERVAL_MS = 20
# 軸がこの量以上動いたら入力とみなす
AXIS_DETECT_DELTA = 0.6
# 軸の動きがこの量未満なら離したとみなす
AXIS_RELEASE_DELTA = 0.3
# 軸をボタンとして割り当てる場合の、押したとみなすしきい値(静止時の値からの距離)
AXIS_BUTTON_THRESHOLD = 0.5
# 静止時の状態は、この時間(秒)変化しなかった状態を使う
# (開いた直後は軸が0のまま実際の値が届いていないことがあるため)
BASELINE_STABLE_TIME = 0.5
# 静止時の状態を決めるときに、変化していないとみなす軸の変化量
BASELINE_AXIS_TOLERANCE = 0.05

BUTTON_LABELS = {
    "A": "A",
    "B": "B",
    "X": "X",
    "Y": "Y",
    "L": "L",
    "R": "R",
    "ZL": "ZL",
    "ZR": "ZR",
    "MINUS": "−(マイナス)",
    "PLUS": "+(プラス)",
    "LCLICK": "左スティック押し込み",
    "RCLICK": "右スティック押し込み",
    "HOME": "HOME",
    "CAPTURE": "キャプチャー",
}
# 設定する順番
BUTTON_ORDER = ("A", "B", "X", "Y", "L", "R", "ZL", "ZR", "MINUS", "PLUS", "LCLICK", "RCLICK", "HOME", "CAPTURE")
assert sorted(BUTTON_ORDER) == sorted(BUTTON_NAMES)
HAT_LABELS = {"up": "上", "right": "右", "down": "下", "left": "左"}
STICK_INSTRUCTIONS = {
    "lx": ("左スティック 左右", "左スティックを右に倒してください"),
    "ly": ("左スティック 上下", "左スティックを下に倒してください"),
    "rx": ("右スティック 左右", "右スティックを右に倒してください"),
    "ry": ("右スティック 上下", "右スティックを下に倒してください"),
}


@dataclass(frozen=True)
class SetupStep:
    """割り当ての手順 1 つ(label: 画面に出す名前。instruction: 利用者への指示の文)"""

    kind: str  # "button" | "hat" | "stick"
    key: str  # ボタン名 / 十字キーの方向 / スティックの軸名
    label: str
    instruction: str


SETUP_STEPS = (
    [
        SetupStep("button", name, BUTTON_LABELS[name], f"Switchの「{BUTTON_LABELS[name]}」に割り当てる入力を押してください")
        for name in BUTTON_ORDER
    ]
    + [
        SetupStep("hat", d, f"十字キー {HAT_LABELS[d]}", f"十字キーの「{HAT_LABELS[d]}」に割り当てる入力を押してください")
        for d in HAT_DIRECTIONS
    ]
    + [SetupStep("stick", key, *STICK_INSTRUCTIONS[key]) for key in STICK_AXES]
)


@dataclass(frozen=True)
class HatAssign:
    """
    十字キーをコントローラーのHatとして割り当てる
    """

    index: int


@dataclass(frozen=True)
class JoystickSnapshot:
    """ある時点のコントローラーの状態(ボタンは 0 / 1、軸は -1.0～1.0、ハットは (x, y) で、番号の順)"""

    buttons: tuple[int, ...]
    axes: tuple[float, ...]
    hats: tuple[tuple[int, int], ...]


def describe(value: InputRef | StickAxis | HatAssign | None) -> str:
    """割り当てを、画面に出す文字列にする("ボタン 3"、"軸 1 (反転)"、"なし" など)"""
    if value is None:
        return "なし"
    if isinstance(value, HatAssign):
        return f"ハット {value.index}"
    if isinstance(value, StickAxis):
        return f"軸 {value.index}" + (" (反転)" if value.invert else "")
    if value.kind == "button":
        return f"ボタン {value.index}"
    return f"軸 {value.index} ({'+' if value.direction > 0 else '−'}方向)"


class SetupSession:
    """
    割り当ての手順を進める(Tkに依存しないので単体で確認できる)
    - feedに状態を渡すと、現在の手順の入力を検出して割り当て、全部離されるのを待ってから次の手順に進む
    - スキップした手順は元のプロファイルの割り当てを残す
    """

    def __init__(self, name: str, match: list[str], base: ControllerProfile | None = None) -> None:
        """
        name: 作るプロファイルの名前
        match: 作るプロファイルの match(コントローラーの名前に含まれる文字列)
        base: 元にするプロファイル(割り当てを変えなかった手順は、この割り当てを残す。None: 何もない状態から)
        """
        self.name = name
        self.match = match
        self.base = base
        self.steps = SETUP_STEPS
        self.index = 0
        # 手順のキー(kind, key) -> 割り当て(Noneは割り当てなし)。キーがなければ元の割り当てを使う
        self.assignments: dict[tuple[str, str], object] = {}
        self.history: list[int] = []
        self.baseline: JoystickSnapshot | None = None
        # 静止時の状態の候補と、その状態になった時刻
        self._baseline_candidate: JoystickSnapshot | None = None
        self._baseline_since = 0.0
        self.waiting_release = False

    @property
    def done(self) -> bool:
        """すべての手順を終えたか"""
        return self.index >= len(self.steps)

    @property
    def current(self) -> SetupStep | None:
        """今の手順(すべて終えていれば None)"""
        return None if self.done else self.steps[self.index]

    @property
    def changed(self) -> bool:
        """割り当てを 1 つでも変えたか(割り当てなしにしたものも含む)"""
        return bool(self.assignments)

    def base_value(self, step: SetupStep) -> InputRef | StickAxis | HatAssign | None:
        """元のプロファイルでの、その手順の割り当て(なければ None)"""
        base = self.base
        if base is None:
            return None
        if step.kind == "button":
            return base.buttons.get(Button[step.key])
        if step.kind == "hat":
            if base.hat_type == "hat":
                return HatAssign(base.hat_index)
            return base.hat_inputs.get(step.key)
        return base.sticks.get(step.key)

    def value(self, step: SetupStep) -> InputRef | StickAxis | HatAssign | None:
        """その手順の、今の割り当て(変えていなければ、元のプロファイルの割り当て。なければ None)"""
        key = (step.kind, step.key)
        if key in self.assignments:
            return self.assignments[key]
        return self.base_value(step)

    def is_assigned(self, step: SetupStep) -> bool:
        """その手順の割り当てを、この手順の中で変えたか(割り当てなしにしたものも含む)"""
        return (step.kind, step.key) in self.assignments

    # --- 入力の検出
    def is_released(self, s: JoystickSnapshot) -> bool:
        """すべての入力が、静止時の状態に戻っているか(静止時の状態が決まった後で呼ぶ)"""
        b = self.baseline
        return (
            s.buttons == b.buttons
            and s.hats == b.hats
            and all(abs(v - r) < AXIS_RELEASE_DELTA for v, r in zip(s.axes, b.axes))
        )

    def active_inputs(self, s: JoystickSnapshot) -> list[str]:
        """
        静止時から変化している入力の一覧(画面表示用)
        """
        b = self.baseline
        result = [f"ボタン {i}" for i, (v, r) in enumerate(zip(s.buttons, b.buttons)) if v and not r]
        result += [f"軸 {i} ({v:+.2f})" for i, (v, r) in enumerate(zip(s.axes, b.axes)) if abs(v - r) >= AXIS_RELEASE_DELTA]
        result += [f"ハット {i} {v}" for i, (v, r) in enumerate(zip(s.hats, b.hats)) if v != r]
        return result

    def _moved_axis(self, s: JoystickSnapshot) -> tuple[int, float] | None:
        """静止時から最も大きく動いた軸を (軸の番号, 動いた量) で返す(AXIS_DETECT_DELTA 以上のものがなければ None)"""
        b = self.baseline
        moved = [(abs(v - r), i, v - r) for i, (v, r) in enumerate(zip(s.axes, b.axes)) if abs(v - r) >= AXIS_DETECT_DELTA]
        if not moved:
            return None
        _, index, delta = max(moved)
        return index, delta

    def detect(self, s: JoystickSnapshot) -> InputRef | StickAxis | HatAssign | None:
        """
        今の手順に割り当てる入力を、状態から見つける(見つからなければ None)。
        ボタン・十字キーの手順では、ハット(十字キーのみ)、ボタン、軸の順に探す。スティックの手順では、軸だけ
        """
        step = self.current
        b = self.baseline
        if step.kind in ("button", "hat"):
            if step.kind == "hat":
                for i, (v, r) in enumerate(zip(s.hats, b.hats)):
                    if v != r:
                        return HatAssign(i)
            for i, (v, r) in enumerate(zip(s.buttons, b.buttons)):
                if v and not r:
                    return InputRef("button", i)
            moved = self._moved_axis(s)
            if moved is not None:
                index, delta = moved
                direction = 1 if delta > 0 else -1
                threshold = round(b.axes[index] * direction + AXIS_BUTTON_THRESHOLD, 3)
                return InputRef("axis", index, threshold, direction)
            return None
        moved = self._moved_axis(s)
        if moved is None:
            return None
        index, delta = moved
        # 右・下に倒したときに値が増える向きが正
        return StickAxis(index, invert=delta < 0)

    def _update_baseline(self, s: JoystickSnapshot, now: float) -> bool:
        """
        状態がBASELINE_STABLE_TIMEの間変化しなければ、静止時の状態として確定する
        (now: 今の時刻(秒)。確定したら True)
        """
        c = self._baseline_candidate
        stable = (
            c is not None
            and s.buttons == c.buttons
            and s.hats == c.hats
            and len(s.axes) == len(c.axes)
            and all(abs(v - r) < BASELINE_AXIS_TOLERANCE for v, r in zip(s.axes, c.axes))
        )
        if not stable:
            self._baseline_candidate = s
            self._baseline_since = now
            return False
        if now - self._baseline_since >= BASELINE_STABLE_TIME:
            self.baseline = s
            return True
        return False

    def feed(self, s: JoystickSnapshot, now: float | None = None) -> bool:
        """
        コントローラーの状態を渡す。割り当てや手順が変わったらTrueを返す
        (now: 今の時刻(秒)。None なら time.monotonic()。静止時の状態を決めるのに使う)
        """
        if self.baseline is None:
            return self._update_baseline(s, time.monotonic() if now is None else now)
        if self.waiting_release:
            if self.is_released(s):
                self.waiting_release = False
                return True
            return False
        if self.done:
            return False
        value = self.detect(s)
        if value is None:
            return False
        self.assign(value)
        self.waiting_release = True
        return True

    # --- 手順の操作
    def assign(self, value: InputRef | StickAxis | HatAssign | None) -> None:
        """今の手順に value を割り当てて、次の手順へ進む(HatAssign は、十字キーの 4 方向にまとめて割り当てる)"""
        step = self.current
        if isinstance(value, HatAssign):
            # Hatなら4方向まとめて割り当て、十字キーの残りの手順は飛ばす
            for s in self.steps:
                if s.kind == "hat":
                    self.assignments[(s.kind, s.key)] = value
            self.history.append(self.index)
            self.index = next(i for i, s in enumerate(self.steps) if s.kind == "stick")
            return
        if step.kind == "hat":
            # ボタン等で割り当てる場合、以前のHatの割り当ては解除する
            for s in self.steps:
                if s.kind == "hat" and isinstance(self.value(s), HatAssign):
                    self.assignments[(s.kind, s.key)] = None
        self.assignments[(step.kind, step.key)] = value
        self._advance()

    def skip(self) -> None:
        """
        現在の割り当てを変えずに次へ進む
        """
        if not self.done:
            self._advance()

    def clear(self) -> None:
        """
        割り当てなしにして次へ進む
        """
        step = self.current
        if step is None:
            return
        if step.kind == "hat" and isinstance(self.value(step), HatAssign):
            for s in self.steps:
                if s.kind == "hat":
                    self.assignments[(s.kind, s.key)] = None
        self.assignments[(step.kind, step.key)] = None
        self._advance()

    def back(self) -> None:
        """1 つ前の手順に戻る(割り当ては、そのまま。最初の手順では何もしない)"""
        if self.history:
            self.index = self.history.pop()
            self.waiting_release = False

    def _advance(self) -> None:
        """今の手順を履歴に残して、次の手順へ進む"""
        self.history.append(self.index)
        self.index += 1

    # --- 結果
    def build_profile(self, path: str | None = None) -> ControllerProfile:
        """
        今の割り当てから、プロファイルを作る(変えなかった手順は、元のプロファイルの割り当て)
        path: プロファイルに覚えさせる、保存先のパス(保存はしない)
        """
        base = self.base
        buttons = dict(base.buttons) if base else {}
        sticks = dict(base.sticks) if base else {}
        for step in self.steps:
            if not self.is_assigned(step) or step.kind == "hat":
                continue
            value = self.assignments[(step.kind, step.key)]
            target = buttons if step.kind == "button" else sticks
            target_key = Button[step.key] if step.kind == "button" else step.key
            if value is None:
                target.pop(target_key, None)
            else:
                target[target_key] = value

        hat_values = {s.key: self.value(s) for s in self.steps if s.kind == "hat"}
        hats = [v for v in hat_values.values() if isinstance(v, HatAssign)]
        if hats:
            hat_type, hat_index, hat_inputs = "hat", hats[0].index, {}
        else:
            hat_type, hat_index = "buttons", 0
            hat_inputs = {d: v for d, v in hat_values.items() if v is not None}

        return ControllerProfile(
            name=self.name,
            match=list(self.match),
            buttons=buttons,
            hat_type=hat_type,
            hat_index=hat_index,
            hat_inputs=hat_inputs,
            sticks=sticks,
            deadzone=base.deadzone if base else DEFAULT_DEADZONE,
            path=path,
        )

    def duplicates(self) -> list[str]:
        """
        同じ入力が複数に割り当てられている箇所(保存前の確認用)
        """
        used: dict[object, list[str]] = {}
        for step in self.steps:
            value = self.value(step)
            if value is None or isinstance(value, HatAssign):
                continue
            # スティックの軸とボタン扱いの軸は同じ軸番号なら重複とみなす
            key = ("axis", value.index) if isinstance(value, StickAxis) or value.kind == "axis" else ("button", value.index)
            used.setdefault(key, []).append(step.label)
        return [f"{describe_key(k)}: {', '.join(labels)}" for k, labels in used.items() if len(labels) > 1]


def describe_key(key: tuple[str, int]) -> str:
    """("button" または "axis", 番号) を、画面に出す文字列にする"""
    kind, index = key
    return f"ボタン {index}" if kind == "button" else f"軸 {index}"


class JoystickMonitor:
    """
    別スレッドでコントローラーを開き、状態を読み続ける(latestに最新の状態が入る)
    """

    def __init__(self, device: str, expected_name: str) -> None:
        """
        device: 使うコントローラー(AUTO_DEVICE、または "番号: 名前" の文字列)
        expected_name: 開くはずのコントローラーの名前(違うものが開いたら、error に文を入れて止まる)
        """
        self.device = device
        self.expected_name = expected_name
        self.latest: JoystickSnapshot | None = None
        self.error: str | None = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="ControllerSetup", daemon=True)

    def start(self) -> None:
        """読み取りのスレッドを始める(1 回だけ呼べる)"""
        self._thread.start()

    def stop(self) -> None:
        """読み取りを止めるよう頼む(スレッドの終わりは待たない)"""
        self._stop.set()

    def _run(self) -> None:
        """スレッドの中身。コントローラーを開いて、止められるまで状態を latest に入れ続ける(失敗は error に入れる)"""
        import pygame

        try:
            with JOYSTICK_LOCK:
                pygame.init()
                try:
                    names = [pygame.joystick.Joystick(i).get_name() for i in range(pygame.joystick.get_count())]
                    # 名前でのプロファイル選択は不要なので、名前が一致するダミーのプロファイルを渡す
                    dummy = ControllerProfile(self.expected_name, [self.expected_name], {}, "buttons")
                    index, _, _ = select_device(names, [dummy], self.device)
                    if names[index] != self.expected_name:
                        raise ControllerProfileError("コントローラーの接続が変わりました。もう一度やり直してください")
                    joystick = pygame.joystick.Joystick(index)
                    joystick.init()
                    instance_id = joystick.get_instance_id()
                    while not self._stop.is_set():
                        for event in pygame.event.get():
                            if event.type == pygame.JOYDEVICEREMOVED and event.instance_id == instance_id:
                                raise ControllerProfileError("コントローラーが切断されました")
                        self.latest = JoystickSnapshot(
                            tuple(joystick.get_button(i) for i in range(joystick.get_numbuttons())),
                            tuple(joystick.get_axis(i) for i in range(joystick.get_numaxes())),
                            tuple(joystick.get_hat(i) for i in range(joystick.get_numhats())),
                        )
                        time.sleep(MONITOR_INTERVAL)
                finally:
                    pygame.quit()
        except Exception as e:
            _logger.error(f"Controller setup monitor stopped: {e}")
            self.error = str(e)
