"""
利用者が足したライブラリの検出(uv の環境に移るときに、引き継ぐ候補を挙げる)

2 つの方法で調べる。どちらも、読むだけ(スクリプトは実行しない。何も入れない)。
- 今の環境に入っているものから、ほかのライブラリが必要とするもの・本体の分・道具を引く
- 利用者のスクリプト(Commands/PythonCommands)が import しているものを調べる
引き継ぐかは、呼び出し側が一覧を見せて、利用者に選んでもらう。
"""
from __future__ import annotations

import ast
import importlib.metadata
import os
import re
import sys
import tomllib
from dataclasses import dataclass, field

# 環境を作る道具(引き継がない)
TOOLS = frozenset({"pip", "setuptools", "wheel", "uv"})
# 以前は本体が必要としていたが、今は使っていないもの(引き継がない)
DROPPED = frozenset({"windows-capture-device-list"})
USER_REQUIREMENTS = "requirements-user.txt"
SCRIPTS_DIR = os.path.join("SerialController", "Commands", "PythonCommands")
APP_DIR = "SerialController"


@dataclass
class Candidate:
    """引き継ぐ候補。used_by は、import しているスクリプトのフォルダー(またはファイル)の名前"""

    name: str
    used_by: list = field(default_factory=list)

    @property
    def used_by_scripts(self) -> bool:
        return bool(self.used_by)


def normalize(name: str) -> str:
    """ライブラリの名前を、比べられる形にする(大文字と小文字、- と _ と . の違いをなくす)"""
    return re.sub(r"[-_.]+", "-", name).strip().lower()


def requirement_name(requirement: str) -> str:
    """「pynput>=1.7.7」「uvicorn[standard] ; extra == 'web'」などから、名前だけを取り出す"""
    return normalize(re.split(r"[<>=!~;\[( ]", requirement.strip(), maxsplit=1)[0])


def project_names(pyproject_path: str) -> set:
    """本体が必要とするライブラリの名前(pyproject.toml の必須の分と、任意の追加分。以前に必要としていたものも含める)"""
    with open(pyproject_path, "rb") as file:
        project = tomllib.load(file).get("project", {})
    requirements = list(project.get("dependencies", []))
    for extra in project.get("optional-dependencies", {}).values():
        requirements.extend(extra)
    return {requirement_name(requirement) for requirement in requirements} | DROPPED


def installed_requirements() -> dict:
    """今の環境に入っているライブラリ: 名前 -> それが必要とするライブラリの名前(任意の追加分は除く)"""
    installed = {}
    for distribution in importlib.metadata.distributions():
        name = distribution.metadata["Name"]
        if not name:
            continue
        requires = [text for text in (distribution.requires or []) if "extra ==" not in text]
        installed[normalize(name)] = {requirement_name(text) for text in requires}
    return installed


def not_required(installed: dict, project: set) -> list:
    """入っているもののうち、ほかのライブラリが必要としておらず、本体の分でも道具でもないもの"""
    required = set().union(*installed.values()) if installed else set()
    return sorted(name for name in installed if name not in required and name not in project and name not in TOOLS)


def imported_names(scripts_dir: str) -> dict:
    """スクリプトが import している名前(いちばん上の階層): 名前 -> 使っているフォルダー(またはファイル)の名前"""
    found = {}
    for folder, _, names in os.walk(scripts_dir):
        for name in names:
            if not name.endswith(".py"):
                continue
            path = os.path.join(folder, name)
            try:
                with open(path, encoding="utf-8-sig", errors="replace") as file:
                    tree = ast.parse(file.read())
            except (OSError, SyntaxError, ValueError):
                continue
            owner = os.path.relpath(path, scripts_dir).split(os.sep)[0]
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    tops = [alias.name.split(".")[0] for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    tops = [node.module.split(".")[0]]
                else:
                    continue
                for top in tops:
                    found.setdefault(top, set()).add(owner)
    return found


def local_names(app_dir: str) -> set:
    """本体のフォルダーの中にあるファイルとフォルダーの名前(import したときに、ライブラリではなく、これらが読まれる)"""
    names = set()
    for _, folders, files in os.walk(app_dir):
        names.update(folders)
        names.update(os.path.splitext(name)[0] for name in files if name.endswith(".py"))
    return names


def candidates(
    installed: dict, project: set, imported: dict, local: set, distributions_of: dict
) -> list:
    """
    引き継ぐ候補の一覧(スクリプトが使っているものが先。その中は名前の順)。
    distributions_of: import する名前 -> ライブラリの名前の一覧(importlib.metadata.packages_distributions() の形)
    """
    used = {}
    for top, owners in imported.items():
        if top in sys.stdlib_module_names or top in local:
            continue
        for name in {normalize(name) for name in distributions_of.get(top, [])}:
            if name in installed and name not in project and name not in TOOLS:
                used.setdefault(name, set()).update(owners)
    result = [Candidate(name, sorted(owners)) for name, owners in sorted(used.items())]
    result.extend(Candidate(name) for name in not_required(installed, project) if name not in used)
    return result


def detect(repository_dir: str) -> list:
    """今の Python の環境と、利用者のスクリプトから、引き継ぐ候補を挙げる"""
    return candidates(
        installed_requirements(),
        project_names(os.path.join(repository_dir, "pyproject.toml")),
        imported_names(os.path.join(repository_dir, SCRIPTS_DIR)),
        local_names(os.path.join(repository_dir, APP_DIR)),
        importlib.metadata.packages_distributions(),
    )


def remove_user_requirements(repository_dir: str, names: list) -> list:
    """requirements-user.txt から、指定した名前の行を取り除く。取り除いた名前(比べられる形)を返す"""
    path = os.path.join(repository_dir, USER_REQUIREMENTS)
    targets = {requirement_name(name) for name in names}
    try:
        with open(path, encoding="utf-8") as file:
            lines = file.read().splitlines()
    except OSError:
        return []
    kept, removed = [], []
    for line in lines:
        is_requirement = line.strip() and not line.lstrip().startswith("#")
        if is_requirement and requirement_name(line) in targets:
            removed.append(requirement_name(line))
        else:
            kept.append(line)
    if removed:
        with open(path, "w", encoding="utf-8", newline="\n") as file:
            file.write("".join(f"{line}\n" for line in kept))
    return removed


def write_user_requirements(repository_dir: str, names: list) -> str:
    """選ばれたライブラリの名前を、requirements-user.txt に書く(版は書かない。すでにある名前は残す)。ファイルの場所を返す"""
    path = os.path.join(repository_dir, USER_REQUIREMENTS)
    existing = []
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as file:
            existing = [line.strip() for line in file if line.strip() and not line.lstrip().startswith("#")]
    known = {requirement_name(line) for line in existing}
    added = [name for name in dict.fromkeys(normalize(name) for name in names) if name not in known]
    with open(path, "w", encoding="utf-8", newline="\n") as file:
        file.write("# 自分で足したライブラリ(.venv に入れるもの。1 行に 1 つ)\n")
        file.write("".join(f"{line}\n" for line in existing + added))
    return path
