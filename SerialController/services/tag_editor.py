#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
コマンドのタグ(クラスの TAGS)の読み取りと書き換え

タグは、コマンドのファイル(.py)の、クラスの中の `TAGS = ["タグ", ...]` に書いてある。
ここでは、その行だけを書き換える(ほかの行、改行コード、文字コードは変えない)。画面(tkinter)には触れない。

- 書き換えられるのは、TAGS が、文字だけを並べた一覧(リスト・タプル)か、1 つの文字のとき。TAGS がないクラスには、行を足す
- それ以外の書き方(変数や計算を使っているなど)は、書き換えない(read_source の editable が False。理由は reason)
- フォルダーの名前から付くタグ(@フォルダー名)は、ファイルには書かれていないので、対象にしない
- 読み取ったとき(read_source)と、ファイルの内容が変わっていたら、上書きしない(save_tags が TagEditError)
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from logging import getLogger, DEBUG, NullHandler
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from CommandLoader import CommandEntry

_logger = getLogger(__name__)
_logger.addHandler(NullHandler())
_logger.setLevel(DEBUG)
_logger.propagate = True

# フォルダーの名前から付くタグの、先頭の印
FOLDER_TAG_PREFIX = "@"
# TagEditError の種類
CHANGED = "changed"  # 読み取った後に、ファイルが書き換わっている
LOCKED = "locked"  # 書き込めない(ほかのアプリが開いている、読み取り専用など)
NOT_EDITABLE = "not_editable"  # 書き換えられない書き方、ファイルやクラスがない など

_NEWLINE = re.compile(r"\r\n|\r|\n")


class TagEditError(Exception):
    """タグを読み取れない、または書き込めない。kind: CHANGED / LOCKED / NOT_EDITABLE。文字にすると、利用者向けの理由"""

    def __init__(self, kind: str, message: str):
        """kind: 種類(CHANGED / LOCKED / NOT_EDITABLE)。message: 利用者に見せる理由"""
        super().__init__(message)
        self.kind = kind


@dataclass
class TagSource:
    """
    1 つのコマンド(クラス)の、ファイルに書いてあるタグの状態
    """

    file_path: str
    class_name: str
    # ファイルに書いてあるタグ(TAGS がないクラスは空。書き換えられない書き方のときも空)
    tags: list = field(default_factory=list)
    # 書き換えられるか。False のときは、reason に理由
    editable: bool = True
    reason: str = ""
    # 読み取ったときのファイルの内容の印(save_tags が、書き換わっていないかを確かめるのに使う)
    digest: str = ""


def split_entry_tags(entry: CommandEntry) -> tuple[list, list]:
    """
    一覧のコマンドのタグを、(ファイルに書いてあるタグ, フォルダーの名前から付いたタグ)に分ける。
    フォルダーのタグは、一覧の後ろに、フォルダーの深さの数だけ付いている
    """
    folders = max(len(entry.module_name.split(".")[2:]) - 1, 0) if entry.module_name else 0
    tags = list(entry.tags)
    if folders == 0:
        return tags, []
    return tags[:-folders], tags[-folders:]


def check_tag(text: str, current: list) -> tuple[str, str]:
    """
    入力されたタグを確かめる。戻り値: (前後の空白を除いたタグ, 使えない理由)。使えるときは、理由は空文字
    current: そのコマンドに、すでに付いているタグ(フォルダーのタグを含む)
    """
    tag = text.strip()
    if not tag:
        return tag, "タグを入力してください。"
    if any(ord(c) < 0x20 or c == "\x7f" for c in tag):
        return tag, "タグに、改行やタブは使えません。"
    if tag.startswith(FOLDER_TAG_PREFIX):
        return tag, f"「{FOLDER_TAG_PREFIX}」で始まるタグは、フォルダーの名前から自動で付くタグなので、足せません。"
    if tag in current:
        return tag, f"「{tag}」は、すでに付いています。"
    return tag, ""


def check_new_name(old: str, new: str) -> tuple[str, str]:
    """
    タグの名前の一括変更で、新しい名前を確かめる。戻り値: (前後の空白を除いた名前, 使えない理由)。使えるときは、理由は空文字
    old: 変える前のタグ。new: 入力された、新しい名前
    """
    tag, error = check_tag(new, [])
    if error:
        return tag, "新しい名前を入力してください。" if not tag else error
    if tag == old:
        return tag, "今と同じ名前です。"
    return tag, ""


def replace_tag(tags: list, old: str, new: str | None = None) -> list:
    """
    タグの一覧の中の old を、new に置き換えた一覧を返す(new が None なら、取り除く)。old がなければ、そのまま。
    new がすでにある場合は、old を取り除くだけにする(同じタグが 2 つにならないように、1 つにまとめる)
    """
    if old not in tags:
        return list(tags)
    if new is None or new in tags:
        return [tag for tag in tags if tag != old]
    return [new if tag == old else tag for tag in tags]


