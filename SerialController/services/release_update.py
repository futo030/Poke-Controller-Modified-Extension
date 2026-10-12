#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Git を使わない更新(Release のソースコードの ZIP で、ファイルを入れ替える)

新しい版の ZIP と、手元の版の ZIP を取得し、手元のファイルと 3 つを比べて、版の間で変わったファイルだけを扱う。
- 新しい版で変わった・増えた: 新しい版のものにする(手元で書き換えてあれば、先に old/日時/ へ退避する)
- 新しい版でなくなった: 消す(手元で書き換えてあれば、old/日時/ へ退避する)
- 版の間で変わっていない・どちらの版にもない: 触らない(利用者の設定、スクリプト、画像など)
取得と比較がすべて終わってから、入れ替えを始める。画面(tkinter)には触れない。標準の機能だけを使う。
"""
from __future__ import annotations

import os
import shutil
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from logging import getLogger, DEBUG, NullHandler
from typing import Callable

_logger = getLogger(__name__)
_logger.addHandler(NullHandler())
_logger.setLevel(DEBUG)
_logger.propagate = True

TIMEOUT = 60
BACKUP_DIR = "old"
# 版の間で変わっていても、上書きも削除もしない場所(利用者が書き換えて使うもの)
PROTECTED = ("SerialController/profiles/",)


class UpdateError(Exception):
    """更新できなかった(メッセージは、そのまま表示できる文)。この例外が出たときは、手元のファイルを変えていない"""


@dataclass
class Plan:
    """入れ替えの内容(どれも、リポジトリから見た場所。区切りは /)"""

    replace: list = field(default_factory=list)  # 新しい版のものにする
    remove: list = field(default_factory=list)  # 消す
    backup: list = field(default_factory=list)  # replace / remove の前に、退避する(手元で書き換えてある)

    @property
    def is_empty(self) -> bool:
        return not (self.replace or self.remove)


def download(url: str, path: str, opener=urllib.request.urlopen) -> None:
    """URL の内容をファイルに保存する。できなければ UpdateError"""
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "Poke-Controller-Modified-Extension"})
        with opener(request, timeout=TIMEOUT) as response, open(path, "wb") as file:
            shutil.copyfileobj(response, file)
    except (OSError, ValueError) as e:
        raise UpdateError(f"ダウンロードできませんでした: {e}") from e


def extract(zip_path: str, folder: str) -> str:
    """ZIP を展開して、中身のいちばん上のフォルダー(リポジトリ名-タグ)の場所を返す"""
    try:
        with zipfile.ZipFile(zip_path) as archive:
            for name in archive.namelist():
                # フォルダーの外を指す名前は、展開しない
                if name.startswith(("/", "\\")) or ".." in name.replace("\\", "/").split("/") or ":" in name:
                    raise UpdateError(f"ZIP の中に、展開できない名前があります: {name}")
            archive.extractall(folder)
    except (OSError, zipfile.BadZipFile) as e:
        raise UpdateError(f"ZIP を展開できませんでした: {e}") from e
    tops = [name for name in os.listdir(folder) if os.path.isdir(os.path.join(folder, name))]
    if len(tops) != 1:
        raise UpdateError("ZIP の中身が、想定した形ではありません。")
    return os.path.join(folder, tops[0])


def list_files(root: str) -> set:
    """フォルダーの中のファイル(root から見た場所。区切りは /)"""
    found = set()
    for folder, _, names in os.walk(root):
        for name in names:
            found.add(os.path.relpath(os.path.join(folder, name), root).replace(os.sep, "/"))
    return found


def same_content(first: str, second: str) -> bool:
    """2 つのファイルの中身が同じか(改行コードの違いは、同じとみなす。git の設定で変わるため)"""
    try:
        with open(first, "rb") as a, open(second, "rb") as b:
            return a.read().replace(b"\r\n", b"\n") == b.read().replace(b"\r\n", b"\n")
    except OSError:
        return False


def is_protected(relative: str) -> bool:
    return relative.startswith(PROTECTED)


def make_plan(local_root: str, old_root: str, new_root: str) -> Plan:
    """手元(local_root)、手元の版(old_root)、新しい版(new_root)を比べて、入れ替えの内容を決める"""
    plan = Plan()
    old_files, new_files = list_files(old_root), list_files(new_root)

    def path(root: str, relative: str) -> str:
        return os.path.join(root, *relative.split("/"))

    for relative in sorted(new_files):
        if is_protected(relative):
            continue
        local, old, new = path(local_root, relative), path(old_root, relative), path(new_root, relative)
        if relative in old_files and same_content(old, new):
            continue  # 版の間で変わっていない
        if os.path.isfile(local):
            if same_content(local, new):
                continue  # すでに新しい版と同じ
            if relative not in old_files or not same_content(local, old):
                plan.backup.append(relative)  # 手元で書き換えてある(または、同じ名前のファイルを利用者が置いている)
        plan.replace.append(relative)
    for relative in sorted(old_files - new_files):
        local = path(local_root, relative)
        if is_protected(relative) or not os.path.isfile(local):
            continue
        if not same_content(local, path(old_root, relative)):
            plan.backup.append(relative)
        plan.remove.append(relative)
    return plan


def apply_plan(plan: Plan, local_root: str, new_root: str, backup_root: str) -> list:
    """入れ替えを行う。できなかったファイルを [(場所, 理由)] で返す(できなかったファイルは、元のまま)"""
    failed = []

    def path(root: str, relative: str) -> str:
        return os.path.join(root, *relative.split("/"))

    skip = set()
    for relative in plan.backup:
        try:
            target = path(backup_root, relative)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copy2(path(local_root, relative), target)
        except OSError as e:
            # 退避できなかったファイルは、入れ替えない
            failed.append((relative, f"退避できませんでした: {e}"))
            skip.add(relative)
    for relative in plan.replace:
        if relative in skip:
            continue
        try:
            target = path(local_root, relative)
            if os.path.isdir(target):
                raise IsADirectoryError("同じ名前のフォルダーがあります")
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copy2(path(new_root, relative), target)
        except OSError as e:
            failed.append((relative, str(e)))
    for relative in plan.remove:
        if relative in skip:
            continue
        try:
            os.remove(path(local_root, relative))
            folder = os.path.dirname(path(local_root, relative))
            while os.path.normcase(folder) != os.path.normcase(local_root) and not os.listdir(folder):
                os.rmdir(folder)
                folder = os.path.dirname(folder)
        except OSError as e:
            failed.append((relative, str(e)))
    return failed


@dataclass
class Result:
    """更新の結果。backup_dir: 退避した先(退避したファイルがなければ None)、failed: 入れ替えられなかったファイル"""

    plan: Plan
    backup_dir: str | None
    failed: list


def update(
    local_root: str, old_zip_url: str, new_zip_url: str,
    log: Callable[[str], None] = print, opener=urllib.request.urlopen, now: datetime | None = None,
) -> Result:  # fmt: skip
    """
    手元の版の ZIP(old_zip_url)と、新しい版の ZIP(new_zip_url)を取得して、手元のファイルを入れ替える。
    取得・展開・比較のどこかで失敗したら UpdateError(その場合、手元のファイルは変えていない)
    """
    with tempfile.TemporaryDirectory() as temporary:
        roots = {}
        for label, url in (("new", new_zip_url), ("old", old_zip_url)):
            log(f"ダウンロードしています: {url}")
            zip_path = os.path.join(temporary, f"{label}.zip")
            download(url, zip_path, opener)
            roots[label] = extract(zip_path, os.path.join(temporary, label))
        plan = make_plan(local_root, roots["old"], roots["new"])
        backup_dir = None
        if plan.backup:
            backup_dir = os.path.join(local_root, BACKUP_DIR, (now or datetime.today()).strftime("%Y%m%d%H%M%S"))
        log(f"入れ替えています(変更 {len(plan.replace)} 件、削除 {len(plan.remove)} 件、退避 {len(plan.backup)} 件)...")
        failed = apply_plan(plan, local_root, roots["new"], backup_dir or "")
    for relative, reason in failed:
        _logger.error(f"Failed to update '{relative}': {reason}")
    return Result(plan, backup_dir, failed)
