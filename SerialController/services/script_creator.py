#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
新しいスクリプト(Python コマンド)のひな形を作る(メニューの ツール > 新しい自動化スクリプトをつくる)

入力された内容(スクリプト名・ファイル名・格納場所・BridgeFunctions を使うか・画像の保存先)を確かめ、
Commands/PythonCommands の中に、そのまま実行できる .py ファイルを作る。画面(tkinter)には触れない。

- すでにあるファイルは、上書きしない
- 格納場所のフォルダーと、画像の保存先のフォルダーは、なければ作る
- 画像の保存先は、Template の中か、スクリプトの格納場所の中(BridgeFunctions を使う場合だけ選べる)
- 格納場所に、README.md と License.txt のひな形も作る(すでにあれば、作らない)。
  どちらも、bridge_functions フォルダーのものを手本にした形(License.txt は、商用利用を禁止する内容。MIT ではない)
- 作るファイルの形:
    画像の保存先あり、または BridgeFunctions を使う → ImageProcPythonCommand(画像認識を使えるコマンド)
    どちらでもない                                  → PythonCommand
"""
from __future__ import annotations

import datetime
import json
import os
import platform
import re
from dataclasses import dataclass, field
from logging import getLogger, DEBUG, NullHandler

_logger = getLogger(__name__)
_logger.addHandler(NullHandler())
_logger.setLevel(DEBUG)
_logger.propagate = True

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# スクリプトを置くフォルダーと、テンプレート画像のフォルダー(SerialController から見た場所)
COMMANDS_PATH = ("Commands", "PythonCommands")
TEMPLATE_PATH = ("Template",)
# 橋渡し関数(BridgeFunctions)のファイル(スクリプトを置くフォルダーから見た場所)と、import の書き方
BRIDGE_FILE = ("bridge_functions", "bridge_functions.py")
BRIDGE_IMPORT = "from Commands.PythonCommands.bridge_functions.bridge_functions import BridgeFunctions"
# 画像の保存先の種類: Template フォルダーの中 / スクリプトの格納場所の中(BridgeFunctions を使う場合だけ)
IN_TEMPLATE = "template"
IN_SCRIPT_FOLDER = "script"
# 格納場所に一緒に作る、説明とライセンスのファイル
README_NAME = "README.md"
LICENSE_NAME = "License.txt"
# 作成者の名前が入力されなかったときに、作るファイルに入れておく文字(利用者が、後で書き換える)
AUTHOR_PLACEHOLDER = "(名前)"
# 橋渡し関数の名前と作成者(橋渡し関数を使うスクリプトの README に、使っている旨を書く)
BRIDGE_CREDIT = "Poke-Controller Modified/Extension 橋渡し関数(作成者：フウ(@dragonite303))"
# 前に入力した作成者名を覚えておくファイル(SerialController から見た場所。プロファイルに関係なく、共通)
SETTING_PATH = ("profiles", "script_creator.json")
NAME_MAX_LENGTH = 100
FILE_NAME_MAX_LENGTH = 64
_FILE_NAME_PATTERN = re.compile(r"[A-Za-z0-9_-]+")
# フォルダーの名前に使えない文字(Windows)。「.」は、Python がフォルダーの区切りとして扱うので、使えないことにする
_FOLDER_FORBIDDEN = set('\\/:*?"<>|.')
# Windows でファイル・フォルダーの名前に使えない名前
_RESERVED_NAMES = {"con", "prn", "aux", "nul"} | {f"{name}{num}" for name in ("com", "lpt") for num in range(1, 10)}
# 一覧に出さないフォルダー(スクリプトを置く所ではないもの)
_HIDDEN_FOLDERS = {"__pycache__", "bridge_functions"}


class ScriptCreateError(Exception):
    """スクリプトを作れない(入力の誤り、同じ名前のファイルがある、書き込めないなど)。文字にすると、利用者向けの理由"""


@dataclass
class ScriptSpec:
    """
    作るスクリプトの内容(入力されたもの。前後の空白は、normalized で取り除く)
    """

    name: str  # スクリプト名(一覧に表示する名前。日本語可)
    file_name: str  # ファイル名(拡張子なし。半角の英数字と - _)
    folder: str = ""  # 格納場所(Commands/PythonCommands の中のフォルダー。空なら直下。"A/B" のように重ねられる)
    use_bridge: bool = False  # 橋渡し関数(BridgeFunctions)を使うか
    template_folder: str = ""  # 画像の保存先のフォルダーの名前(空なら、画像を使わない)
    # 画像の保存先の種類(IN_TEMPLATE: Template の中 / IN_SCRIPT_FOLDER: スクリプトの格納場所の中)
    template_location: str = IN_TEMPLATE
    author: str = ""  # 作成者の名前(スクリプト・README.md・License.txt に書く。空なら「(名前)」と書いておく)

    def author_name(self) -> str:
        """作るファイルに書く、作成者の名前(入力がなければ、後で書き換えるための「(名前)」)"""
        return self.author.strip() or AUTHOR_PLACEHOLDER

    def normalized(self) -> ScriptSpec:
        """前後の空白を取り除き、フォルダーの区切りを「/」にそろえたもの"""
        return ScriptSpec(
            name=self.name.strip(),
            file_name=self.file_name.strip(),
            folder=normalize_folder(self.folder),
            use_bridge=bool(self.use_bridge),
            template_folder=normalize_folder(self.template_folder),
            template_location=self.template_location,
            author=self.author.strip(),
        )


@dataclass
class ScriptResult:
    """作った結果"""

    path: str  # 作ったファイル(絶対パス)
    command_name: str  # コマンドの一覧に表示される名前("スクリプト名 (フォルダー/ファイル名)")
    class_name: str
    created_folders: list = field(default_factory=list)  # 新しく作ったフォルダー(絶対パス)
    created_files: list = field(default_factory=list)  # 一緒に作ったファイル(README.md / License.txt。絶対パス)
    skipped_files: list = field(default_factory=list)  # すでにあったので作らなかったファイル(絶対パス)


def load_author(base_dir: str = BASE_DIR) -> str:
    """前に入力した作成者名を読む(覚えていない・読めないときは、空文字)"""
    try:
        with open(os.path.join(base_dir, *SETTING_PATH), encoding="utf-8") as file:
            author = json.load(file).get("author", "")
        return author if isinstance(author, str) and not check_author(author) else ""
    except (OSError, ValueError, AttributeError):
        return ""


def save_author(author: str, base_dir: str = BASE_DIR) -> None:
    """作成者名を覚える(次に画面を開いたときの、初めの値にする)。書けないときは、何もしない"""
    path = os.path.join(base_dir, *SETTING_PATH)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as file:
            json.dump({"author": author.strip()}, file, ensure_ascii=False, indent=2)
    except OSError as e:
        _logger.warning(f"Failed to save the author name: {e}")


def normalize_folder(text: str) -> str:
    """フォルダーの指定を、「/」で区切った形にそろえる(前後の空白と区切り、重なった区切りは取り除く)"""
    parts = [part.strip() for part in text.replace("\\", "/").split("/")]
    return "/".join(part for part in parts if part)


def check_name(name: str) -> str:
    """スクリプト名を確かめる。使えない理由を返す(使えるなら空文字)"""
    if not name:
        return "スクリプト名を入力してください。"
    if any(ord(c) < 0x20 or c == "\x7f" for c in name):
        return "スクリプト名に、改行やタブは使えません。"
    if len(name) > NAME_MAX_LENGTH:
        return f"スクリプト名は {NAME_MAX_LENGTH} 文字以内にしてください。"
    return ""


def check_author(author: str) -> str:
    """作成者の名前を確かめる(空でもよい)。使えない理由を返す(使えるなら空文字)"""
    if any(ord(c) < 0x20 or c == "\x7f" for c in author):
        return "作成者名に、改行やタブは使えません。"
    if len(author) > NAME_MAX_LENGTH:
        return f"作成者名は {NAME_MAX_LENGTH} 文字以内にしてください。"
    return ""


def check_file_name(file_name: str) -> str:
    """ファイル名(拡張子なし)を確かめる。使えない理由を返す(使えるなら空文字)"""
    if not file_name:
        return "ファイル名を入力してください。"
    if file_name.lower().endswith(".py"):
        return "ファイル名に「.py」は付けないでください(自動で付きます)。"
    if _FILE_NAME_PATTERN.fullmatch(file_name) is None:
        return "ファイル名に使えるのは、半角の英数字と「-」「_」だけです。"
    if len(file_name) > FILE_NAME_MAX_LENGTH:
        return f"ファイル名は {FILE_NAME_MAX_LENGTH} 文字以内にしてください。"
    if file_name.lower() in _RESERVED_NAMES:
        return f"「{file_name}」は、Windows でファイル名に使えません。別の名前にしてください。"
    if file_name == "__init__":
        return "「__init__」は、ファイル名に使えません。"
    return ""


def check_folder(folder: str, label: str) -> str:
    """
    フォルダーの指定("A/B" の形。空は、指定なし)を確かめる。使えない理由を返す(使えるなら空文字)
    label: 理由の文に使う、項目の名前
    """
    for part in folder.split("/") if folder else []:
        if any(c in _FOLDER_FORBIDDEN or ord(c) < 0x20 for c in part):
            return f"{label}のフォルダー名に、次の文字は使えません: \\ / : * ? \" < > | ."
        if part.lower() in _RESERVED_NAMES:
            return f"「{part}」は、Windows でフォルダー名に使えません。別の名前にしてください。"
    return ""


def _relative(path: str, base_dir: str) -> str:
    """base_dir から見た場所を、「/」で区切って返す(利用者に見せる文に使う)"""
    return os.path.relpath(path, base_dir).replace(os.sep, "/")


def check_spec(spec: ScriptSpec, base_dir: str = BASE_DIR) -> str:
    """
    入力の全体を確かめる(spec は normalized のもの)。作れない理由を返す(作れるなら空文字)
    """
    error = (
        check_name(spec.name)
        or check_author(spec.author)
        or check_file_name(spec.file_name)
        or check_folder(spec.folder, "格納場所")
        or check_folder(spec.template_folder, "画像保存先")
    )
    if error:
        return error
    if spec.template_location not in (IN_TEMPLATE, IN_SCRIPT_FOLDER):
        return "画像保存先の種類が正しくありません。"
    if spec.template_location == IN_SCRIPT_FOLDER and spec.template_folder and not spec.use_bridge:
        return "画像保存先をスクリプト格納場所の中にできるのは、BridgeFunctions を使用する場合だけです。"
    if spec.folder.split("/")[0] in _HIDDEN_FOLDERS:
        return f"「{spec.folder.split('/')[0]}」は、スクリプトの格納場所に使えません。"
    path = script_path(spec, base_dir)
    if os.path.exists(path):
        return f"同じ名前のファイルが、すでにあります: {_relative(path, base_dir)}"
    for folder in (os.path.dirname(path), template_dir(spec, base_dir)):
        # フォルダーにしたい場所に、同じ名前のファイルがある
        current = folder
        while current and len(current) > len(base_dir):
            if os.path.isfile(current):
                return f"フォルダーにしたい場所に、同じ名前のファイルがあります: {_relative(current, base_dir)}"
            current = os.path.dirname(current)
    if spec.use_bridge and not bridge_available(base_dir):
        return (
            "BridgeFunctions(Commands/PythonCommands/bridge_functions/bridge_functions.py)がありません。"
            "「使用しない」にするか、bridge_functions フォルダーを置いてください。"
        )
    return ""


def script_path(spec: ScriptSpec, base_dir: str = BASE_DIR) -> str:
    """作るファイルの場所(絶対パス)"""
    return os.path.join(base_dir, *COMMANDS_PATH, *(spec.folder.split("/") if spec.folder else []), spec.file_name + ".py")


def template_dir(spec: ScriptSpec, base_dir: str = BASE_DIR) -> str:
    """画像の保存先のフォルダー(絶対パス。指定がなければ空文字)"""
    if not spec.template_folder:
        return ""
    if spec.template_location == IN_SCRIPT_FOLDER:
        return os.path.join(os.path.dirname(script_path(spec, base_dir)), *spec.template_folder.split("/"))
    return os.path.join(base_dir, *TEMPLATE_PATH, *spec.template_folder.split("/"))


def preview_lines(spec: ScriptSpec, base_dir: str = BASE_DIR) -> list:
    """
    入力の途中で表示する、作るファイルの場所(と、新しく作るフォルダー、一緒に作るファイル)の文の一覧を返す
    (spec は normalized のもの。ファイル名か格納場所が、まだ正しくないときは、空)
    """
    if not spec.file_name or check_file_name(spec.file_name) or check_folder(spec.folder, ""):
        return []
    path = script_path(spec, base_dir)
    lines = ["作るファイル: " + _relative(path, base_dir)]
    template = template_dir(spec, base_dir)
    if template and not check_folder(spec.template_folder, ""):
        state = "" if os.path.isdir(template) else "(新しく作ります)"
        lines.append("画像のフォルダー: " + _relative(template, base_dir) + state)
    # 一緒に作る、説明とライセンスのひな形(すでにあるものは、作らない)
    folder = os.path.dirname(path)
    extras = [name for name in (README_NAME, LICENSE_NAME) if not os.path.exists(os.path.join(folder, name))]
    if extras:
        lines.append("一緒に作るファイル: " + "、".join(extras) + "(スクリプトと同じフォルダー)")
    else:
        lines.append("README.md と License.txt は、すでにあるので、作りません")
    return lines


def bridge_available(base_dir: str = BASE_DIR) -> bool:
    """橋渡し関数(BridgeFunctions)のファイルがあるか"""
    return os.path.isfile(os.path.join(base_dir, *COMMANDS_PATH, *BRIDGE_FILE))


def command_name(spec: ScriptSpec) -> str:
    """コマンドの一覧に表示される名前("スクリプト名 (フォルダー/ファイル名)")"""
    return f"{spec.name} ({'/'.join(part for part in (spec.folder, spec.file_name) if part)})"


def class_name_for(file_name: str) -> str:
    """
    ファイル名から、クラスの名前を作る(「-」「_」で区切って、それぞれの先頭を大文字にしてつなぐ。
    数字で始まる場合は、前に Command を付ける)
    """
    parts = [part for part in re.split(r"[-_]+", file_name) if part]
    name = "".join(part[0].upper() + part[1:] for part in parts)
    if not name or not (name[0].isalpha() and name[0].isascii()):
        name = "Command" + name
    return name


def list_folders(root: str, hidden: set | None = None) -> list:
    """root の中のフォルダーを、"A/B" の形で、名前の順に返す(root がなければ空。「.」や「_」で始まるものと hidden は除く)"""
    hidden = hidden or set()
    found = []

    def walk(folder: str, prefix: str) -> None:
        """folder の中のフォルダーを、prefix を付けて found に足す(その中も調べる)"""
        try:
            names = sorted(os.listdir(folder), key=str.lower)
        except OSError:
            return
        for name in names:
            path = os.path.join(folder, name)
            if name.startswith((".", "_")) or name in hidden or not os.path.isdir(path):
                continue
            found.append(prefix + name)
            walk(path, prefix + name + "/")

    walk(root, "")
    return found


def script_folders(base_dir: str = BASE_DIR) -> list:
    """今ある、スクリプトの格納場所のフォルダー(Commands/PythonCommands の中)"""
    return list_folders(os.path.join(base_dir, *COMMANDS_PATH), _HIDDEN_FOLDERS)


def template_folders(base_dir: str = BASE_DIR) -> list:
    """今ある、画像の保存先のフォルダー(Template の中)"""
    return list_folders(os.path.join(base_dir, *TEMPLATE_PATH))


# 作るファイルに入れる、ウィジェット(ダイアログ)の例の、初めと終わりの印
WIDGET_BEGIN = "# ---- ウィジェット(ダイアログ)を使う場合は、ここから下の「# 」を外します ----"
WIDGET_END = "# ---- ウィジェットの例は、ここまで ----"


def widget_example(spec: ScriptSpec) -> list:
    """
    ウィジェット(ダイアログ)の例(コメントにする前の行の並び)。
    BridgeFunctions を使う場合: bridge_functions/Sample/bf_sample.py と同じ(設定を保存・選択できるダイアログ)。
    使わない場合: self.dialogue6widget と print だけを使う(設定の保存はしない。利用者の指定)
    """
    if not spec.use_bridge:
        return [
            "# ダイアログ呼び出し",
            "ret = self.dialogue6widget(",
            '    "config",',
            '    [["Entry", "テスト1", 1]],',
            '    desc="テスト用ウィジェット",',
            ")",
            "",
            "# 表示する",
            'print(f"ウィジェット1結果:{ret[0]}")',
            "",
            "# ダイアログ呼び出し(選択肢から選ぶ)",
            "ret = self.dialogue6widget(",
            '    "config",',
            '    [["Combo", "テスト2", ["A", "B", "C"], "A"]],',
            '    desc="テスト用ウィジェット2",',
            ")",
            "",
            "# 表示する",
            'print(f"ウィジェット2結果:{ret[0]}")',
        ]
    save, select = "self.bf.bf_dialogue6widget_save_settings", "self.bf.bf_dialogue6widget_select_settings"
    show, show_other = "self.bf.bf_print({})", "self.bf.bf_print_w({})"
    return [
        "# 履歴保存用ファイル",
        f'settings_file = os.path.join(os.path.dirname(__file__), "{spec.file_name}_setting.json")',
        "",
        "# ダイアログ呼び出し(前回の値を初期値とする)",
        f"ret = {save}(",
        '    "config",',
        '    [["Entry", "テスト1", 1]],',
        "    settings_file,",
        '    desc="テスト用ウィジェット",',
        ")",
        "",
        "# 表示する",
        show.format('f"ウィジェット1結果:{ret[0]}"'),
        "",
        "# 履歴保存用ディレクトリ",
        f'settings_dir = os.path.join(os.path.dirname(__file__), "{spec.file_name}_settings")',
        "",
        "# ダイアログ呼び出し(保存した値を選択して呼び出す)",
        f"ret = {select}(",
        '    "config",',
        '    [["Combo", "テスト2", ["A", "B", "C"], "(n/a)"]],',
        "    settings_dir,",
        '    desc="テスト用ウィジェット2",',
        ")",
        "",
        "# 表示する(標準出力に割り当てられていない方の出力画面に、上書きで表示)",
        show_other.format('f"ウィジェット2結果:{ret[0]}"'),
    ]


def build_source(spec: ScriptSpec) -> str:
    """
    作るファイルの中身(spec は normalized のもの)。
    BridgeFunctions を使う場合は、bridge_functions/Sample/bf_sample.py の流れ(橋渡し関数の用意 → プログラム情報の表示 →
    テンプレートのフォルダーの設定 → ウィジェット)に合わせる。ウィジェットの部分は、どの場合も、コメントにして入れる
    """
    name = json.dumps(spec.name, ensure_ascii=False)
    use_image = bool(spec.template_folder) or spec.use_bridge
    base_class = "ImageProcPythonCommand" if use_image else "PythonCommand"
    print_call = "self.bf.bf_print" if spec.use_bridge else "print"
    lines = [
        "#!/usr/bin/env python3",
        "# -*- coding: utf-8 -*-",
        "",
        "# ボタン・スティック・十字キーの名前(使わないものは、消して構いません)",
        "from Commands.Keys import Button, Direction, Hat  # noqa: F401",
        f"from Commands.PythonCommandBase import {base_class}",
    ]
    if spec.use_bridge:
        lines.append(BRIDGE_IMPORT)
    if spec.use_bridge:
        # os は、ウィジェットの設定の保存先(と、スクリプト格納場所の中の画像の場所)に使う
        uses_os = bool(spec.template_folder) and spec.template_location == IN_SCRIPT_FOLDER
        lines.append("import os" if uses_os else "import os  # noqa: F401 (ウィジェットの設定の保存先に使います)")
    lines.append("")
    if spec.template_folder:
        place = "このファイルと同じフォルダーの中" if spec.template_location == IN_SCRIPT_FOLDER else "SerialController/Template の中"
        lines += [
            f"# テンプレート画像を置くフォルダー({place})",
            f"TEMPLATE_DIR = {json.dumps(spec.template_folder, ensure_ascii=False)}",
            "",
        ]
    lines += [
        "",
        f"class {class_name_for(spec.file_name)}({base_class}):",
        f"    NAME = {name}",
        "    TAGS = []",
        "",
    ]
    if use_image:
        lines += ["    def __init__(self, cam):", "        super().__init__(cam)"]
    else:
        lines += ["    def __init__(self):", "        super().__init__()"]
    lines += ["", "    def do(self):"]
    body = []
    if spec.use_bridge:
        body += [
            "# クロスプラットフォーム用クラス",
            "self.bf = BridgeFunctions(self)",
            "",
            "# プログラム情報の表示",
            f"developer = {json.dumps(spec.author_name(), ensure_ascii=False)}",
            "self.bf.bf_show_informations(self.NAME, developer)",
            "",
        ]
        if spec.template_folder and spec.template_location == IN_SCRIPT_FOLDER:
            body += [
                "# テンプレートファイルディレクトリの設定(このファイルと同じフォルダーの中の TEMPLATE_DIR を使う)",
                "# ※Poke-Controller Modified では、場所は変わらず、Template フォルダーの中の画像が使われます",
                "self.bf.set_template_directory(os.path.join(os.path.dirname(__file__)), TEMPLATE_DIR)",
                "",
            ]
        elif spec.template_folder:
            body += [
                "# テンプレートファイルディレクトリの設定",
                'self.bf.set_template_directory("./Template", TEMPLATE_DIR)',
                "",
            ]
    else:
        body += [f"print({json.dumps(spec.name + ' を開始します', ensure_ascii=False)})", ""]
    body.append(WIDGET_BEGIN)
    body += [("# " + line).rstrip() for line in widget_example(spec)]
    body += [WIDGET_END, "", "# ここに、実行する処理を書きます"]
    if spec.template_folder:
        check = "self.bf.bf_isContainTemplate" if spec.use_bridge else "self.isContainTemplate"
        body += [
            "# 例: 画像が見つかるまで、A を押す",
            f'# while not {check}(f"{{TEMPLATE_DIR}}/sample.png"):',
            "#     self.press(Button.A, wait=1.0)",
        ]
    else:
        body += ["# 例: A を 0.1 秒押して、1 秒待つ", "# self.press(Button.A, duration=0.1, wait=1.0)"]
    body += ["self.wait(1.0)", "", f"{print_call}({json.dumps(spec.name + ' を終了します', ensure_ascii=False)})"]
    lines += [("        " + line).rstrip() for line in body]
    lines.append("")
    return "\n".join(lines)


def _windows_path(spec: ScriptSpec, *names: str) -> str:
    """SerialController から見た場所を、README に書く形(「\\」で区切る)にする"""
    return "\\".join(["SerialController", *COMMANDS_PATH, *(spec.folder.split("/") if spec.folder else []), *names])


def build_readme(spec: ScriptSpec, app_version: str = "") -> str:
    """
    README.md のひな形(bridge_functions/README.md と同じ章立て。spec は normalized のもの)
    app_version: このアプリケーションのバージョン(開発環境と、対象のバージョンに書く。空なら書かない)
    """
    author = spec.author_name()
    app = "Poke-Controller Modified Extension" + (f" ver.{app_version}" if app_version else "")
    lines = [
        "fileencoding=utf-8",
        "",
        f"{spec.name} ver.0.0.1 作成者：{author}",
        "",
        "■要約",
        "\u3000(本プログラムの説明を書いてください。)",
        "",
        "■開発環境",
        f"\u3000python v{platform.python_version()}",
        f"\u3000{app}",
        "",
        "■事前準備",
    ]
    if spec.folder:
        lines += [
            f"* {'\\'.join(['SerialController', *COMMANDS_PATH])}のフォルダにフォルダごとおいてください。",
            f"\u3000{_windows_path(spec, spec.file_name + '.py')}となる想定です。",
        ]
    else:
        lines.append(f"* {_windows_path(spec, spec.file_name + '.py')}となるようにおいてください。")
    if spec.use_bridge:
        lines.append(
            "* 橋渡し関数(bridge_functions)が必要です。"
            "SerialController\\Commands\\PythonCommands\\bridge_functions\\bridge_functions.pyとなるようにおいてください。"
        )
    if spec.template_folder and spec.template_location == IN_SCRIPT_FOLDER:
        lines += [
            f"* テンプレート画像は、{_windows_path(spec, *spec.template_folder.split('/'))}においてください。",
            "\u3000※Poke-Controller Modifiedでは、SerialController\\Template\\"
            + "\\".join(spec.template_folder.split("/")) + "においてください(テンプレートファイルの場所を変更できないため)。",
        ]
    elif spec.template_folder:
        lines.append("* テンプレート画像は、SerialController\\Template\\" + "\\".join(spec.template_folder.split("/")) + "においてください。")
    lines += [
        "",
        "■使用方法",
        f"* Commandsタブの一覧から「{command_name(spec)}」を選び、Startを押します。",
        "* (使い方の手順を書いてください。)",
        "",
        "■対象のバージョン",
        f"* {app}",
    ]
    if spec.use_bridge:
        lines.append("* Poke-Controller Modified(橋渡し関数が対応しているバージョン)")
    lines += [
        "",
        "■利用上の注意",
        "* 勝手に改変して使用いただいて構いません。",
        "* License.txtに記載の通り改変しての配布は禁止とさせていただきます。",
        "* 想定外の動作をした場合でも責任はとれません。自己責任で利用ください。",
        "* 商用利用/自作発言はお控えください。",
        "",
        "■その他",
        "* 質問などありましたら作成者までお問い合わせください。なお、返信には数日ほどかかる場合もありますのでご承知おきください。"
        "常識やマナーを守って問い合わせいただければ幸いです。",
        "* 改変のない再配布は自由に可能です。",
        "* 本プログラムの挙動に関して、他の方に問い合わせをするのはご迷惑をおかけする可能性があるため基本的におやめください。",
        "* 修正および機能追加を希望される場合は作成者までご連絡ください。",
    ]
    if spec.use_bridge:
        lines += ["", "■使用しているプログラム", f"* 本プログラムは、{BRIDGE_CREDIT}を使用しています。"]
    lines.append("")
    return "\n".join(lines)


# License.txt の、関連するプログラムの一覧(bridge_functions/License.txt と同じもの)
_LICENSE_REFERENCES = (
    ("Python", "https://docs.python.org/ja/3/license.html"),
    ("Poke-Controller", "https://github.com/KawaSwitch/Poke-Controller"),
    ("lufa", "https://github.com/abcminiuser/lufa"),
    ("Poke-Controller-Modified", "https://github.com/Moi-poke/Poke-Controller-Modified"),
    ("Poke-Controller-Modified Extension", "https://github.com/futo030/Poke-Controller-Modified-Extension"),
    ("Pillow", "https://github.com/python-pillow/Pillow"),
    ("numpy", "https://numpy.org/doc/stable/license.html"),
    ("opencv-python", "https://github.com/opencv/opencv/tree/master"),
    ("pandas", "https://pandas.pydata.org/pandas-docs/stable/getting_started/overview.html"),
    ("plyer", "https://github.com/kivy/plyer"),
    ("pygubu", "https://github.com/alejandroautalan/pygubu"),
    ("pynput", "https://github.com/pravinnath/pynput"),
    ("pyocr", "https://gitlab.gnome.org/World/OpenPaperwork/pyocr/-/tree/master"),
    ("pyperclip", "https://github.com/asweigart/pyperclip"),
    ("pyserial", "https://github.com/pyserial/pyserial"),
    ("pythonnet", "https://github.com/pythonnet/pythonnet"),
    ("requests", "https://github.com/psf/requests"),
    ("scipy", "https://github.com/scipy/scipy"),
    ("pygame", "https://github.com/pygame/pygame"),
    ("paho-mqtt", "https://github.com/eclipse/paho.mqtt.python"),
)


def build_license(spec: ScriptSpec, year: int | None = None) -> str:
    """
    License.txt のひな形(bridge_functions/License.txt と同じ条項。商用利用を禁止する内容で、MIT ではない)
    year: 著作権の年(None なら、今年)
    """
    year = datetime.date.today().year if year is None else year
    lines = [
        spec.name,
        f"Copyright (C) {year}年 {spec.author_name()}",
        "",
        "1.本プログラムは、個人のみ使用可能であり、プログラム利用者は以下のことを実行可能です。",
        "\u3000・プログラムの実行、複製、改変、改変しない状態での二次配布",
        "",
        "2.本プログラム利用者は、以下のことを遵守しなければなりません。",
        "\u3000・商用利用(※)をしない。",
        "\u3000\u3000※商用利用とは、本プログラムを用いて金銭的な対価を得ることを指します。",
        "\u3000\u3000(例：本プログラムの販売、本プログラムを用いて得られた成果物の販売、など。なお、配信サイトにおける配信での利用は対象外です。）",
        "",
        "3.本プログラム利用者は、以下の行為を行う場合、プログラムのどこか(例:readme)に引用の旨を記載する必要があります。",
        "\u3000・本プログラムを同梱したプログラムの配布",
        "",
        "4.本プログラムの少なくとも一部を抽出または改変して公開したい場合、プログラム作成者に連絡の上、プログラム作成者より配布するものとします。",
        "",
        "5.本プログラムではプログラミング言語(python)およびpythonのライブラリを使用します。各プログラムに関する権利はそれぞれの権利者が有します。",
        "\u3000権利者から本プログラムの利用中止を求められた場合は直ちに本プログラムの利用を中止するものとします。",
        "",
    ]
    references = list(_LICENSE_REFERENCES)
    if spec.use_bridge:
        references.insert(5, ("Poke-Controller Modified/Extension 橋渡し関数", "(同梱の bridge_functions フォルダーの License.txt)"))
    width = max(len(name) for name, _ in references) + 3
    lines += [name.ljust(width) + url for name, url in references]
    lines += [
        "",
        "6.本プログラム利用者は、自らの責任において本プログラムを利用することに同意し、"
        "本プログラムの利用によって生じる一切の損害、損失について、著作権者は損害賠償義務及びその他一切の責任を負いません。",
        "",
    ]
    return "\n".join(lines)


def create_script(spec: ScriptSpec, base_dir: str = BASE_DIR, app_version: str = "") -> ScriptResult:
    """
    スクリプトのファイルを作る(格納場所と、画像の保存先のフォルダーも、なければ作る)。
    格納場所に、README.md と License.txt のひな形も作る(すでにあるものは、上書きせず、そのままにする)。
    app_version: README.md に書く、このアプリケーションのバージョン
    作れないとき(入力の誤り、同じ名前のファイルがある、書き込めない)は ScriptCreateError
    """
    spec = spec.normalized()
    error = check_spec(spec, base_dir)
    if error:
        raise ScriptCreateError(error)
    path = script_path(spec, base_dir)
    result = ScriptResult(path=path, command_name=command_name(spec), class_name=class_name_for(spec.file_name))
    try:
        for folder in (os.path.dirname(path), template_dir(spec, base_dir)):
            if folder and not os.path.isdir(folder):
                # 新しく作るフォルダーを、上から順に覚える
                missing = []
                current = folder
                while not os.path.isdir(current):
                    missing.append(current)
                    current = os.path.dirname(current)
                os.makedirs(folder)
                result.created_folders += reversed(missing)
        # すでにあるファイルは、上書きしない("x": なければ作る。あればエラー)
        with open(path, "x", encoding="utf-8", newline="\n") as file:
            file.write(build_source(spec))
    except FileExistsError as e:
        raise ScriptCreateError(f"同じ名前のファイルが、すでにあります: {_relative(path, base_dir)}") from e
    except OSError as e:
        raise ScriptCreateError(f"ファイルを作れませんでした({e.strerror or e})。") from e
    # 説明とライセンスのひな形(スクリプトは作れているので、こちらが作れなくても、エラーにはしない)
    for name, content in ((README_NAME, build_readme(spec, app_version)), (LICENSE_NAME, build_license(spec))):
        extra = os.path.join(os.path.dirname(path), name)
        try:
            with open(extra, "x", encoding="utf-8", newline="\n") as file:
                file.write(content)
            result.created_files.append(extra)
        except OSError:
            # すでにある(同じフォルダーに、ほかのスクリプトがある)か、書き込めない
            result.skipped_files.append(extra)
    _logger.info(f"Script created: {path}")
    return result