def _digest(data: bytes) -> str:
    """ファイルの内容の印(内容が同じなら、同じ文字になる)"""
    return hashlib.sha1(data).hexdigest()


def _read(file_path: str) -> tuple[bytes, str]:
    """ファイルを読んで、(内容, 文字にしたもの)を返す。読めない・UTF-8 でないときは TagEditError"""
    try:
        with open(file_path, "rb") as file:
            data = file.read()
    except OSError as e:
        raise TagEditError(NOT_EDITABLE, f"ファイルを読めません({e.strerror or e})。") from e
    try:
        return data, data.decode("utf-8")
    except UnicodeDecodeError as e:
        raise TagEditError(NOT_EDITABLE, "ファイルの文字コードが UTF-8 ではないため、編集できません。") from e


def _parse(text: str, file_path: str) -> ast.Module:
    """ソースを解析する。文法の誤りがあるときは TagEditError"""
    try:
        return ast.parse(text, filename=file_path)
    except (SyntaxError, ValueError) as e:
        raise TagEditError(NOT_EDITABLE, f"ファイルに文法の誤りがあるため、編集できません({e})。") from e


def _find_class(tree: ast.Module, class_name: str) -> ast.ClassDef | None:
    """ファイルの直下にある、その名前のクラス(同じ名前が複数あるときは、最後のもの。なければ None)"""
    found = None
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            found = node
    return found


def _assignments(node: ast.ClassDef, name: str) -> list:
    """クラスの直下で、name に代入している文(`名前 = 値` と `名前: 型 = 値`)"""
    found = []
    for stmt in node.body:
        if isinstance(stmt, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in stmt.targets):
            found.append(stmt)
        elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name) and stmt.target.id == name:
            found.append(stmt)
    return found


def _literal_tags(value: ast.expr | None) -> list | None:
    """TAGS の値が、文字だけの一覧(または 1 つの文字)なら、そのタグの一覧。そうでなければ None"""
    if isinstance(value, ast.Constant) and isinstance(value.value, str):
        return [value.value]
    if isinstance(value, (ast.List, ast.Tuple)):
        if all(isinstance(e, ast.Constant) and isinstance(e.value, str) for e in value.elts):
            return [e.value for e in value.elts]
    return None


def _inspect(node: ast.ClassDef) -> tuple[list, str, ast.stmt | None]:
    """
    クラスの TAGS を調べる。戻り値: (タグ, 書き換えられない理由(書き換えられるなら空文字), TAGS の文(なければ None))
    """
    statements = _assignments(node, "TAGS")
    if not statements:
        if node.body[0].lineno == node.lineno:
            return [], "クラスの中身が、class の行に続けて書かれているため、編集できません。", None
        return [], "", None
    if len(statements) > 1:
        return [], "TAGS が 2 か所以上に書かれているため、編集できません。", statements[0]
    statement = statements[0]
    if isinstance(statement, ast.Assign) and len(statement.targets) != 1:
        return [], "TAGS が、ほかの変数と一緒に代入されているため、編集できません。", statement
    tags = _literal_tags(statement.value)
    if tags is None:
        return [], "TAGS が、文字だけを並べた一覧ではない(変数や計算を使っている)ため、編集できません。", statement
    return tags, "", statement


def read_source(file_path: str, class_name: str) -> TagSource:
    """
    コマンドのファイルから、クラスのタグの状態を読み取る。
    読めない・書き換えられないときも、例外にせず、editable が False の TagSource を返す(理由は reason)
    """
    source = TagSource(file_path=file_path, class_name=class_name)
    if not file_path.lower().endswith(".py"):
        source.editable, source.reason = False, "このコマンドのタグは、ファイルに書かれていないため、編集できません。"
        return source
    try:
        data, text = _read(file_path)
        source.digest = _digest(data)
        node = _find_class(_parse(text, file_path), class_name)
        if node is None:
            raise TagEditError(NOT_EDITABLE, f"ファイルに、クラス {class_name} がありません。")
    except TagEditError as e:
        source.editable, source.reason = False, str(e)
        return source
    source.tags, source.reason, _ = _inspect(node)
    source.editable = not source.reason
    return source


def format_tags(tags: list) -> str:
    """タグの一覧を、ファイルに書く形(`["a", "b"]`)にする"""
    return "[" + ", ".join(json.dumps(str(tag), ensure_ascii=False) for tag in tags) + "]"


def _offset(lines: list, starts: list, lineno: int, column: int) -> int:
    """ast の位置(行は 1 始まり、列は UTF-8 のバイト数)を、文字にしたソースの中の位置にする"""
    line = lines[lineno - 1]
    return starts[lineno - 1] + len(line.encode("utf-8")[:column].decode("utf-8"))


