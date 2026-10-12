#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
プロファイル(profiles/<名前>/ に置く設定一式)の一覧・名前の確認・優先度・起動中の確認
"""
from __future__ import annotations

import atexit
import os
import re

PROFILES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "profiles")
DEFAULT_PROFILE = "default"
PROFILE_NAME_MAX_LENGTH = 50
_PROFILE_NAME_PATTERN = re.compile(r"[A-Za-z0-9_-]+")
# Windowsでフォルダ名に使えない名前
_RESERVED_NAMES = {"con", "prn", "aux", "nul"} | {f"{name}{num}" for name in ("com", "lpt") for num in range(1, 10)}


def list_profiles() -> list[str]:
    """
    プロファイル名の一覧(profiles/ にあるフォルダ名)を名前順で返す
    """
    try:
        names = [name for name in os.listdir(PROFILES_DIR) if os.path.isdir(os.path.join(PROFILES_DIR, name))]
    except OSError:
        return []
    return sorted(names, key=str.lower)


def find_profile(name: str) -> str | None:
    """
    同じ名前のプロファイルがあれば、その名前を返す(大文字・小文字は区別しない)
    """
    for profile in list_profiles():
        if profile.lower() == name.lower():
            return profile
    return None


def check_profile_name(name: str) -> str | None:
    """
    新しいプロファイルの名前として使えるかを確かめる。使えない場合は理由を、使える場合はNoneを返す
    """
    if name == "":
        return "プロファイル名を入力してください。"
    if _PROFILE_NAME_PATTERN.fullmatch(name) is None:
        return "プロファイル名に使えるのは、アルファベット・数字・「-」・「_」のみです。"
    if len(name) > PROFILE_NAME_MAX_LENGTH:
        return f"プロファイル名は{PROFILE_NAME_MAX_LENGTH}文字以内にしてください。"
    if name.lower() in _RESERVED_NAMES:
        return f"「{name}」はフォルダ名に使えません。別の名前にしてください。"
    existing = find_profile(name)
    if existing is not None:
        return f"プロファイル「{existing}」はすでに存在します。別の名前にしてください。"
    return None


# ---------- 設定を保存しないモード ----------
# 同じプロファイルで2つ目以降に起動した場合はTrueにし、設定ファイル(settings.ini)を書き換えない
_read_only = False


def set_read_only(read_only: bool) -> None:
    """設定を保存しないモードにする / 解く(同じプロファイルで 2 つ目以降に起動したときに True にする)"""
    global _read_only
    _read_only = read_only


def is_read_only() -> bool:
    """設定を保存しないモードか"""
    return _read_only


# ---------- 優先度(--auto で起動するときに選ぶ順番) ----------
# profiles/ の直下に置くファイル。1行に1つプロファイル名を書き、上にあるものほど優先する
PRIORITY_FILE_NAME = "priority.txt"


def _priority_path() -> str:
    """優先度ファイルの場所"""
    return os.path.join(PROFILES_DIR, PRIORITY_FILE_NAME)


def read_priority() -> list[str] | None:
    """
    優先度ファイルに書かれたプロファイル名を上から順に返す。ファイルがない場合はNone
    (空行と # で始まる行は読み飛ばす)
    """
    try:
        with open(_priority_path(), encoding="utf-8-sig") as file:
            lines = [line.strip() for line in file]
    except OSError:
        return None
    return [line for line in lines if line != "" and not line.startswith("#")]


def _profiles_by_created() -> list[str]:
    """
    プロファイル名を、フォルダの作成日時が古い順に返す
    """

    def created(name: str) -> float:
        """フォルダの作成日時(取得できない場合は、最後に並ぶよう無限大)"""
        try:
            return os.path.getctime(os.path.join(PROFILES_DIR, name))
        except OSError:
            return float("inf")

    return sorted(list_profiles(), key=lambda name: (created(name), name.lower()))


def add_profile_priority(name: str) -> None:
    """
    新しく作ったプロファイルを、優先度ファイルの最後(優先度が最も低い位置)に追加する
    ファイルがない場合は作り直す(default、すでにあるプロファイルを作成日時の古い順、の順に書く)
    すでに書かれている名前(大文字・小文字は区別しない)の場合は、何もしない
    """
    names = read_priority()
    if names is None:
        names = [DEFAULT_PROFILE]
        for profile in _profiles_by_created():
            if profile.lower() not in [n.lower() for n in names] and profile.lower() != name.lower():
                names.append(profile)
    elif name.lower() in [n.lower() for n in names]:
        return
    if name.lower() not in [n.lower() for n in names]:
        names.append(name)
    os.makedirs(PROFILES_DIR, exist_ok=True)
    with open(_priority_path(), "w", encoding="utf-8") as file:
        file.write("\n".join(names) + "\n")


def auto_profile_order() -> list[str]:
    """
    --auto で起動するときに試すプロファイルの順番
    優先度ファイルがある場合は、書かれた順(フォルダがないものは除く。書かれていないプロファイルは対象にしない)
    優先度ファイルがない場合は、すべてのプロファイルを作成日時の古い順
    """
    by_created = _profiles_by_created()
    names = read_priority()
    if names is None:
        return by_created
    order = []
    for name in names:
        profile = next((p for p in by_created if p.lower() == name.lower()), None)
        if profile is not None and profile not in order:
            order.append(profile)
    return order


# ---------- プロファイルと起動ファイルの作成 ----------
def create_profile(name: str) -> None:
    """
    新しいプロファイルnameを作る。--auto での優先度は最も低くする
    (フォルダだけを作る。設定ファイルは、そのプロファイルで起動したときに初期値で作られる)
    すでにフォルダがある場合は FileExistsError
    """
    os.makedirs(os.path.join(PROFILES_DIR, name))
    add_profile_priority(name)


# 起動用の bat の形
BAT_UV = "uv"  # uv の環境向け(PokeConExtension.bat を呼ぶ。PC に Python が入っていなくても動く)
BAT_CLASSIC = "classic"  # 従来の形(PC の python で起動する。.venv があれば、起動した後に .venv の Python に切り替わる)
BAT_LABELS = {BAT_UV: "uv 向け (PokeConExtension.bat)", BAT_CLASSIC: "従来 (python Window.py)"}


def has_uv_environment() -> bool:
    """ツールのフォルダに、uv の環境(.venv)があるか"""
    folder = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.isfile(os.path.join(folder, ".venv", "Scripts", "python.exe"))


def create_profile_bat(name: str, kind: str | None = None) -> str | None:
    """
    プロファイルnameで起動するbatファイルを、ツールのフォルダ(SerialControllerの1つ上)に作る
    作ったファイルのパスを返す。すでにある場合は何もせずNoneを返す
    kind: bat の形(BAT_UV / BAT_CLASSIC)。指定がなければ、uv の環境(.venv)がある場合は BAT_UV、ない場合は BAT_CLASSIC
    """
    folder = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(folder, f"ExecutePokeConModified-Extension_{name}.bat")
    if os.path.exists(path):
        return None
    if kind not in (BAT_UV, BAT_CLASSIC):
        kind = BAT_UV if has_uv_environment() else BAT_CLASSIC
    if kind == BAT_UV:
        text = f'@call "%~dp0PokeConExtension.bat" --profile {name}\n'
    else:
        text = (
            "python SerialController/PokeConUpdateChecker.py\ncd SerialController\n"
            f"python Window.py --profile {name}\npause\n"
        )
    with open(path, "w", encoding="utf-8") as file:
        file.write(text)
    return path


# ---------- 起動中の確認 ----------
# プロファイルごとに profiles/<名前>.lock を開いてロックし、終了するまで持ち続ける
# (ロックはプロセスが終わるとOSが外すので、異常終了しても残らない)
_held_locks = {}


def acquire_profile_lock(name: str) -> bool:
    """
    プロファイルnameを「起動中」にする。すでに他で起動されている場合はFalseを返す
    (このプロセスが、すでに「起動中」にしている場合は True)
    """
    key = name.lower()
    if key in _held_locks:
        return True
    os.makedirs(PROFILES_DIR, exist_ok=True)
    path = os.path.join(PROFILES_DIR, f"{key}.lock")
    try:
        file = open(path, "a+")
    except OSError:
        return False
    try:
        file.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        file.close()
        return False
    _held_locks[key] = (file, path)
    return True


def select_auto_profile() -> str | None:
    """
    --auto: 起動されていないプロファイルを優先度の順に探し、起動中にして名前を返す
    すべて起動されている場合はNone
    """
    for name in auto_profile_order():
        if acquire_profile_lock(name):
            return name
    return None


@atexit.register
def _release_profile_locks() -> None:
    """終了するときに、持っているロックを外して、ロックのファイルを消す"""
    for file, path in _held_locks.values():
        try:
            file.close()
            os.remove(path)
        except OSError:
            pass
    _held_locks.clear()
