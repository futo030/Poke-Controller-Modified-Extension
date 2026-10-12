#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
コマンドの開始と停止の予約(時刻・タイマー)

画面(tkinter)には触れない。画面が、1 秒に数回 tick() を呼び、時刻が来ていれば、渡してある関数で開始・停止する。
- 開始の予約: 決めた時刻に、決めたコマンド(実行リストも可)を開始する
- 停止の予約: 決めた時刻に止める。または、開始から決めた時間がたったら止める
- 予約は、アプリを閉じると消える(保存しない)
- PC の設定(スリープ)は、変えない。PC がスリープしている間は、予約は働かないので、予約するときに、画面が警告を出す。
  スリープなどで、開始の時刻を大きく過ぎてから気づいた場合は、開始しない(遅れて、思わぬ時刻に始めないため)
"""
from __future__ import annotations

import datetime
from logging import getLogger, DEBUG, NullHandler
from typing import Callable

_logger = getLogger(__name__)
_logger.addHandler(NullHandler())
_logger.setLevel(DEBUG)
_logger.propagate = True

TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
MINUTES_MAX = 60 * 24 * 7
# 開始の予約の時刻を、これより長く(秒)過ぎていたら、開始しない(PC がスリープしていた場合など)
START_LATE_LIMIT_SECONDS = 60
# 予約するときに、画面が警告として出す文
SLEEP_WARNING = (
    "予約した時刻に PC がスリープしていると、予約は正常に動作しません。\n"
    "(開始は行われず、停止は、スリープから戻った後になります)\n"
    "このアプリは、PC のスリープの設定を変えません。\n"
    "予約の時刻まで PC がスリープしないように、Windows の電源の設定を確かめてください。"
)


def parse_clock(text: str, now: datetime.datetime) -> datetime.datetime:
    """
    「時:分」または「時:分:秒」の文字を、次にその時刻になる日時にする(今より前の時刻は、明日)。
    読めないときは ValueError
    """
    parts = text.strip().replace("：", ":").split(":")
    if len(parts) not in (2, 3) or not all(part.strip().isdigit() for part in parts):
        raise ValueError("時刻は 23:30 のように、時:分 で入力してください。")
    hour, minute = int(parts[0]), int(parts[1])
    second = int(parts[2]) if len(parts) == 3 else 0
    if not (0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 59):
        raise ValueError("時刻は 0:00 〜 23:59 で入力してください。")
    when = now.replace(hour=hour, minute=minute, second=second, microsecond=0)
    if when <= now:
        when += datetime.timedelta(days=1)
    return when


def parse_minutes(text: str) -> float:
    """「◯分」の入力欄の文字を、分の数にする(0 より大きく、MINUTES_MAX まで。読めないときは ValueError)"""
    try:
        minutes = float(text.strip())
    except ValueError:
        raise ValueError("分は、数で入力してください(例: 30、1.5)。")
    if not 0 < minutes <= MINUTES_MAX:
        raise ValueError(f"分は、0 より大きく {MINUTES_MAX} までにしてください。")
    return minutes


def format_remaining(seconds: float) -> str:
    """残り時間の表示(例: 1 時間 02 分 03 秒)"""
    total = max(0, int(seconds + 0.999))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours} 時間 {minutes:02d} 分 {secs:02d} 秒"
    if minutes:
        return f"{minutes} 分 {secs:02d} 秒"
    return f"{secs} 秒"


class RunSchedule:
    """開始と停止の予約を持ち、時刻が来たら、開始・停止する"""

    def __init__(
        self,
        start: Callable[[str, str], bool],
        stop: Callable[[], None],
        is_running: Callable[[], bool],
        notify: Callable[[str], None],
        now: Callable[[], datetime.datetime] = datetime.datetime.now,
    ):
        """
        start: コマンドを開始する関数(種別, 名前)。開始できたかを返す
        stop: 実行中のコマンドを止める関数
        is_running: コマンドを実行中かを返す関数
        notify: 知らせ(予約した・開始した・止めた・取り消したなど)を表示する関数
        now: 今の日時を返す関数(テストで差し替える)
        """
        self._start = start
        self._stop = stop
        self._is_running = is_running
        self._notify = notify
        self._now = now
        # 開始の予約: 日時と、開始するコマンド(種別, 名前)
        self.start_at: datetime.datetime | None = None
        self.start_target: tuple | None = None
        # 停止の予約: 日時。または、開始から止めるまでの分(開始の予約が働いたときに、日時に直す)
        self.stop_at: datetime.datetime | None = None
        self.stop_after_minutes: float | None = None
        # 停止の予約をした後に、コマンドが動いているのを見たか(見た後で終わっていたら、予約を取り消す)
        self._stop_armed = False

    # ---------------------------------------------------------------- 予約する・取り消す

    def reserve_start(self, when: datetime.datetime, command_type: str, name: str) -> None:
        """開始を予約する(前の開始の予約は、置き換える)"""
        self.start_at = when
        self.start_target = (command_type, name)
        self._notify(f"開始を予約しました: {when.strftime(TIME_FORMAT)} に「{name}」")

    def cancel_start(self) -> None:
        """開始の予約を取り消す(「開始から◯分で停止」の予約も、一緒に取り消す)"""
        if self.start_at is None:
            return
        self.start_at = None
        self.start_target = None
        self._notify("開始の予約を取り消しました。")
        if self.stop_after_minutes is not None:
            self.stop_after_minutes = None
            self._notify("「開始から」の停止の予約も、取り消しました。")

    def reserve_stop_at(self, when: datetime.datetime) -> None:
        """決めた日時に止める予約をする(前の停止の予約は、置き換える)"""
        self.stop_at = when
        self.stop_after_minutes = None
        self._stop_armed = self._is_running()
        self._notify(f"停止を予約しました: {when.strftime(TIME_FORMAT)}")

    def reserve_stop_after(self, minutes: float) -> str:
        """
        開始から minutes 分で止める予約をする。予約できないときは、その理由を返す(できたときは空文字)。
        実行中なら、今から数える。開始を予約していれば、その開始から数える。どちらでもなければ、予約できない
        """
        if self._is_running():
            self.stop_at = self._now() + datetime.timedelta(minutes=minutes)
            self.stop_after_minutes = None
            self._stop_armed = True
            self._notify(f"停止を予約しました: 今から {minutes:g} 分後({self.stop_at.strftime(TIME_FORMAT)})")
        elif self.start_at is not None:
            self.stop_at = None
            self.stop_after_minutes = minutes
            self._stop_armed = False
            self._notify(f"停止を予約しました: 予約した開始から {minutes:g} 分後")
        else:
            return "コマンドを実行中か、開始を予約しているときだけ、「開始から」の停止を予約できます。"
        return ""

    def cancel_stop(self) -> None:
        """停止の予約を取り消す"""
        if self.stop_at is None and self.stop_after_minutes is None:
            return
        self.stop_at = None
        self.stop_after_minutes = None
        self._stop_armed = False
        self._notify("停止の予約を取り消しました。")

    def cancel_all(self) -> None:
        """すべての予約を、知らせずに取り消す(アプリを閉じるとき)"""
        self.start_at = self.start_target = None
        self.stop_at = self.stop_after_minutes = None
        self._stop_armed = False

    @property
    def pending(self) -> bool:
        """予約が残っているか"""
        return self.start_at is not None or self.stop_at is not None or self.stop_after_minutes is not None

    # ---------------------------------------------------------------- 時刻が来たか

    def tick(self) -> None:
        """時刻が来ていれば、開始・停止する(画面が、1 秒に数回呼ぶ)"""
        now = self._now()
        if self.start_at is not None and now >= self.start_at:
            command_type, name = self.start_target
            late = (now - self.start_at).total_seconds()
            self.start_at = None
            self.start_target = None
            if late > START_LATE_LIMIT_SECONDS:
                # PC がスリープしていた場合など。遅れて、思わぬ時刻に始めない
                self._notify(
                    f"予約の時刻を {format_remaining(late)} 過ぎていたので、「{name}」は開始しませんでした"
                    "(PC がスリープしていた可能性があります)。"
                )
                started = False
            elif self._is_running():
                self._notify(f"予約の時刻になりましたが、ほかのコマンドを実行中のため、「{name}」は開始しませんでした。")
                started = False
            else:
                self._notify(f"予約の時刻になりました。「{name}」を開始します。")
                started = bool(self._start(command_type, name))
                if not started:
                    self._notify(f"「{name}」を開始できませんでした。")
            if self.stop_after_minutes is not None:
                if started:
                    self.stop_at = now + datetime.timedelta(minutes=self.stop_after_minutes)
                    self._stop_armed = True
                    self._notify(f"停止の予約: {self.stop_at.strftime(TIME_FORMAT)}")
                else:
                    self._notify("開始しなかったので、「開始から」の停止の予約を取り消しました。")
                self.stop_after_minutes = None
        if self.stop_at is not None:
            running = self._is_running()
            if running:
                self._stop_armed = True
            if now >= self.stop_at:
                self.stop_at = None
                self._stop_armed = False
                if running:
                    self._notify("停止の予約の時刻になりました。コマンドを止めます。")
                    self._stop()
                else:
                    self._notify("停止の予約の時刻になりましたが、実行中のコマンドはありませんでした。")
            elif self._stop_armed and not running:
                # 止める相手のコマンドが、先に終わった
                self.stop_at = None
                self._stop_armed = False
                self._notify("コマンドが終わったので、停止の予約を取り消しました。")

    # ---------------------------------------------------------------- 表示

    def describe(self) -> tuple[str, str]:
        """今の予約の表示(開始の予約, 停止の予約)。予約がなければ「予約はありません」"""
        now = self._now()
        if self.start_at is None:
            start = "予約はありません"
        else:
            remaining = format_remaining((self.start_at - now).total_seconds())
            start = f"{self.start_at.strftime(TIME_FORMAT)} に「{self.start_target[1]}」を開始(あと {remaining})"
        if self.stop_at is not None:
            remaining = format_remaining((self.stop_at - now).total_seconds())
            stop = f"{self.stop_at.strftime(TIME_FORMAT)} に停止(あと {remaining})"
        elif self.stop_after_minutes is not None:
            stop = f"予約した開始から {self.stop_after_minutes:g} 分後に停止"
        else:
            stop = "予約はありません"
        return start, stop