def _replacement(text: str, node: ast.ClassDef, tags: list) -> tuple[int, int, str] | None:
    """
    クラスのタグを tags にするための、書き換え(始まりの位置, 終わりの位置, 入れる文字)を返す。変える所がなければ None。
    書き換えられないクラスのときは TagEditError
    """
    current, reason, statement = _inspect(node)
    if reason:
        raise TagEditError(NOT_EDITABLE, reason)
    if statement is None and not tags:
        return None
    if statement is not None and current == list(tags):
        return None
    lines, starts, position = [], [], 0
    for match in _NEWLINE.finditer(text):
        lines.append(text[position:match.start()])
        starts.append(position)
        position = match.end()
    lines.append(text[position:])
    starts.append(position)
    if statement is not None:
        value = statement.value
        start = _offset(lines, starts, value.lineno, value.col_offset)
        end = _offset(lines, starts, value.end_lineno, value.end_col_offset)
        # かっこで囲んだ値(`TAGS = ("a", "b")` など)は、かっこも含めて置き換える
        before = text[_offset(lines, starts, statement.lineno, statement.col_offset):start]
        if before.rstrip().endswith("("):
            start = text.rindex("(", 0, start)
            end = text.index(")", end) + 1
        return start, end, format_tags(tags)
    # TAGS がないクラス: NAME の行の下(なければ、説明の下か、中身の先頭)に、行を足す
    names = _assignments(node, "NAME")
    first = node.body[0]
    is_docstring = isinstance(first, ast.Expr) and isinstance(getattr(first, "value", None), ast.Constant) \
        and isinstance(first.value.value, str)
    anchor = names[-1] if names else (first if is_docstring and len(node.body) > 1 else None)
    indent = lines[first.lineno - 1][: len(lines[first.lineno - 1]) - len(lines[first.lineno - 1].lstrip())]
    newline_match = _NEWLINE.search(text)
    newline = newline_match.group(0) if newline_match else "\n"
    line = f"{indent}TAGS = {format_tags(tags)}"
    if anchor is None:
        # 中身の先頭の行の前に足す
        position = starts[first.lineno - 1]
        return position, position, line + newline
    # anchor の文の最後の行の、行末に続けて足す
    end_line = anchor.end_lineno - 1
    position = starts[end_line] + len(lines[end_line])
    return position, position, newline + line


def build_text(text: str, file_path: str, changes: dict) -> str:
    """
    ソース text の、クラスのタグを書き換えた文字を返す(ファイルには触れない)。
    changes: クラスの名前 -> タグの一覧。書き換えられないクラスがあるときは TagEditError
    """
    tree = _parse(text, file_path)
    edits = []
    for class_name, tags in changes.items():
        node = _find_class(tree, class_name)
        if node is None:
            raise TagEditError(NOT_EDITABLE, f"ファイルに、クラス {class_name} がありません。")
        edit = _replacement(text, node, [str(tag) for tag in tags])
        if edit is not None:
            edits.append(edit)
    # 後ろから書き換える(前の位置がずれないようにする)
    for start, end, value in sorted(edits, reverse=True):
        text = text[:start] + value + text[end:]
    if edits:
        # 書き換えた結果を読み直して、意図したタグになっていることを確かめる(なっていなければ、書き込まない)
        tree = _parse(text, file_path)
        for class_name, tags in changes.items():
            node = _find_class(tree, class_name)
            if node is None or _inspect(node)[0] != [str(tag) for tag in tags]:
                raise TagEditError(NOT_EDITABLE, "この書き方の TAGS は、安全に書き換えられないため、編集できません。")
    return text


def save_tags(file_path: str, digest: str, changes: dict) -> str:
    """
    ファイルの、クラスのタグを書き換えて保存する(同じファイルのクラスは、まとめて 1 回で書く)。
    digest: 読み取ったとき(read_source)の印。今のファイルの内容と違っていたら、上書きせずに TagEditError(CHANGED)
    changes: クラスの名前 -> タグの一覧
    戻り値: 保存した後のファイルの印。書き込めないときは TagEditError(LOCKED)
    """
    try:
        data, text = _read(file_path)
    except TagEditError as e:
        if isinstance(e.__cause__, OSError) and os.path.exists(file_path):
            # ファイルはあるのに読めない: ほかのアプリが、読み書きできない形で開いている
            raise TagEditError(LOCKED, f"{e} ほかのアプリで開いている場合は閉じてから、もう一度保存してください。") from e
        raise
    if _digest(data) != digest:
        raise TagEditError(CHANGED, "この画面を開いた後に、ファイルが書き換えられています。上書きしませんでした。")
    new_data = build_text(text, file_path, changes).encode("utf-8")
    if new_data == data:
        return digest
    try:
        with open(file_path, "r+b") as file:
            file.write(new_data)
            file.truncate()
    except OSError as e:
        raise TagEditError(
            LOCKED,
            f"ファイルに書き込めません({e.strerror or e})。ほかのアプリで開いている場合は閉じて、"
            "読み取り専用の場合は解除してから、もう一度保存してください。",
        ) from e
    _logger.info(f"Tags saved: {os.path.basename(file_path)} {sorted(changes)}")
    return _digest(new_data)
