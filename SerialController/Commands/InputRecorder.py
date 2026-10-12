#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
操作記録を自動化スクリプト(self.press / self.hold / self.holdChange / self.holdEnd / self.wait)に変換する

- 記録中は入力の変化(スティックは角度・倒し量を丸めた後の変化)のみを保持し、生ログにも逐次書き出す
  (生ログの書き込みは別スレッドで行い、入力の送信を待たせない)
- 記録終了時に、変化の一覧を自動化スクリプトに変換してファイルに出力する
- 入力源に依存しない(Senderが手動操作を合成した状態を渡す)
  (ボタンはDefault形式のビット配置、スティックは送信値(0-255, yは上が0)、タッチは送信値(0は離している)で渡す)

生ログから自動化スクリプトを作り直す場合(SerialControllerフォルダで実行):
    python -m Commands.InputRecorder Controller_Log/record_YYYYMMDD_HHMMSS.csv
"""
from __future__ import annotations

import datetime
import math
import os
import queue
import re
import sys
import threading
import time
from dataclasses import dataclass
from logging import getLogger, DEBUG, NullHandler
from typing import TextIO, List, Optional, Tuple

from Commands.Keys import Button, Hat

# 自動化スクリプトの出力先・タグ
RECORD_COMMAND_DIR = os.path.join("Commands", "PythonCommands", "Record")
RECORD_TAG = "Record"

# スティックの間引き(初期値)
ANGLE_STEP = 5  # 角度の刻み[度]
MAGNITUDE_STEP = 0.2  # 倒し量の刻み
MERGE_INTERVAL = 0.05  # この時間[秒]未満のスティックの変化は1つにまとめる

RAW_LOG_HEADER = "time,buttons,hat,l_angle,l_mag,r_angle,r_mag,touch_x,touch_y"
# 記録終了時に、生ログの書き込みスレッドの終了を待つ時間の上限(秒)
RAW_LOG_CLOSE_TIMEOUT = 5.0
TIME_FORMAT = "%Y%m%d_%H%M%S"

_BUTTON_VALUES = {int(b) for b in Button}

logger = getLogger(__name__)
logger.addHandler(NullHandler())
logger.setLevel(DEBUG)
logger.propagate = True

# (角度[度], 倒し量) / None: ニュートラル
StickValue = Optional[Tuple[int, float]]
# タッチスクリーンの座標(x, y) / None: 離している
TouchValue = Optional[Tuple[int, int]]


@dataclass(frozen=True)
class InputSnapshot:
    """
    ある時点の入力状態(スティックは丸め済み)
    """

    buttons: int = 0  # Buttonのビット列(Default形式のビット配置)
    hat: int = int(Hat.CENTER)
    lstick: StickValue = None
    rstick: StickValue = None
    touch: TouchValue = None


NEUTRAL_SNAPSHOT = InputSnapshot()

# (記録開始からの経過時間[秒], 入力状態)
Event = Tuple[float, InputSnapshot]


def quantize_stick(x: int, y: int, angle_step: int = ANGLE_STEP, magnitude_step: float = MAGNITUDE_STEP) -> StickValue:
    """
    スティックの送信値(0-255, yは上が0)を、Directionで使う(角度, 倒し量)に丸める
    angle_step: 角度の刻み[度]。magnitude_step: 倒し量の刻み
    戻り値: (角度[度]。-180 より大きく 180 以下, 倒し量。0 より大きく 1.0 以下)。丸めて倒し量が 0 なら None
    """
    dx = x - 127.5
    dy = 127.5 - y
    mag = min(math.hypot(dx, dy) / 127.5, 1.0)
    mag = round(round(mag / magnitude_step) * magnitude_step, 2)
    if mag <= 0:
        return None
    angle = int(round(math.degrees(math.atan2(dy, dx)) / angle_step) * angle_step)
    if angle <= -180:
        angle += 360
    return angle, min(mag, 1.0)


class InputRecorder(object):
    """
    入力の変化を記録し、記録終了時に自動化スクリプトを出力するクラス
    """

    def __init__(
        self,
        source_name: str = "",
        raw_log_dir: str | None = None,
        out_dir: str = RECORD_COMMAND_DIR,
        angle_step: int = ANGLE_STEP,
        magnitude_step: float = MAGNITUDE_STEP,
        merge_interval: float = MERGE_INTERVAL,
    ) -> None:
        """
        source_name: 記録する入力源の名前(ログと、出力するスクリプトの先頭のコメントに入れる)
        raw_log_dir: 生ログ(CSV)を書き出すフォルダー(None や空: 書き出さない)
        out_dir: 自動化スクリプトを出力するフォルダー
        angle_step: スティックの角度の刻み[度]
        magnitude_step: スティックの倒し量の刻み
        merge_interval: この時間[秒]未満で続くスティックの変化を、1 つにまとめる
        """
        self.source_name = source_name
        self.raw_log_dir = raw_log_dir
        self.out_dir = out_dir
        self.angle_step = angle_step
        self.magnitude_step = magnitude_step
        self.merge_interval = merge_interval

        self.started_at = None
        self.events: List[Event] = []
        self.raw_log_path = None
        # 生ログは別スレッドで書き出す(ファイル書き込みの待ちで、入力の送信を遅らせないようにする)
        # キューには書き出す行を積み、Noneで終了を伝える
        self._raw_queue: queue.SimpleQueue | None = None
        self._raw_thread: threading.Thread | None = None
        self._t0 = 0.0
        self._last = NEUTRAL_SNAPSHOT
        self._recording = False

    @property
    def recording(self) -> bool:
        """記録している最中か(start から stop まで)"""
        return self._recording

    def start(self) -> None:
        """
        記録を始める(それまでの記録は捨てる)。raw_log_dir があれば、生ログのファイルと、書き込みのスレッドも作る
        (フォルダーやファイルを作れない場合は OSError)
        """
        self.started_at = datetime.datetime.now()
        self._t0 = time.perf_counter()
        self.events = []
        self._last = NEUTRAL_SNAPSHOT
        if self.raw_log_dir:
            os.makedirs(self.raw_log_dir, exist_ok=True)
            self.raw_log_path = os.path.join(self.raw_log_dir, f"record_{self.started_at.strftime(TIME_FORMAT)}.csv")
            raw_log = open(self.raw_log_path, "w", encoding="utf-8")
            raw_log.write(RAW_LOG_HEADER + "\n")
            raw_log.flush()
            self._raw_queue = queue.SimpleQueue()
            self._raw_thread = threading.Thread(
                target=self._write_raw_log, args=(raw_log, self._raw_queue), name="RecordRawLog", daemon=True
            )
            self._raw_thread.start()
        self._recording = True
        logger.info(f"Start recording: {self.source_name}")

    def update_raw(
        self,
        buttons: int,
        hat: int,
        lx: int,
        ly: int,
        rx: int,
        ry: int,
        sx: int = 0,
        sy: int = 0,
        t: float | None = None,
    ) -> None:
        """
        現在の入力状態を渡す(変化していなければ何もしない)
        buttons: Buttonのビット列(Default形式のビット配置)
        hat: Hatの値
        lx, ly, rx, ry: スティックの送信値(0-255, yは上が0)
        sx, sy: タッチスクリーンの送信値(どちらも0なら離している)
        t: 時刻(time.perf_counter() の値。None なら今)
        """
        if not self._recording:
            return
        snapshot = InputSnapshot(
            int(buttons) & sum(_BUTTON_VALUES),
            int(hat),
            quantize_stick(lx, ly, self.angle_step, self.magnitude_step),
            quantize_stick(rx, ry, self.angle_step, self.magnitude_step),
            None if (sx == 0 and sy == 0) else (int(sx), int(sy)),
        )
        self.update(snapshot, t)

    def update(self, snapshot: InputSnapshot, t: float | None = None) -> None:
        """
        丸め済みの入力状態を渡す。前の状態から変わっていれば、変化として記録し、生ログにも書き出す
        t: 時刻(time.perf_counter() の値。None なら今)
        """
        if not self._recording or snapshot == self._last:
            return
        elapsed = (time.perf_counter() if t is None else t) - self._t0
        if self.events:
            # 時刻が前の変化より前にならないようにする
            elapsed = max(elapsed, self.events[-1][0])
        self.events.append((elapsed, snapshot))
        self._last = snapshot
        if self._raw_queue is not None:
            self._raw_queue.put(_format_raw_line(elapsed, snapshot))

    @staticmethod
    def _write_raw_log(raw_log: TextIO, lines: queue.SimpleQueue) -> None:
        """
        生ログの書き込みスレッド: キューの行を書き出す(溜まっている分はまとめて書いてからflushする)
        raw_log: 書き込む先のファイル(終わるときに、ここで閉じる)
        lines: 書き出す行のキュー(None が来たら終わる)
        """
        try:
            closing = False
            while not closing:
                batch = [lines.get()]
                try:
                    while True:
                        batch.append(lines.get_nowait())
                except queue.Empty:
                    pass
                if None in batch:
                    closing = True
                    batch = batch[: batch.index(None)]
                if batch:
                    raw_log.write("\n".join(batch) + "\n")
                    raw_log.flush()
        except Exception as e:
            logger.error(f"Failed to write the raw log: {e}")
        finally:
            raw_log.close()

    def _close_raw_log(self) -> None:
        """
        生ログを最後まで書き出して閉じる
        """
        if self._raw_queue is None:
            return
        self._raw_queue.put(None)
        self._raw_thread.join(RAW_LOG_CLOSE_TIMEOUT)
        if self._raw_thread.is_alive():
            logger.warning("The raw log writer did not finish in time.")
        self._raw_queue = None
        self._raw_thread = None

    def stop(self) -> str | None:
        """
        記録を終了し、自動化スクリプトを出力する
        戻り値: 出力したファイルのパス(操作が無かった場合はNone)
        """
        if not self._recording:
            return None
        # 入力が残っていれば、終了時点で全て離したものとする
        self.update(NEUTRAL_SNAPSHOT)
        self._recording = False
        self._close_raw_log()
        logger.info(f"Stop recording: {self.source_name}")
        if not self.events:
            return None
        return write_record_command(self.events, self.started_at, self.out_dir, self.merge_interval, self.source_name)


############### 生ログ ###############
def _format_raw_line(t: float, s: InputSnapshot) -> str:
    """生ログの 1 行(RAW_LOG_HEADER の並び。t は経過時間[秒]。倒していないスティックと、離しているタッチは空)"""

    def stick(v: StickValue) -> tuple[str, str]:
        """スティックの値を (角度, 倒し量) の文字列にする"""
        return ("", "") if v is None else (str(v[0]), f"{v[1]:g}")

    touch = ("", "") if s.touch is None else (str(s.touch[0]), str(s.touch[1]))
    return ",".join([f"{t:.4f}", str(s.buttons), str(s.hat), *stick(s.lstick), *stick(s.rstick), *touch])


def load_raw_log(path: str) -> List[Event]:
    """
    生ログ(CSV)を読んで、入力の変化の一覧にする(書式が違う行は ValueError、開けなければ OSError)
    """

    def stick(angle: str, mag: str) -> StickValue:
        """生ログの 2 つの列を、スティックの値に戻す(空は、倒していない)"""
        return None if angle == "" else (int(angle), float(mag))

    events = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("time,"):
                continue
            # タッチの列が無い古い生ログも読めるようにする
            t, buttons, hat, la, lm, ra, rm, tx, ty = (line.split(",") + ["", ""])[:9]
            touch = None if tx == "" else (int(tx), int(ty))
            events.append((float(t), InputSnapshot(int(buttons), int(hat), stick(la, lm), stick(ra, rm), touch)))
    return events


############### 自動化スクリプトへの変換 ###############
def _is_stick_only_change(a: InputSnapshot, b: InputSnapshot) -> bool:
    """a から b への変化が、スティックとタッチの位置だけか(ボタン・十字キー・タッチの有無は同じ)"""
    # スティックの向き・倒し量、タッチの位置(ドラッグ)のみの変化
    return a != b and a.buttons == b.buttons and a.hat == b.hat and (a.touch is None) == (b.touch is None)


def merge_stick_changes(events: List[Event], interval: float = MERGE_INTERVAL) -> List[Event]:
    """
    スティック・タッチ位置のみの変化が interval 秒未満で続く場合、1つの変化にまとめる
    (まとめた変化の時刻は最初の変化の時刻、状態は最後の変化の状態)
    """
    merged: List[Event] = []
    for t, s in events:
        if merged:
            prev_t, prev_s = merged[-1]
            before = merged[-2][1] if len(merged) >= 2 else NEUTRAL_SNAPSHOT
            if t - prev_t < interval and _is_stick_only_change(before, prev_s) and _is_stick_only_change(prev_s, s):
                if s == before:
                    # 元に戻った場合は変化自体を無かったことにする
                    merged.pop()
                else:
                    merged[-1] = (prev_t, s)
                continue
        merged.append((t, s))
    return merged


def _items(s: InputSnapshot) -> dict:
    """
    入力状態を {キー: 入力} に分解する
    (キーは ("btn", ビットの番号)、"hat"、"lstick"、"rstick"、"touch"。入力は Button、Hat、または値の組)
    """
    items = {}
    for i in range(s.buttons.bit_length()):
        value = 1 << i
        if s.buttons & value and value in _BUTTON_VALUES:
            items[("btn", i)] = Button(value)
    if s.hat != int(Hat.CENTER):
        items["hat"] = Hat(s.hat)
    if s.lstick is not None:
        items["lstick"] = s.lstick
    if s.rstick is not None:
        items["rstick"] = s.rstick
    if s.touch is not None:
        items["touch"] = s.touch
    return items


def _expr(key: str | tuple[str, int], value: Button | Hat | tuple) -> str:
    """_items の 1 つの入力を、スクリプトに書く式にする("Button.A"、"Direction(Stick.LEFT, 90)" など)"""
    if key in ("lstick", "rstick"):
        stick = "Stick.LEFT" if key == "lstick" else "Stick.RIGHT"
        angle, mag = value
        if mag >= 1.0:
            return f"Direction({stick}, {angle})"
        return f"Direction({stick}, {angle}, {mag:g})"
    if key == "touch":
        return f"Touchscreen({value[0]}, {value[1]})"
    if key == "hat":
        return f"Hat.{value.name}"
    return f"Button.{value.name}"


def _exprs(pairs: list[tuple]) -> str:
    """(キー, 入力) の並びを、スクリプトに書く式にする(1 つならそのまま、2 つ以上ならリスト)"""
    exprs = [_expr(k, v) for k, v in pairs]
    return exprs[0] if len(exprs) == 1 else "[" + ", ".join(exprs) + "]"


def _sec(t: float) -> str:
    """秒数を、小数 3 桁の文字列にする(負の値は 0)"""
    return f"{max(t, 0.0):.3f}"


def generate_steps(events: List[Event], merge_interval: float = MERGE_INTERVAL) -> List[str]:
    """
    入力の変化の一覧を自動化スクリプトの処理(1行1文)に変換する
    - 押してから離すまでに他の入力の変化が無い場合: self.press
    - それ以外: self.hold / self.holdChange / self.holdEnd と self.wait
    記録開始から最初の操作までの待ち時間は含めない
    """
    events = merge_stick_changes(events, merge_interval)

    # 各時点の変化を (離した入力, 変更した入力, 押した入力) に分解する
    actions = []
    prev = {}
    for t, s in events:
        cur = _items(s)
        released = [(k, prev[k]) for k in prev if k not in cur]
        changed = [(k, cur[k]) for k in cur if k in prev and prev[k] != cur[k]]
        pressed = [(k, cur[k]) for k in cur if k not in prev]
        if released or changed or pressed:
            actions.append((t, released, changed, pressed))
        prev = cur

    def gap(i: int) -> float:
        """i 番目の変化から、次の変化までの時間[秒](最後の変化は 0)"""
        # 次の変化までの時間
        return actions[i + 1][0] - actions[i][0] if i + 1 < len(actions) else 0.0

    lines = []
    i = 0
    while i < len(actions):
        t, released, changed, pressed = actions[i]
        if pressed and not released and not changed and i + 1 < len(actions):
            t2, released2, changed2, pressed2 = actions[i + 1]
            if not changed2 and not pressed2 and {k for k, _ in released2} == {k for k, _ in pressed}:
                lines.append(f"self.press({_exprs(pressed)}, duration={_sec(t2 - t)}, wait={_sec(gap(i + 1))})")
                i += 2
                continue

        stmts = [(m, p) for m, p in (("holdEnd", released), ("holdChange", changed), ("hold", pressed)) if p]
        for j, (method, pairs) in enumerate(stmts):
            wait = gap(i) if j == len(stmts) - 1 else 0.0
            if method == "holdEnd":
                lines.append(f"self.holdEnd({_exprs(pairs)})")
                if wait > 0:
                    lines.append(f"self.wait({_sec(wait)})")
            else:
                lines.append(f"self.{method}({_exprs(pairs)}, wait={_sec(wait)})")
        i += 1
    return lines


def build_command_source(steps: List[str], started_at: datetime.datetime, source_name: str = "") -> str:
    """
    自動化スクリプト(PythonCommand を継承したクラスの .py)の中身を作る

    steps: do() の中に並べる処理(generate_steps の戻り値。空なら pass)
    started_at: 記録を始めた日時(クラス名と、表示名に入れる)
    source_name: 入力源の名前(先頭のコメントに入れる)
    """
    class_name = f"Record_{started_at.strftime(TIME_FORMAT)}"
    name = f"Record {started_at.strftime('%Y-%m-%d %H:%M:%S')}"
    source = f"{source_name}の" if source_name else ""
    body = "\n".join("        " + s for s in steps) if steps else "        pass"
    return (
        "#!/usr/bin/env python3\n"
        "# -*- coding: utf-8 -*-\n"
        f"# {source}操作記録から自動生成 (記録開始: {started_at.strftime('%Y-%m-%d %H:%M:%S')})\n"
        "\n"
        "from Commands.Keys import Button, Direction, Hat, Stick, Touchscreen\n"
        "from Commands.PythonCommandBase import PythonCommand\n"
        "\n"
        "\n"
        f"class {class_name}(PythonCommand):\n"
        f"    NAME = {name!r}\n"
        f"    TAGS = [{RECORD_TAG!r}]\n"
        "\n"
        "    def __init__(self):\n"
        "        super().__init__()\n"
        "\n"
        "    def do(self):\n"
        f"{body}\n"
    )


def write_record_command(
    events: List[Event],
    started_at: datetime.datetime,
    out_dir: str = RECORD_COMMAND_DIR,
    merge_interval: float = MERGE_INTERVAL,
    source_name: str = "",
) -> str:
    """
    自動化スクリプトをファイルに出力し、そのパスを返す
    (ファイル名は Record_記録開始の日時.py。同じ名前があれば上書きする)
    """
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"Record_{started_at.strftime(TIME_FORMAT)}.py")
    source = build_command_source(generate_steps(events, merge_interval), started_at, source_name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(source)
    return path


def convert_raw_log(path: str, out_dir: str = RECORD_COMMAND_DIR, merge_interval: float = MERGE_INTERVAL) -> str:
    """
    生ログから自動化スクリプトを作り直す(記録開始時刻はファイル名から取得する。取れなければ今の時刻)
    戻り値: 出力したファイルのパス
    """
    m = re.search(r"(\d{8}_\d{6})", os.path.basename(path))
    started_at = datetime.datetime.strptime(m.group(1), TIME_FORMAT) if m else datetime.datetime.now()
    return write_record_command(load_raw_log(path), started_at, out_dir, merge_interval)


if __name__ == "__main__":
    for p in sys.argv[1:]:
        print(convert_raw_log(p))
