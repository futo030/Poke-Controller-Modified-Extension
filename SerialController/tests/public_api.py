#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
スクリプトから使う関数・クラスの一覧(名前と引数)を集める。

スクリプトがそのまま動き続けるように、名前・引数の並び・省略時の値・ボタンなどの値を
記録(tests/data/public_api.json)と比べる(tests/test_public_api.py)。

- なくなった名前、変わった引数、省略できない引数の追加は、テストが失敗する
- 関数や、省略できる引数を足したときは、記録を作り直す

SerialController フォルダで実行する:
    python tests/public_api.py            記録との違いを表示する
    python tests/public_api.py --write    記録を作り直す(互換性がなくなる変更があるときは、作り直さない)
    python tests/public_api.py --write --force    互換性がなくなる変更を承知のうえで、作り直す
"""
from __future__ import annotations

import ast
import enum
import importlib
import io
import json
import os
import sys

SERIAL_CONTROLLER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RECORD_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "public_api.json")

# 対象のファイル。値は、対象にする名前(None は、"_" で始まらない名前のすべて)
FILES = {
    "Commands/CommandBase.py": None,
    "Commands/PythonCommandBase.py": None,
    "Commands/McuCommandBase.py": None,
    "Commands/Keys.py": None,
    "Commands/SwitchKeyboard.py": ["KEY"],
}

# 値も記録するファイル(ボタンやキーの値、スティックの向き)
VALUE_MODULES = {
    "Commands/Keys.py": "Commands.Keys",
    "Commands/SwitchKeyboard.py": "Commands.SwitchKeyboard",
}

_FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)


def _public(name: str) -> bool:
    return not name.startswith("_")


def _token(name: str, default) -> str:
    return name if default is None else f"{name}={ast.unparse(default)}"


def _parameters(node) -> list:
    """
    引数の一覧。デコレータを付けた関数も、書いてあるとおりの引数になる
    (実行時の情報では、デコレータの中の関数の引数になってしまう)
    """
    args = node.args
    positional = args.posonlyargs + args.args
    defaults = [None] * (len(positional) - len(args.defaults)) + list(args.defaults)
    tokens = []
    for index, (arg, default) in enumerate(zip(positional, defaults)):
        tokens.append(_token(arg.arg, default))
        if args.posonlyargs and index == len(args.posonlyargs) - 1:
            tokens.append("/")
    if args.vararg:
        tokens.append("*" + args.vararg.arg)
    elif args.kwonlyargs:
        tokens.append("*")
    for arg, default in zip(args.kwonlyargs, args.kw_defaults):
        tokens.append(_token(arg.arg, default))
    if args.kwarg:
        tokens.append("**" + args.kwarg.arg)
    return tokens


def _targets(statement) -> list:
    if isinstance(statement, ast.Assign):
        return statement.targets
    if isinstance(statement, ast.AnnAssign):
        return [statement.target]
    return []


def _assigned_names(statement) -> list:
    """代入文で作られる名前(`A = 1`、`A, B = 1, 2`)"""
    names = []
    for target in _targets(statement):
        # `Direction.UP = 値` の Direction のように、読むだけの名前は含めない
        names += [node.id for node in ast.walk(target) if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store)]
    return names


def _assigned_attributes(statement, owner: str | None = None) -> list:
    """`名前.属性 = 値` の形の代入の (名前, 属性)。owner を指定すると、その名前への代入だけ"""
    found = []
    for node in ast.walk(statement):
        if not (isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Store)):
            continue
        if isinstance(node.value, ast.Name) and owner in (None, node.value.id):
            found.append((node.value.id, node.attr))
    return found


def _class(node) -> dict:
    methods, attributes = {}, set()
    for item in node.body:
        if isinstance(item, _FUNCTIONS):
            if item.name == "__init__":
                methods[item.name] = _parameters(item)
                # self.keys のように、作ったときに持たせる変数
                attributes.update(attr for _, attr in _assigned_attributes(item, "self"))
            elif _public(item.name):
                methods[item.name] = _parameters(item)
        else:
            attributes.update(_assigned_names(item))
    return {
        "bases": [ast.unparse(base) for base in node.bases],
        "methods": dict(sorted(methods.items())),
        "attributes": sorted(name for name in attributes if _public(name)),
    }


def _module(path: str, only: list | None) -> dict:
    with io.open(os.path.join(SERIAL_CONTROLLER_DIR, path), encoding="utf-8") as file:
        tree = ast.parse(file.read())
    functions, classes, variables, added = {}, {}, set(), []
    for item in tree.body:
        if isinstance(item, _FUNCTIONS):
            functions[item.name] = _parameters(item)
        elif isinstance(item, ast.ClassDef):
            classes[item.name] = _class(item)
        else:
            variables.update(_assigned_names(item))
            # クラスの外で足している属性(Direction.UP = ... など)
            added += _assigned_attributes(item)
    for owner, name in added:
        if owner in classes and _public(name):
            classes[owner]["attributes"] = sorted(set(classes[owner]["attributes"]) | {name})

    def wanted(name):
        return _public(name) if only is None else name in only

    return {
        "functions": {name: value for name, value in sorted(functions.items()) if wanted(name)},
        "classes": {name: value for name, value in sorted(classes.items()) if wanted(name)},
        "variables": sorted(name for name in variables if wanted(name)),
    }


def _plain(value):
    return value if isinstance(value, (int, str)) else repr(value)


def _values(module_name: str, class_names: list) -> dict:
    """列挙の値(Button.A など)と、あらかじめ用意してあるスティックの向き(Direction.UP など)"""
    if SERIAL_CONTROLLER_DIR not in sys.path:
        sys.path.insert(0, SERIAL_CONTROLLER_DIR)
    module = importlib.import_module(module_name)
    values = {}
    for class_name in class_names:
        target = getattr(module, class_name)
        if issubclass(target, enum.Enum):
            found = {name: _plain(member.value) for name, member in target.__members__.items()}
        else:
            found = {
                name: [value.stick.name, value.x, value.y]
                for name, value in vars(target).items()
                if _public(name) and isinstance(value, target) and hasattr(value, "stick")
            }
        if found:
            values[f"{module_name}.{class_name}"] = found
    return values


def collect() -> dict:
    files, values = {}, {}
    for path, only in FILES.items():
        files[path] = _module(path, only)
        if path in VALUE_MODULES:
            values.update(_values(VALUE_MODULES[path], list(files[path]["classes"])))
    return {"files": files, "values": values}


# ---- 記録との比較 ----

_PARAMETER_LISTS = ("functions", "methods")
_NAME_LISTS = ("bases", "attributes", "variables")
_KINDS = _PARAMETER_LISTS + _NAME_LISTS + ("values",)


def _compare_parameters(recorded: list, current: list, path: str, broken: list, unrecorded: list):
    if recorded == current:
        return
    if current[: len(recorded)] != recorded:
        broken.append(f"引数が変わった: {path}: ({', '.join(recorded)}) -> ({', '.join(current)})")
        return
    required = [token for token in current[len(recorded):] if "=" not in token and not token.startswith("*")]
    if required:
        broken.append(f"省略できない引数が増えた: {path}: {', '.join(required)}")
    else:
        unrecorded.append(f"{path}: 引数 {', '.join(current[len(recorded):])}")


def compare(recorded, current, path: str = "", kind: str = "") -> tuple:
    """
    記録と今のコードを比べる。
    返り値は (互換性がなくなる違いの一覧, 記録にまだない追加の一覧)
    """
    broken, unrecorded = [], []
    if isinstance(recorded, dict) and isinstance(current, dict):
        for key, value in recorded.items():
            where = f"{path} > {key}" if path else key
            if key not in current:
                broken.append(f"なくなった: {where}")
                continue
            found = compare(value, current[key], where, key if key in _KINDS else kind)
            broken += found[0]
            unrecorded += found[1]
        unrecorded += [f"{path} > {key}" if path else key for key in current if key not in recorded]
    elif kind in _PARAMETER_LISTS:
        _compare_parameters(recorded, current, path, broken, unrecorded)
    elif kind in _NAME_LISTS:
        broken += [f"なくなった: {path} > {name}" for name in recorded if name not in current]
        unrecorded += [f"{path} > {name}" for name in current if name not in recorded]
    elif recorded != current:
        broken.append(f"値が変わった: {path}: {recorded!r} -> {current!r}")
    return broken, unrecorded


# ---- 記録の読み書き ----


def dumps(value, indent: int = 0) -> str:
    """辞書は1項目を1行に、引数や名前の一覧は1行にまとめる(差分を読みやすくする)"""
    if isinstance(value, dict) and value:
        pad = " " * indent
        rows = [f"{pad} {json.dumps(key, ensure_ascii=False)}: {dumps(item, indent + 1)}" for key, item in value.items()]
        return "{\n" + ",\n".join(rows) + "\n" + pad + "}"
    return json.dumps(value, ensure_ascii=False)


def load() -> dict | None:
    if not os.path.isfile(RECORD_FILE):
        return None
    with io.open(RECORD_FILE, encoding="utf-8") as file:
        return json.load(file)


def write(result: dict):
    os.makedirs(os.path.dirname(RECORD_FILE), exist_ok=True)
    with io.open(RECORD_FILE, "w", encoding="utf-8", newline="\n") as file:
        file.write(dumps(result) + "\n")


def main() -> int:
    current = collect()
    recorded = load()
    broken, unrecorded = compare(recorded, current) if recorded is not None else ([], [])
    for line in broken:
        print(line)
    if "--write" in sys.argv:
        if broken and "--force" not in sys.argv:
            print("スクリプトが動かなくなる変更があるため、記録を作り直していません(承知のうえで作り直すときは --force)")
            return 1
        write(current)
        print(f"wrote {RECORD_FILE}")
        return 0
    if recorded is None:
        print("記録がありません(--write で作ります)")
        return 1
    for line in unrecorded:
        print(f"記録にない: {line}")
    if not broken and not unrecorded:
        print("記録と同じです")
    return 1 if broken or unrecorded else 0


if __name__ == "__main__":
    sys.exit(main())
