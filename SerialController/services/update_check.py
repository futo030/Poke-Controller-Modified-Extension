#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
更新の確認(GitHub の最新の Release が、手元のバージョンより新しいかを調べる)

画面(tkinter)には触れない。通信は Python の標準の機能で行うので、git も、追加のライブラリも要らない
(Windows では、証明書に Windows の一覧を使う)。
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from logging import getLogger, DEBUG, NullHandler

import Constant

_logger = getLogger(__name__)
_logger.addHandler(NullHandler())
_logger.setLevel(DEBUG)
_logger.propagate = True

REPOSITORY = "futo030/Poke-Controller-Modified-Extension"
LATEST_RELEASE_API = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
RELEASES_URL = f"https://github.com/{REPOSITORY}/releases"
# 応答を待つ秒数(起動のたびに確かめるので、つながらないときに長く待たせない)
TIMEOUT = 8

UP_TO_DATE = "0"
UPDATE_AVAILABLE = "1"
UNKNOWN = "-1"


class UpdateCheckError(Exception):
    """確認できなかった(通信できない、応答を読めない等)"""


@dataclass(frozen=True)
class Release:
    """公開されている版。tag: タグの名前(v0.2.1 など)、version: 比べるための形、url: Release のページ"""

    tag: str
    version: tuple
    url: str

    @property
    def zip_url(self) -> str:
        """その版のソースコードの ZIP"""
        return zip_url(self.tag)


def zip_url(tag: str) -> str:
    """タグの時点のソースコードの ZIP の URL"""
    return f"https://github.com/{REPOSITORY}/archive/refs/tags/{tag}.zip"


def parse_version(text: str) -> tuple:
    """「v0.2.1」「0.2.1」などを (0, 2, 1) にする。数字の並びでなければ ()"""
    found = re.fullmatch(r"\s*v?(\d+(?:\.\d+)*)\s*", text or "")
    return tuple(int(part) for part in found.group(1).split(".")) if found else ()


def current_version() -> tuple:
    """手元のバージョン"""
    return parse_version(Constant.VERSION)


def current_tag() -> str:
    """手元のバージョンに付く、タグの名前"""
    return f"v{Constant.VERSION}"


def fetch_latest_release(opener=urllib.request.urlopen) -> Release | None:
    """
    最新の Release を調べる(試作版 = Pre-release は、対象にならない)。Release が 1 つもなければ None。
    調べられなければ UpdateCheckError
    """
    request = urllib.request.Request(
        LATEST_RELEASE_API, headers={"Accept": "application/vnd.github+json", "User-Agent": "Poke-Controller-Modified-Extension"}
    )  # fmt: skip
    try:
        with opener(request, timeout=TIMEOUT) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise UpdateCheckError(f"GitHub returned {e.code}") from e
    except (OSError, ValueError) as e:
        raise UpdateCheckError(str(e)) from e
    tag = str(data.get("tag_name", "")) if isinstance(data, dict) else ""
    version = parse_version(tag)
    if not version:
        raise UpdateCheckError(f"Unexpected tag name: {tag!r}")
    return Release(tag, version, str(data.get("html_url") or RELEASES_URL))


def find_update(opener=urllib.request.urlopen) -> Release | None:
    """手元より新しい Release があれば、それを返す(なければ None)。調べられなければ UpdateCheckError"""
    release = fetch_latest_release(opener)
    if release is None or release.version <= current_version():
        return None
    return release


def check(path: str | None = None) -> str:
    """
    更新があるかを確かめる。"0": 最新 / "1": 更新あり / "-1": 確認できない(通信できない等。理由はログに残す)
    path: 使っていない(以前の呼び出し方との互換のために残している)
    """
    try:
        release = find_update()
    except UpdateCheckError as e:
        _logger.warning(f"Update check failed: {e}")
        print("更新を確認できませんでした。")
        return UNKNOWN
    if release is None:
        print("最新の版です。")
        return UP_TO_DATE
    print(f"新しい版があります: {release.tag}")
    return UPDATE_AVAILABLE
