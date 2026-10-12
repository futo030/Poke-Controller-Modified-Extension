"""
今の環境(.venv)に入っているライブラリの一覧(PokeConExtension_ListLibraries.bat から表示する)

本体が使うもの / 利用者が足したもの(requirements-user.txt)/ そのほか(それらが必要とするもの)に分けて、版と一緒に並べる。
"""
from __future__ import annotations

import importlib.metadata
import os
import sys
import tomllib

from bootstrap import environment
from bootstrap.added_libraries import normalize, requirement_name


def installed_versions() -> dict:
    """今の Python の環境に入っているライブラリ: 名前(比べられる形)-> (表示する名前, 版)"""
    found = {}
    for distribution in importlib.metadata.distributions():
        name = distribution.metadata["Name"]
        if name:
            found[normalize(name)] = (name, distribution.version)
    return found


def project_requirements(root: str) -> list:
    """本体が使うライブラリの名前(pyproject.toml に書いてある順)"""
    try:
        with open(os.path.join(root, "pyproject.toml"), "rb") as file:
            dependencies = tomllib.load(file).get("project", {}).get("dependencies", [])
    except (OSError, ValueError):
        return []
    return [requirement_name(requirement) for requirement in dependencies]


def sections(project: list, user: list, installed: dict) -> list:
    """
    表示する内容: [(見出し, [(名前, 版 または None)])]。None は、入っていないもの。
    project / user: 本体の分 / 利用者が足した分の名前(比べられる形)、installed: installed_versions() の形
    """

    def rows(names: list) -> list:
        return [(installed[name][0], installed[name][1]) if name in installed else (name, None) for name in names]

    user = [name for name in dict.fromkeys(user) if name not in project]
    listed = set(project) | set(user)
    others = sorted((name for name in installed if name not in listed), key=lambda name: installed[name][0].lower())
    return [
        ("本体が使うライブラリ", rows(project)),
        ("自分で足したライブラリ(requirements-user.txt)", rows(user)),
        ("そのほか(上のライブラリが必要とするものなど)", rows(others)),
    ]


def format_report(python: str, place: str, parts: list) -> str:
    """一覧を、表示用の文章にする"""
    width = max([len(name) for _, rows in parts for name, _ in rows] + [1])
    lines = [f"Python {python}", f"環境: {place}", ""]
    for title, rows in parts:
        lines.append(f"■ {title}: {len(rows)} 個")
        if not rows:
            lines.append("  (ありません)")
        for name, version in rows:
            lines.append(f"  {name.ljust(width)}  {version if version is not None else '(入っていません)'}")
        lines.append("")
    lines.append("ライブラリを足すには、PokeConExtension_AddLibrary.bat を実行します。")
    return "\n".join(lines)


def report(root: str) -> str:
    """今の環境の、ライブラリの一覧の文章"""
    user = [requirement_name(line) for line in environment.user_requirements(root)]
    parts = sections(project_requirements(root), user, installed_versions())
    return format_report(sys.version.split()[0], sys.prefix, parts)
