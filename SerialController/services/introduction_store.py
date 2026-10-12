#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
機能紹介の文章の読み込みと、「今後は表示しない」の保存

- 紹介文は assets/introduction/introduction.md に書く。「# 見出し」で1ページが始まる
- 保存先は profiles/introduction.json(全プロファイル共通)

画面(tkinter)には触れない。表示は Introduction.py(tkinter 版)と、Web ブラウザ版の画面が行う
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field

import Profile

INTRODUCTION_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "introduction")
INTRODUCTION_FILE = "introduction.md"
STATE_FILE = "introduction.json"
# 画面の種類: これまでのウィンドウの画面(tkinter 版)と、Web ブラウザ版。紹介文と「今後は表示しない」を、別々に持つ
TK = "tk"
WEB = "web"
# 画面の種類 -> (紹介文のファイル, 「今後は表示しない」を保存する項目の名前)
KINDS = {TK: (INTRODUCTION_FILE, "hidden_revision"), WEB: ("introduction_web.md", "hidden_revision_web")}


@dataclass
class Page:
    """紹介文の 1 ページ(見出し、画像のファイル名(無ければ None)、文章)"""

    title: str
    image: str | None = None
    # (箇条書きか, 文章) の並び
    lines: list[tuple[bool, str]] = field(default_factory=list)


def load_pages(kind: str = TK) -> list[Page]:
    """
    紹介文のファイルを読み、ページの並びにする(ファイルがない場合は空)
    """
    try:
        with open(os.path.join(INTRODUCTION_DIR, KINDS[kind][0]), encoding="utf-8-sig") as file:
            lines = [line.rstrip() for line in file]
    except OSError:
        return []
    pages = []
    for line in lines:
        text = line.strip()
        if text.startswith("# "):
            pages.append(Page(text[2:].strip()))
        elif text == "" or not pages:
            continue
        elif text.startswith("![") and text.endswith(")") and "](" in text:
            pages[-1].image = text[text.index("](") + 2 : -1].strip()
        elif text.startswith("- "):
            pages[-1].lines.append((True, text[2:].strip()))
        else:
            pages[-1].lines.append((False, text))
    return pages


def content_revision(kind: str = TK) -> str:
    """
    紹介文の内容(文章と、文章から使っている画像)の識別値。内容が変わると値が変わる
    """
    digest = hashlib.sha1()
    text_file = KINDS[kind][0]
    names = [text_file] + sorted({page.image for page in load_pages(kind) if page.image})
    for name in names:
        digest.update(name.encode("utf-8"))
        try:
            with open(os.path.join(INTRODUCTION_DIR, name), "rb") as file:
                # 改行コードの違い(取得のしかたによる)では、値が変わらないようにする
                data = file.read()
                digest.update(data.replace(b"\r\n", b"\n") if name == text_file else data)
        except OSError:
            pass
    return digest.hexdigest()


def _state_path() -> str:
    """「今後は表示しない」を保存するファイルの場所"""
    return os.path.join(Profile.PROFILES_DIR, STATE_FILE)


def _read_state() -> dict:
    """保存した内容を読む(ファイルが無い・読めない・形が違う場合は、空の dict)"""
    try:
        with open(_state_path(), encoding="utf-8") as file:
            state = json.load(file)
    except (OSError, ValueError):
        return {}
    return state if isinstance(state, dict) else {}


def hidden_revision(kind: str = TK) -> str | None:
    """
    「今後は表示しない」でOKを押したときの紹介文の識別値(押していない場合はNone)
    """
    value = _read_state().get(KINDS[kind][1])
    return value if isinstance(value, str) else None


def set_hidden(hidden: bool, kind: str = TK) -> None:
    """
    今の紹介文を、今後は表示しない(hidden=False なら、また表示する)設定にして保存する
    (もう一方の画面の種類の設定は、そのまま残す)
    """
    if Profile.is_read_only():
        # 同じプロファイルで2つ目以降に起動した場合は保存しない
        return
    os.makedirs(Profile.PROFILES_DIR, exist_ok=True)
    state = _read_state()
    state[KINDS[kind][1]] = content_revision(kind) if hidden else None
    with open(_state_path(), "w", encoding="utf-8") as file:
        json.dump(state, file, indent=2)


def should_show_at_startup(kind: str = TK) -> bool:
    """
    起動時に表示するか(紹介文があり、今の内容を「今後は表示しない」にしていない)
    """
    return len(load_pages(kind)) > 0 and hidden_revision(kind) != content_revision(kind)
