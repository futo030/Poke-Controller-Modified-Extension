#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GUIのテーマ(配色)

- デフォルト(Light): 今までの見た目(Windows の標準のテーマ vista)。色は変えない
- それ以外: 色を変えられるテーマ clam に、テーマごとの配色を付ける
  (vista は Windows の部品をそのまま描くため、色を変えられない)

色は「役割」(背景・入力欄・文字など)ごとに持つ。tk の部品(Text・Frame など)は、
今の色が前のテーマのその役割の色と同じ場合だけ、新しいテーマの色に置き換える
(コントローラーの色など、役割と関係なく決めた色は変えない)。
"""
from __future__ import annotations

import ctypes
import json
import os
import platform
import re
import tkinter as tk
import tkinter.ttk as ttk
from logging import NullHandler, getLogger
from typing import Callable

DEFAULT_THEME = "default"

# 色の役割
# bg: 背景 / surface: 少し浮いた部分(タブの見出し・メニューバー) / field: 入力欄・出力画面 / border: 枠線
# fg: 文字 / muted: 薄い文字(無効・選んでいないタブ) / accent: 強調(チェック・フォーカス)
# select: 選択の背景 / select_fg: 選択の文字 / check_fg: チェックの印
# button / button_active: ボタン(マウスを重ねたとき) / sash: 仕切り線 / link: リンク
# code: Instruction Manual のコードの背景 / danger: 記録中など(赤) / menu / menu_fg: メニュー
# tile_border / strong_border: コントローラー設定のプリセットの枠(選んでいるもの) / focus_border: 入力中の一覧などの枠
DEFAULT_COLORS = dict(
    bg="SystemButtonFace",
    surface="SystemButtonFace",
    field="SystemWindow",
    border="#a0a0a0",
    fg="SystemButtonText",
    text_fg="SystemWindowText",
    muted="SystemGrayText",
    accent="SystemHighlight",
    select="SystemHighlight",
    select_fg="SystemHighlightText",
    check_fg="SystemHighlightText",
    button="SystemButtonFace",
    button_active="SystemButtonFace",
    sash="#e6e6e6",
    link="#0066cc",
    code="#f1f3f5",
    danger="red",
    menu="SystemMenu",
    menu_fg="SystemMenuText",
    tile_border="#a0a0a0",
    strong_border="#000000",
    focus_border="SystemWindowFrame",
)
# デフォルトのテーマで、役割の色と同じとみなす値(Tk の既定値や、コードで指定している値)
DEFAULT_ALIASES = dict(
    bg={"#f0f0f0"},
    field={"white"},
    fg={"black", "systemwindowtext"},
    text_fg={"black", "systembuttontext"},
)


def _palette(dark: bool, bg: str, surface: str, field: str, border: str, fg: str, muted: str, accent: str, select: str,
             select_fg: str, check_fg: str, button: str, button_active: str, sash: str, link: str, code: str,
             danger: str) -> dict:
    """
    テーマの定義(暗いテーマか、役割ごとの色)を作る。
    dark: 暗いテーマか。そのほかの引数: その役割の色("#rrggbb")。
    引数に無い役割(text_fg / menu / menu_fg / tile_border / strong_border / focus_border)は、ほかの役割の色から決める
    """
    return dict(
        dark=dark,
        colors=dict(
            bg=bg, surface=surface, field=field, border=border, fg=fg, text_fg=fg, muted=muted, accent=accent,
            select=select, select_fg=select_fg, check_fg=check_fg, button=button, button_active=button_active,
            sash=sash, link=link, code=code, danger=danger, menu=surface, menu_fg=fg,
            tile_border=border, strong_border=fg, focus_border=border,
        ),
    )


# テーマ: ID -> 名前・暗いテーマか・色
THEMES = {
    DEFAULT_THEME: dict(name="デフォルト (Light)", dark=False, colors=DEFAULT_COLORS),
    "dark_gray": dict(name="A: ダーク(グレー)", **_palette(
        True, "#202020", "#2b2b2b", "#1b1b1b", "#3c3c3c", "#e4e4e4", "#9a9a9a", "#4cc2ff", "#0e5a8a", "#ffffff",
        "#000000", "#333333", "#3d3d3d", "#3a3a3a", "#6cb8ff", "#2a2d31", "#ff6b6b")),
    "dark_blue": dict(name="B: ダーク(青みのあるグレー)", **_palette(
        True, "#1e1e1e", "#252526", "#1e1e1e", "#3f3f46", "#d4d4d4", "#8c8c8c", "#3794ff", "#264f78", "#ffffff",
        "#000000", "#0e639c", "#1177bb", "#333337", "#4fc1ff", "#2a2a2e", "#f48771")),
    "dark_charcoal": dict(name="C: ダーク(チャコール)", **_palette(
        True, "#2d2f33", "#36393f", "#26282c", "#4a4d54", "#e8e8e8", "#a0a0a0", "#7aa2f7", "#3e5a8f", "#ffffff",
        "#000000", "#40444b", "#4a4f57", "#45484f", "#8ab4f8", "#33363b", "#ff7b72")),
    "light_white": dict(name="D: 白基調", **_palette(
        False, "#f3f3f3", "#fafafa", "#ffffff", "#d1d1d1", "#1b1b1b", "#6e6e6e", "#0067c0", "#cce4f7", "#1b1b1b",
        "#ffffff", "#fdfdfd", "#ececec", "#e0e0e0", "#0066cc", "#eef0f2", "#c42b1c")),
    "blue_gray": dict(name="E: ブルーグレー", **_palette(
        False, "#e6edf5", "#f2f6fb", "#ffffff", "#b4c4d8", "#1a2b3c", "#5d6f84", "#2f6db5", "#bcd5f2", "#1a2b3c",
        "#ffffff", "#d4e1f0", "#c2d4ea", "#c6d4e5", "#1f5fae", "#eef3f9", "#c42b1c")),
    "warm": dict(name="F: ウォーム(ベージュ)", **_palette(
        False, "#f3eee4", "#f9f5ee", "#fffdf8", "#d4c8b3", "#3a3026", "#7d6e5c", "#b5651d", "#efd9bb", "#3a3026",
        "#ffffff", "#e9e0cf", "#e0d3bd", "#dbcfba", "#9a4f0f", "#f6f0e5", "#c0392b")),
    "mint": dict(name="G: ミント(グリーン)", **_palette(
        False, "#e7f2ec", "#f3f9f6", "#ffffff", "#b3d1c1", "#1d3229", "#5a7468", "#2e8b57", "#c3e4d0", "#1d3229",
        "#ffffff", "#d1e7da", "#bfdecb", "#c5ddd0", "#1d7047", "#eef6f1", "#c0392b")),
    "lavender": dict(name="H: ラベンダー", **_palette(
        False, "#eeebf6", "#f7f5fb", "#ffffff", "#c9c1de", "#2a2440", "#6d6585", "#6a4fb3", "#dcd2f2", "#2a2440",
        "#ffffff", "#e1dbf0", "#d4cbea", "#d6cfe8", "#5a3fa6", "#f3f1f9", "#c0392b")),
}

# tk の部品の種類ごとに、色の設定項目と、その色の役割(候補を順に調べる)
OPTION_ROLES = {
    "Text": dict(
        background=("field", "code"), foreground=("text_fg",), insertbackground=("text_fg",),
        selectbackground=("select",), selectforeground=("select_fg",), highlightbackground=("bg",),
        highlightcolor=("focus_border",),
    ),
    "Listbox": dict(
        background=("field",), foreground=("text_fg",), selectbackground=("select",), selectforeground=("select_fg",),
        highlightbackground=("bg",), highlightcolor=("focus_border",),
    ),
    "Frame": dict(background=("bg", "sash", "field"), highlightbackground=("bg", "tile_border", "strong_border")),
    "Label": dict(background=("bg", "field"), foreground=("fg",)),
    "Toplevel": dict(background=("bg",)),
    "Tk": dict(background=("bg",)),
    "Canvas": dict(background=("bg", "field"), highlightbackground=("bg",)),
    "Panedwindow": dict(background=("sash",)),
    "Menu": dict(
        background=("menu",), foreground=("menu_fg",), activebackground=("select",), activeforeground=("select_fg",),
        disabledforeground=("muted",), selectcolor=("menu_fg",),
    ),
    "Button": dict(
        background=("bg",), foreground=("fg",), activebackground=("bg",), activeforeground=("fg",),
        highlightbackground=("bg",),
    ),
    "Checkbutton": dict(background=("bg",), foreground=("fg",), activebackground=("bg",), selectcolor=("field",)),
    "Radiobutton": dict(background=("bg",), foreground=("fg",), activebackground=("bg",), selectcolor=("field",)),
}
# Text の文字の装飾(タグ)の色の役割
TAG_ROLES = dict(foreground=("link", "danger"), background=("code",))

# 新しく作る tk の部品の色(オプションデータベース): パターン -> 役割
OPTION_DATABASE = {
    "*Text.background": "field",
    "*Text.foreground": "text_fg",
    "*Text.insertBackground": "text_fg",
    "*Text.selectBackground": "select",
    "*Text.selectForeground": "select_fg",
    "*Text.highlightColor": "focus_border",
    "*Listbox.background": "field",
    "*Listbox.foreground": "text_fg",
    "*Listbox.selectBackground": "select",
    "*Listbox.selectForeground": "select_fg",
    "*Listbox.highlightColor": "focus_border",
    "*Frame.background": "bg",
    "*Label.background": "bg",
    "*Label.foreground": "fg",
    "*Toplevel.background": "bg",
    "*Canvas.background": "bg",
    "*Canvas.highlightBackground": "bg",
    "*Menu.background": "menu",
    "*Menu.foreground": "menu_fg",
    "*Menu.activeBackground": "select",
    "*Menu.activeForeground": "select_fg",
    "*Menu.disabledForeground": "muted",
    "*Button.background": "bg",
    "*Button.foreground": "fg",
    "*Button.activeBackground": "bg",
    "*TCombobox*Listbox.background": "field",
    "*TCombobox*Listbox.foreground": "text_fg",
    "*TCombobox*Listbox.selectBackground": "select",
    "*TCombobox*Listbox.selectForeground": "select_fg",
}

# Windows のタイトルバーの設定(DwmSetWindowAttribute)
DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_CAPTION_COLOR = 35
DWMWA_COLOR_DEFAULT = 0xFFFFFFFF

_state = dict(
    theme=DEFAULT_THEME, root=None, base_theme=None, hooks=[], images=None, element=False, preview_origin=None
)
# テーマを作る画面で、色を試している間だけ使う、一時的なテーマの ID(メニューには出さない。設定にも保存しない)
PREVIEW_THEME = "__preview"
_logger = getLogger(__name__)
_logger.addHandler(NullHandler())


def theme_ids() -> list:
    """テーマの ID の一覧(定義した順。色を試している間の、一時的なテーマは含まない)"""
    return [theme_id for theme_id in THEMES if theme_id != PREVIEW_THEME]


def theme_name(theme_id: str) -> str:
    """テーマの、画面に出す名前(知らない ID は KeyError)"""
    return THEMES[theme_id]["name"]


def current() -> str:
    """今のテーマの ID(色を試している間は、一時的なテーマの ID)"""
    return _state["theme"]


def saved_theme_id() -> str:
    """
    設定に保存するテーマの ID(色を試している間は、試す前のテーマ。そうでなければ、今のテーマ)
    """
    return _state["preview_origin"] or _state["theme"]


def is_color(value: object) -> bool:
    """色の書き方("#rrggbb")として読めるか"""
    return isinstance(value, str) and _COLOR_PATTERN.fullmatch(value) is not None


def is_default() -> bool:
    """今のテーマが、デフォルト(色を変えないテーマ)か"""
    return _state["theme"] == DEFAULT_THEME


############### 利用者が足すテーマ ###############
# themes フォルダーの *.json を、起動時(init)と、メニューの「テーマを読み込み直す」で読み込む。
# ファイルの形: {"name": "名前", "dark": true / false, "colors": {"bg": "#rrggbb", ...}}
USER_THEME_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "themes")
# 利用者が足したテーマの ID は「user_ファイル名」(元からあるテーマと、重ならないようにする)
USER_THEME_PREFIX = "user_"
# 必ず書く役割(_palette の引数と同じ)と、書かなければ、ほかの役割の色から決める役割
USER_THEME_ROLES = ("bg", "surface", "field", "border", "fg", "muted", "accent", "select", "select_fg", "check_fg",
                    "button", "button_active", "sash", "link", "code", "danger")
USER_THEME_OPTIONAL_ROLES = ("text_fg", "menu", "menu_fg", "tile_border", "strong_border", "focus_border")
USER_THEME_NAME_MAX_LENGTH = 40
_COLOR_PATTERN = re.compile(r"#[0-9a-fA-F]{6}")
# ひな形を作るとき、デフォルトのテーマ(色が Windows の設定で決まる)の代わりに、元にするテーマ
TEMPLATE_BASE_THEME = "light_white"


def parse_user_theme(data: object) -> dict:
    """
    利用者が書いたテーマ(JSON を読んだもの)を確かめて、テーマの定義(THEMES の値と同じ形)にする。
    使えない内容のときは ValueError(理由を、利用者に見せる文で持つ)
    """
    if not isinstance(data, dict):
        raise ValueError("全体を { } で囲んだ形にしてください。")
    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError('"name" に、テーマの名前を書いてください。')
    if len(name.strip()) > USER_THEME_NAME_MAX_LENGTH:
        raise ValueError(f'"name" は {USER_THEME_NAME_MAX_LENGTH} 文字までにしてください。')
    colors = data.get("colors")
    if not isinstance(colors, dict):
        raise ValueError('"colors" に、役割ごとの色を書いてください。')
    missing = [role for role in USER_THEME_ROLES if role not in colors]
    if missing:
        raise ValueError('"colors" に、次の役割がありません: ' + ", ".join(missing))
    unknown = [role for role in colors if role not in USER_THEME_ROLES + USER_THEME_OPTIONAL_ROLES]
    if unknown:
        raise ValueError('"colors" に、知らない役割があります: ' + ", ".join(str(role) for role in unknown))
    bad = [role for role, value in colors.items() if not isinstance(value, str) or not _COLOR_PATTERN.fullmatch(value)]
    if bad:
        raise ValueError('色は "#rrggbb" の形で書いてください: ' + ", ".join(bad))
    dark = data.get("dark")
    if dark is None:
        # 書いていなければ、背景の明るさから決める
        red, green, blue = (int(colors["bg"][i:i + 2], 16) for i in (1, 3, 5))
        dark = (red * 299 + green * 587 + blue * 114) / 1000 < 128
    elif not isinstance(dark, bool):
        raise ValueError('"dark" は true か false にしてください(暗いテーマなら true)。')
    theme = _palette(dark, **{role: colors[role].lower() for role in USER_THEME_ROLES})
    for role in USER_THEME_OPTIONAL_ROLES:
        if role in colors:
            theme["colors"][role] = colors[role].lower()
    return dict(name=name.strip(), **theme)


def user_theme_ids() -> list:
    """利用者が足したテーマの ID の一覧"""
    return [theme_id for theme_id in THEMES if theme_id.startswith(USER_THEME_PREFIX)]


def load_user_themes(folder: str | None = None) -> list:
    """
    themes フォルダーのテーマを読み込み直す(前に読み込んだものは、いったん外す)。
    戻り値: 読み込めなかったファイル [(ファイルの名前, 理由), ...]
    folder: テーマのフォルダー(None: USER_THEME_DIR)
    """
    folder = folder or USER_THEME_DIR
    for theme_id in user_theme_ids():
        del THEMES[theme_id]
    problems = []
    try:
        names = sorted(name for name in os.listdir(folder) if name.lower().endswith(".json"))
    except OSError:
        return problems
    for name in names:
        try:
            with open(os.path.join(folder, name), encoding="utf-8-sig") as file:
                theme = parse_user_theme(json.load(file))
        except json.JSONDecodeError as error:
            problems.append((name, f"JSON として読めません({error.lineno} 行目: {error.msg})。"))
        except (OSError, UnicodeDecodeError) as error:
            problems.append((name, f"ファイルを読めません({error})。"))
        except ValueError as error:
            problems.append((name, str(error)))
        else:
            THEMES[USER_THEME_PREFIX + os.path.splitext(name)[0]] = theme
    return problems


def reload_user_themes(folder: str | None = None) -> list:
    """
    themes フォルダーのテーマを読み込み直し、今のテーマを当て直す(今のテーマのファイルを書き換えた場合に、色を変える)。
    今のテーマがなくなっていた場合は、デフォルトのテーマにする。戻り値: load_user_themes と同じ
    """
    # (色を試している間は、試すのをやめてから、読み込み直す)
    end_preview()
    previous = dict(THEMES[_state["theme"]]["colors"])
    current_id = _state["theme"]
    problems = load_user_themes(folder)
    if _state["root"] is not None:
        apply(current_id if current_id in THEMES else DEFAULT_THEME, force=True, previous=previous)
    elif current_id not in THEMES:
        _state["theme"] = DEFAULT_THEME
    return problems


def theme_template(theme_id: str | None = None, name: str = "My Theme") -> dict:
    """
    テーマのひな形(ファイルに書く内容)を作る。色は、theme_id(None: 今のテーマ)のものを入れる。
    デフォルトのテーマは、色が Windows の設定で決まるので、代わりに TEMPLATE_BASE_THEME の色を入れる
    """
    theme_id = current() if theme_id is None else theme_id
    if theme_id not in THEMES or theme_id == DEFAULT_THEME:
        theme_id = TEMPLATE_BASE_THEME
    source = THEMES[theme_id]
    return dict(name=name, dark=source["dark"], colors={role: source["colors"][role] for role in USER_THEME_ROLES})


def create_user_theme(folder: str | None = None, theme_id: str | None = None) -> str:
    """
    今のテーマ(theme_id)の色を入れた、テーマのひな形のファイルを作って、その場所を返す。
    名前は my_theme.json(あれば my_theme_2.json、…)。すでにあるファイルは、上書きしない
    """
    folder = folder or USER_THEME_DIR
    os.makedirs(folder, exist_ok=True)
    number = 1
    while True:
        stem = "my_theme" if number == 1 else f"my_theme_{number}"
        path = os.path.join(folder, stem + ".json")
        try:
            with open(path, "x", encoding="utf-8", newline="\n") as file:
                name = "My Theme" if number == 1 else f"My Theme {number}"
                json.dump(theme_template(theme_id, name), file, ensure_ascii=False, indent=2)
                file.write("\n")
            return path
        except FileExistsError:
            number += 1


def save_user_theme(data: dict, stem: str | None = None, folder: str | None = None) -> str:
    """
    テーマを、themes フォルダーのファイルに書いて、読み込む。ファイルの名前(.json の前)を返す
    data: 書く内容(name / dark / colors。parse_user_theme で確かめられる形。使えない内容なら ValueError)
    stem: 上書きするファイルの名前(None: 新しいファイル。my_theme、my_theme_2、… のうち、まだないもの)
    """
    folder = folder or USER_THEME_DIR
    theme = parse_user_theme(data)
    os.makedirs(folder, exist_ok=True)
    if stem is None:
        number = 1
        while True:
            stem = "my_theme" if number == 1 else f"my_theme_{number}"
            if not os.path.exists(os.path.join(folder, stem + ".json")):
                break
            number += 1
    content = dict(name=theme["name"], dark=theme["dark"], colors={role: theme["colors"][role] for role in USER_THEME_ROLES})
    path = os.path.join(folder, stem + ".json")
    temporary = f"{path}.{os.getpid()}.tmp"
    try:
        with open(temporary, "w", encoding="utf-8", newline="\n") as file:
            json.dump(content, file, ensure_ascii=False, indent=2)
            file.write("\n")
        os.replace(temporary, path)
    finally:
        try:
            os.remove(temporary)
        except OSError:
            pass
    THEMES[USER_THEME_PREFIX + stem] = theme
    return stem


def delete_user_theme(stem: str, folder: str | None = None) -> None:
    """themes フォルダーの、テーマのファイルを消す(消せないときは OSError)。テーマの一覧からも外す"""
    folder = folder or USER_THEME_DIR
    os.remove(os.path.join(folder, stem + ".json"))
    THEMES.pop(USER_THEME_PREFIX + stem, None)


def start_preview(theme: dict) -> None:
    """
    本体の色を、一時的に theme(parse_user_theme の戻り値の形)に変える(テーマを作る画面で、色を試す)。
    end_preview で、元のテーマに戻る。試している間に、もう一度呼ぶと、色だけを入れ替える
    """
    previous = dict(THEMES[_state["theme"]]["colors"])
    if _state["preview_origin"] is None:
        _state["preview_origin"] = _state["theme"]
    THEMES[PREVIEW_THEME] = theme
    apply(PREVIEW_THEME, force=True, previous=previous)


def end_preview(theme_id: str | None = None) -> None:
    """
    色を試すのをやめて、元のテーマに戻す(試していなければ、何もしない)。
    theme_id: 戻す先のテーマ(None: 試す前のテーマ。なくなっていれば、デフォルト)
    """
    origin = _state["preview_origin"]
    if origin is None:
        return
    previous = dict(THEMES[_state["theme"]]["colors"])
    _state["preview_origin"] = None
    target = theme_id if theme_id is not None else origin
    apply(target if target in THEMES and target != PREVIEW_THEME else DEFAULT_THEME, force=True, previous=previous)
    THEMES.pop(PREVIEW_THEME, None)


def is_dark() -> bool:
    """今のテーマが、暗いテーマか"""
    return THEMES[_state["theme"]]["dark"]


def color(role: str) -> str:
    """
    今のテーマの、役割の色(role: "bg" / "fg" などの役割の名前。知らない役割は KeyError)
    """
    return THEMES[_state["theme"]]["colors"][role]


def add_style_hook(hook: Callable[[ttk.Style], None]) -> None:
    """
    テーマを変えるたびに呼ぶ処理(ttk のスタイルはテーマごとに持つため、独自のスタイルを作り直す)を登録し、今すぐ1回呼ぶ
    hook(style: ttk.Style)
    """
    _state["hooks"].append(hook)
    if _state["root"] is not None:
        hook(ttk.Style())


def init(root: tk.Tk, theme_id: str = DEFAULT_THEME) -> None:
    """
    テーマの準備をし、テーマを当てる(アプリの起動時に1回)
    theme_id: テーマの ID(知らない ID は、デフォルトのテーマにする)
    """
    _state["root"] = root
    _state["base_theme"] = ttk.Style().theme_use()
    # 利用者が足したテーマ(themes フォルダー)を読み込む。読み込めないファイルは、ログに残して、飛ばす
    for name, reason in load_user_themes():
        _logger.warning(f"Failed to load the theme file {name}: {reason}")
    # 後から開くウィンドウにも、タイトルバーの色を付ける
    root.bind_class("Toplevel", "<Map>", _onMapToplevel, add="+")
    apply(theme_id if theme_id in THEMES else DEFAULT_THEME, force=True)


def apply(theme_id: str, force: bool = False, previous: dict | None = None) -> None:
    """
    テーマを変える(開いているすべてのウィンドウに反映する)
    theme_id: テーマの ID(知らない ID は、デフォルトのテーマにする)
    force: 今と同じテーマでも当て直す(起動時。部品の色は、デフォルトの色から置き換える)
    previous: 今、部品に付いている色(役割 -> 色)。None: 今のテーマの色(force のときは、デフォルトの色)。
        テーマの定義を読み込み直した後に、前の色から置き換えるときに渡す
    """
    if theme_id not in THEMES:
        theme_id = DEFAULT_THEME
    if theme_id == _state["theme"] and not force:
        return
    if previous is None:
        previous = THEMES[_state["theme"]]["colors"] if not force else DEFAULT_COLORS
    _state["theme"] = theme_id
    root = _state["root"]
    style = ttk.Style()
    if theme_id == DEFAULT_THEME:
        style.theme_use(_state["base_theme"])
    else:
        style.theme_use("clam")
        _configureStyles(style)
    for hook in _state["hooks"]:
        hook(style)
    for pattern, role in OPTION_DATABASE.items():
        root.option_add(pattern, color(role))
    _recolor(root, previous)
    _setTitleBar(root)
    for widget in _toplevels(root):
        _setTitleBar(widget)


############### ttk のスタイル ###############
def _configureStyles(s: ttk.Style) -> None:
    """ttk の部品のスタイル(clam)に、今のテーマの色を付ける"""
    c = THEMES[_state["theme"]]["colors"]
    s.configure(
        ".", background=c["bg"], foreground=c["fg"], fieldbackground=c["field"], bordercolor=c["border"],
        darkcolor=c["bg"], lightcolor=c["bg"], troughcolor=c["field"], selectbackground=c["select"],
        selectforeground=c["select_fg"], insertcolor=c["text_fg"], arrowcolor=c["fg"], focuscolor=c["accent"],
    )
    s.map(".", foreground=[("disabled", c["muted"])], background=[("disabled", c["bg"])])
    # 大きさは、デフォルト(vista)の見た目と同じくらいにする
    s.configure("TButton", background=c["button"], bordercolor=c["border"], lightcolor=c["button"], darkcolor=c["button"],
                padding=(2, 2), anchor="center")
    s.map(
        "TButton",
        background=[("pressed", c["select"]), ("active", c["button_active"]), ("disabled", c["bg"])],
        lightcolor=[("active", c["button_active"])],
        darkcolor=[("active", c["button_active"])],
    )
    s.configure("TLabelframe", background=c["bg"], bordercolor=c["border"], lightcolor=c["bg"], darkcolor=c["bg"],
                borderwidth=1, labelmargins=(6, 0, 0, 0))
    s.configure("TLabelframe.Label", background=c["bg"], foreground=c["fg"])
    s.configure("TNotebook", background=c["bg"], bordercolor=c["border"], lightcolor=c["bg"], darkcolor=c["bg"])
    s.configure("TNotebook.Tab", background=c["surface"], foreground=c["muted"], bordercolor=c["border"],
                lightcolor=c["surface"], darkcolor=c["surface"], padding=(3, 1))
    s.map(
        "TNotebook.Tab",
        background=[("selected", c["bg"]), ("active", c["button_active"])],
        foreground=[("selected", c["fg"])],
        lightcolor=[("selected", c["bg"])],
        padding=[("selected", (3, 1))],
    )
    for name in ("TCombobox", "TEntry", "TSpinbox"):
        s.configure(name, fieldbackground=c["field"], background=c["button"], foreground=c["text_fg"],
                    bordercolor=c["border"], lightcolor=c["field"], darkcolor=c["field"], arrowcolor=c["fg"],
                    insertcolor=c["text_fg"])
        s.map(
            name,
            fieldbackground=[("readonly", c["field"]), ("disabled", c["bg"])],
            foreground=[("disabled", c["muted"]), ("readonly", c["text_fg"])],
            selectbackground=[("readonly", c["field"])],
            selectforeground=[("readonly", c["text_fg"])],
            bordercolor=[("focus", c["accent"])],
        )
    s.configure("TSpinbox", arrowsize=10, padding=(1, 0))
    for name in ("TCheckbutton", "TRadiobutton"):
        s.configure(name, background=c["bg"], foreground=c["fg"], indicatorbackground=c["field"],
                    indicatorforeground=c["fg"], upperbordercolor=c["border"], lowerbordercolor=c["border"])
        s.map(name, background=[("active", c["bg"])],
              indicatorbackground=[("selected", c["accent"]), ("pressed", c["select"])],
              indicatorforeground=[("selected", c["check_fg"])])
    _configureCheckIndicator(s)
    for orient in ("Horizontal", "Vertical"):
        s.configure(f"{orient}.TScrollbar", background=c["surface"], troughcolor=c["bg"], bordercolor=c["bg"],
                    arrowcolor=c["muted"], lightcolor=c["surface"], darkcolor=c["surface"], arrowsize=16)
        s.map(f"{orient}.TScrollbar", background=[("active", c["button_active"])])
    s.configure("Horizontal.TScale", background=c["button"], troughcolor=c["field"], bordercolor=c["border"],
                lightcolor=c["button"], darkcolor=c["button"])
    s.configure("Treeview", background=c["field"], fieldbackground=c["field"], foreground=c["text_fg"],
                bordercolor=c["border"])
    s.map("Treeview", background=[("selected", c["select"])], foreground=[("selected", c["select_fg"])])
    s.configure("Treeview.Heading", background=c["surface"], foreground=c["fg"], bordercolor=c["border"],
                lightcolor=c["surface"], darkcolor=c["surface"], padding=(3, 1))
    s.map("Treeview.Heading", background=[("active", c["button_active"])])
    s.configure("TSeparator", background=c["border"])
    s.configure("TProgressbar", background=c["accent"], troughcolor=c["field"], bordercolor=c["border"],
                lightcolor=c["accent"], darkcolor=c["accent"])
    # 自作のメニューバー
    s.configure("MenuBar.TFrame", background=c["surface"])
    s.configure("MenuBar.TLabel", background=c["surface"], foreground=c["fg"], padding=(8, 1))
    s.map("MenuBar.TLabel", background=[("active", c["button_active"])])


def _configureCheckIndicator(s: ttk.Style) -> None:
    """
    チェックボックスの印を「✓」にする(clam の印は「×」のため)。画像はテーマの色で描き直す
    """
    c = THEMES[_state["theme"]]["colors"]
    if _state["images"] is None:
        _state["images"] = dict(off=tk.PhotoImage(width=13, height=13), on=tk.PhotoImage(width=13, height=13))
    off, on = _state["images"]["off"], _state["images"]["on"]
    for image, fill in ((off, c["field"]), (on, c["accent"])):
        image.put(c["border"] if image is off else c["accent"], to=(0, 0, 13, 13))
        image.put(fill, to=(1, 1, 12, 12))
    # 印(✓)
    for x, y in ((3, 6), (4, 7), (5, 8), (6, 7), (7, 6), (8, 5), (9, 4)):
        on.put(c["check_fg"], to=(x, y, x + 1, y + 2))
    if not _state["element"]:
        s.element_create("Themed.Checkbutton.indicator", "image", off, ("selected", on), border=0, sticky="")
        _state["element"] = True
    s.layout(
        "TCheckbutton",
        [("Checkbutton.padding", {"sticky": "nswe", "children": [
            ("Themed.Checkbutton.indicator", {"side": "left", "sticky": ""}),
            ("Checkbutton.focus", {"side": "left", "sticky": "w", "children": [
                ("Checkbutton.label", {"sticky": "nswe"})]})]})],
    )
    s.configure("TCheckbutton", padding=(2, 2, 2, 2))


############### tk の部品 ###############
def _toplevels(root: tk.Misc) -> list[tk.Toplevel]:
    """root の下にある、すべての Toplevel(子の子も含む)"""
    result = []
    stack = [root]
    while stack:
        widget = stack.pop()
        for child in widget.winfo_children():
            if isinstance(child, tk.Toplevel):
                result.append(child)
            stack.append(child)
    return result


def _matches(value: str, role: str, previous: dict) -> bool:
    """
    部品の今の色 value が、その役割の色か(置き換えてよいか)。
    previous: 前のテーマの、役割 -> 色。前のテーマの色のほか、デフォルトの色とも比べる(大文字・小文字は区別しない)
    """
    value = str(value).lower()
    if value == str(previous[role]).lower():
        return True
    # デフォルトの色(Tk の既定値など)は、どのテーマからでも置き換える
    return value == DEFAULT_COLORS[role].lower() or value in DEFAULT_ALIASES.get(role, set())


def _recolor(widget: tk.Misc, previous: dict) -> None:
    """
    tk の部品の色を、前のテーマの役割の色から、今のテーマの役割の色に置き換える(子の部品も)
    theme_exclude を True にした部品(コントローラーの絵など)は、子の部品も含めて変えない
    """
    if getattr(widget, "theme_exclude", False):
        return
    roles = OPTION_ROLES.get(widget.winfo_class())
    if roles is not None and not isinstance(widget, ttk.Widget):
        changes = {}
        for option, candidates in roles.items():
            try:
                value = widget.cget(option)
            except tk.TclError:
                continue
            for role in candidates:
                if _matches(value, role, previous):
                    changes[option] = color(role)
                    break
        if changes:
            try:
                widget.configure(**changes)
            except tk.TclError:
                pass
        if isinstance(widget, tk.Text):
            for tag in widget.tag_names():
                for option, candidates in TAG_ROLES.items():
                    value = widget.tag_cget(tag, option)
                    if not value:
                        continue
                    for role in candidates:
                        if _matches(value, role, previous):
                            widget.tag_configure(tag, **{option: color(role)})
                            break
    for child in widget.winfo_children():
        _recolor(child, previous)


############### タイトルバー(Windows) ###############
def _onMapToplevel(event: tk.Event) -> None:
    """Toplevel が表示されたときに、タイトルバーの色を付ける"""
    if isinstance(event.widget, tk.Toplevel):
        _setTitleBar(event.widget)


def _setTitleBar(window: tk.Misc) -> None:
    """
    Windows のタイトルバーを、テーマに合わせる(暗いテーマでは黒、色のあるテーマでは背景色。Windows 11 のみ)
    """
    if platform.system() != "Windows":
        return
    try:
        window.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id()) or window.winfo_id()
        dwm = ctypes.windll.dwmapi
        dark = ctypes.c_int(1 if is_dark() else 0)
        dwm.DwmSetWindowAttribute(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(dark), ctypes.sizeof(dark))
        if is_default():
            value = DWMWA_COLOR_DEFAULT
        else:
            red, green, blue = window.winfo_rgb(color("bg"))
            value = (red >> 8) | ((green >> 8) << 8) | ((blue >> 8) << 16)
        caption = ctypes.c_uint(value)
        dwm.DwmSetWindowAttribute(hwnd, DWMWA_CAPTION_COLOR, ctypes.byref(caption), ctypes.sizeof(caption))
        # 枠を描き直す(SWP_NOSIZE | SWP_NOMOVE | SWP_NOZORDER | SWP_FRAMECHANGED | SWP_NOACTIVATE)
        ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0020 | 0x0010)
    except Exception:
        pass


############### 自作のメニューバー ###############
class _MenuArrowHook:
    """
    開いているメニュー(Windows のポップアップのメニュー)の中で押された、左右の矢印キーを受け取る(Windows のみ)。
    ウィンドウのメニューバーと同じように、左右のキーで隣のメニューに移るために使う
    (ポップアップのメニューは、開いている間、キーを tkinter に渡さないので、Windows の、メニューの中のメッセージを見る仕組みを使う)。
    on_arrow(step): 隣のメニューに移るときに呼ぶ関数(step: -1 = 左、1 = 右)
    """

    _WH_MSGFILTER, _MSGF_MENU, _WM_KEYDOWN, _VK_LEFT, _VK_RIGHT = -1, 2, 0x0100, 0x25, 0x27
    _MN_GETHMENU, _MF_BYPOSITION, _MF_POPUP, _MF_HILITE = 0x01E1, 0x0400, 0x0010, 0x0080

    def __init__(self, on_arrow: Callable[[int], None]):
        """on_arrow: 隣のメニューに移るときに呼ぶ関数。(作るだけ。install で受け取り始める)"""
        self._on_arrow = on_arrow
        self._hook = None
        self._proc = None
        self._user32 = None
        # いちばん上の項目を選ぶための、Windows のタイマー(番号、呼ばれる関数、残りの回数、キーの送り先)
        self._timer = 0
        self._timer_proc = None
        self._timer_tries = 0
        self._timer_hwnd = 0

    def install(self, select_first_hwnd: int = 0) -> None:
        """
        受け取り始める(Windows 以外と、用意できなかった場合は、何もしない)。
        select_first_hwnd: 0 以外なら、メニューが開いた後に、いちばん上の項目を選んだ状態にする(キーの知らせを送る先の、ウィンドウのハンドル)
        """
        if platform.system() != "Windows" or self._hook is not None:
            return
        try:
            from ctypes import wintypes

            user32 = ctypes.WinDLL("user32", use_last_error=True)
            lresult = ctypes.c_ssize_t
            hookproc = ctypes.WINFUNCTYPE(lresult, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
            user32.SetWindowsHookExW.argtypes = [ctypes.c_int, hookproc, wintypes.HINSTANCE, wintypes.DWORD]
            user32.SetWindowsHookExW.restype = ctypes.c_void_p
            user32.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
            user32.CallNextHookEx.restype = lresult
            user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
            user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
            user32.SendMessageW.restype = ctypes.c_void_p
            user32.GetMenuItemCount.argtypes = [ctypes.c_void_p]
            user32.GetMenuState.argtypes = [ctypes.c_void_p, wintypes.UINT, wintypes.UINT]
            user32.GetMenuState.restype = wintypes.UINT
            user32.GetSubMenu.argtypes = [ctypes.c_void_p, ctypes.c_int]
            user32.GetSubMenu.restype = ctypes.c_void_p
            self._enum_proc_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
            user32.EnumThreadWindows.argtypes = [wintypes.DWORD, self._enum_proc_type, wintypes.LPARAM]
            self._user32 = user32
            self._msg_pointer = ctypes.POINTER(wintypes.MSG)
            self._proc = hookproc(self._onMessage)
            self._hook = user32.SetWindowsHookExW(
                self._WH_MSGFILTER, self._proc, None, ctypes.windll.kernel32.GetCurrentThreadId()
            )
            if select_first_hwnd:
                # メニューが開いている間も、Windows のタイマーは呼ばれる。開いたのを確かめてから、下の矢印キーの知らせを送る
                # (開く前に送ると、メニューに届かないことがある)
                timer_proc_type = ctypes.WINFUNCTYPE(None, wintypes.HWND, wintypes.UINT, ctypes.c_size_t, wintypes.DWORD)
                user32.SetTimer.argtypes = [wintypes.HWND, ctypes.c_size_t, wintypes.UINT, timer_proc_type]
                user32.SetTimer.restype = ctypes.c_size_t
                user32.KillTimer.argtypes = [wintypes.HWND, ctypes.c_size_t]
                user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
                self._timer_hwnd = select_first_hwnd
                self._timer_tries = 50
                self._timer_proc = timer_proc_type(self._onTimer)
                self._timer = user32.SetTimer(None, 0, 10, self._timer_proc)
        except Exception:
            self._hook = None

    def _stopTimer(self) -> None:
        """いちばん上の項目を選ぶためのタイマーを止める"""
        if self._timer:
            try:
                self._user32.KillTimer(None, self._timer)
            except Exception:
                pass
        self._timer = 0

    def _onTimer(self, hwnd: int, message: int, timer_id: int, time: int) -> None:
        """メニューが開いていて、どの項目も選んでいなければ、下の矢印キーの知らせを送る(Windows のタイマーから呼ばれる。引数は使わない)"""
        try:
            self._timer_tries -= 1
            menus = self._openMenus()
            if not menus and self._timer_tries > 0:
                return
            self._stopTimer()
            if len(menus) == 1 and not self._hasSelection(menus[0]):
                self._user32.PostMessageW(self._timer_hwnd, self._WM_KEYDOWN, 0x28, 0)
        except Exception:
            self._stopTimer()

    def _hasSelection(self, menu: int) -> bool:
        """そのメニューの中に、選んでいる項目があるか"""
        for position in range(max(self._user32.GetMenuItemCount(menu), 0)):
            state = self._user32.GetMenuState(menu, position, self._MF_BYPOSITION)
            if state != 0xFFFFFFFF and state & self._MF_HILITE:
                return True
        return False

    def remove(self) -> None:
        """受け取るのをやめる"""
        self._stopTimer()
        self._timer_proc = None
        if self._hook:
            try:
                self._user32.UnhookWindowsHookEx(self._hook)
            except Exception:
                pass
        self._hook = None
        self._proc = None

    def _onMessage(self, code: int, wparam: int, lparam: int) -> int:
        """メニューの中のメッセージを見る(Windows から呼ばれる)。隣のメニューに移る左右のキーなら、メニューを閉じて、キーは渡さない"""
        try:
            if code == self._MSGF_MENU:
                message = ctypes.cast(lparam, self._msg_pointer).contents
                if message.message == self._WM_KEYDOWN and message.wParam in (self._VK_LEFT, self._VK_RIGHT):
                    step = self._step(message.wParam)
                    if step:
                        self._on_arrow(step)
                        self._user32.EndMenu()
                        return 1
        except Exception:
            pass
        return self._user32.CallNextHookEx(None, code, wparam, lparam)

    def _openMenus(self) -> list:
        """開いているメニュー(入れ子で開いているものを含む)の、Windows でのハンドルの一覧"""
        menus = []

        def collect(hwnd: int, _: int) -> bool:
            name = ctypes.create_unicode_buffer(16)
            ctypes.windll.user32.GetClassNameW(hwnd, name, 16)
            if name.value == "#32768" and ctypes.windll.user32.IsWindowVisible(hwnd):
                menu = self._user32.SendMessageW(hwnd, self._MN_GETHMENU, 0, 0)
                if menu:
                    menus.append(menu)
            return True

        self._user32.EnumThreadWindows(ctypes.windll.kernel32.GetCurrentThreadId(), self._enum_proc_type(collect), 0)
        return menus

    def _step(self, key: int) -> int:
        """
        左右のキーで、隣のメニューに移るか(-1: 左へ、1: 右へ、0: 移らない。キーは、メニューにそのまま渡す)。
        ウィンドウのメニューバーと同じ: 入れ子のメニューを開いている間の左は、入れ子を閉じるだけ。
        入れ子のメニューを持つ項目を選んでいる間の右は、入れ子を開くだけ
        """
        menus = self._openMenus()
        if not menus:
            return 0
        if key == self._VK_LEFT:
            return -1 if len(menus) == 1 else 0
        for menu in menus:
            for position in range(max(self._user32.GetMenuItemCount(menu), 0)):
                state = self._user32.GetMenuState(menu, position, self._MF_BYPOSITION)
                if state == 0xFFFFFFFF or not state & self._MF_HILITE or not state & self._MF_POPUP:
                    continue
                # 選んでいる項目が、入れ子のメニューを持つ: まだ開いていなければ、右のキーは、それを開く
                if self._user32.GetSubMenu(menu, position) not in menus:
                    return 0
        return 1


class ThemedMenuBar:
    """
    デフォルト以外のテーマで使う、テーマの色のメニューバー
    (Windows のメニューバーは色を変えられないため、ウィンドウの中に同じメニューを並べる)
    menu: ウィンドウのメニューバー(tk.Menu)。各項目のメニューを、クリックした位置に開く
    """

    def __init__(self, root: tk.Tk, menu: tk.Menu, before: tk.Widget):
        """
        root: メニューバーを置くウィンドウ、menu: ウィンドウのメニューバー
        before: この部品の上に、自作のメニューバーを置く(pack の before)
        (作るだけで、表示はしない。update() で切り替える)
        """
        self.root = root
        self.menu = menu
        self.before = before
        self.frame = ttk.Frame(root, style="MenuBar.TFrame")
        self.labels = []
        # labels と同じ並びの、各項目のメニュー
        self.submenus = []
        # 開いているメニューの番号(labels の中での位置。開いていなければ None)と、左右のキーで次に開くメニューへの移動量
        self.open_index = None
        self._arrow_step = 0
        self._arrow_hook = _MenuArrowHook(self._onArrow)
        for index in range(menu.index("end") + 1):
            if menu.type(index) != "cascade":
                continue
            submenu = root.nametowidget(menu.entrycget(index, "menu"))
            text = menu.entrycget(index, "label")
            underline = int(menu.entrycget(index, "underline"))
            label = ttk.Label(self.frame, text=text, underline=underline, style="MenuBar.TLabel")
            label.pack(side="left")
            label.bind("<Enter>", lambda e: e.widget.state(["active"]))
            label.bind("<Leave>", lambda e: e.widget.state(["!active"]))
            label.bind("<Button-1>", lambda e, submenu=submenu: self._post(e.widget, submenu))
            self.labels.append(label)
            self.submenus.append(submenu)
            if 0 <= underline < len(text):
                # Alt + 下線の付いたキー で開く(ウィンドウのメニューバーと同じ操作)
                key = text[underline]
                for name in {key.lower(), key.upper()}:
                    root.bind(
                        f"<Alt-KeyPress-{name}>",
                        lambda e, label=label, submenu=submenu: self._postByKey(label, submenu),
                        add="+",
                    )

    def _postByKey(self, label: ttk.Label, submenu: tk.Menu) -> str | None:
        """Alt + キーで、メニューを開く。開いた場合は "break"(ほかの処理に渡さない)、何もしない場合は None"""
        # ウィンドウのメニューバーを使っている間(デフォルトのテーマ)は、Windows が開くので何もしない
        if not self.frame.winfo_manager():
            return None
        self._post(label, submenu, select_first=True)
        return "break"

    def _onArrow(self, step: int) -> None:
        """開いているメニューの中で、隣のメニューに移る左右のキーが押された(step: -1 = 左、1 = 右)。今のメニューが閉じた後に、隣を開く"""
        self._arrow_step = step

    def _post(self, label: ttk.Label, submenu: tk.Menu, select_first: bool = False) -> None:
        """
        項目(label)の下に、そのメニューを開く(閉じるまで戻らない)。
        開いている間に、左右の矢印キーを押すと、隣の項目のメニューに移る(端からは、反対の端に回る。ウィンドウのメニューバーと同じ)。
        select_first: 開いたときに、いちばん上の項目を選んだ状態にする(キーボードで開いたとき)
        """
        while True:
            self._arrow_step = 0
            self._postOne(label, submenu, select_first)
            if not self._arrow_step or label not in self.labels:
                return
            index = (self.labels.index(label) + self._arrow_step) % len(self.labels)
            label, submenu, select_first = self.labels[index], self.submenus[index], True

    def _postOne(self, label: ttk.Label, submenu: tk.Menu, select_first: bool) -> None:
        """項目(label)の下に、そのメニューを 1 つ開く(閉じるまで戻らない)"""
        label.state(["active"])
        self.open_index = self.labels.index(label) if label in self.labels else None
        toplevel = 0
        if select_first and platform.system() == "Windows":
            try:
                toplevel = ctypes.windll.user32.GetParent(self.root.winfo_id())
            except Exception:
                toplevel = 0
        self._arrow_hook.install(select_first_hwnd=toplevel)
        try:
            submenu.tk_popup(label.winfo_rootx(), label.winfo_rooty() + label.winfo_height())
        finally:
            self._arrow_hook.remove()
            self.open_index = None
            submenu.grab_release()
            label.state(["!active"])

    def height(self) -> int:
        """
        表示しているときの高さ(表示していないときは 0)
        """
        return self.frame.winfo_reqheight() if self.frame.winfo_manager() else 0

    def update(self) -> None:
        """
        今のテーマに合わせて、自作のメニューバーとウィンドウのメニューバーを切り替える
        """
        if is_default():
            self.frame.pack_forget()
            self.root.config(menu=self.menu)
        else:
            self.root.config(menu="")
            if not self.frame.winfo_manager():
                self.frame.pack(side="top", fill="x", before=self.before)
