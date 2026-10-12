"""
以前からの環境(PC に入っている Python と pip)から、uv の環境(.venv)への移行(0.2.x の間だけ使う。0.3.0 で消す)

更新の確認(PokeConUpdateChecker.py)から、以前からの Python で呼ばれる。尋ねてから、次の順に行う。
uv を用意する → .venv を作る → 利用者が足していたライブラリを一覧から選んでもらい、.venv に入れる
以前からの環境には、手を付けない(失敗しても、今までどおり起動できる)。
"""
from __future__ import annotations

import json
import os
import sys
import tkinter as tk
from tkinter import messagebox, ttk

from bootstrap import added_libraries, environment, uv_tool

TITLE = "uv の環境への移行"
# 「今後は尋ねない」を覚えるファイル(利用者ごとの設定と同じ場所。git の対象外)
STATE_FILE = os.path.join("SerialController", "profiles", "bootstrap.json")
OFFER = (
    "このツール専用の環境(uv と Python 3.13)に移行しますか?\n\n"
    "・リポジトリのフォルダーの中に、専用の環境(.venv)を作ります。\n"
    "・今の Python と、そこに入っているライブラリは、そのまま残ります。\n"
    "・移行した後も、今までと同じ方法で起動できます。\n"
    "・ver.0.3.0 以降は、この環境が必要になります。\n\n"
    "初回は、ダウンロードに数分かかります。"
)
REQUIRED_OFFER = (
    "新しい版が公開されていますが、更新するには、先に次の移行が必要です。\n"
    "(移行しない場合は、今の版のまま使い続けられます)\n\n"
)


def read_state(root: str) -> dict:
    try:
        with open(os.path.join(root, STATE_FILE), encoding="utf-8") as file:
            state = json.load(file)
        return state if isinstance(state, dict) else {}
    except (OSError, ValueError):
        return {}


def write_state(root: str, state: dict) -> None:
    path = os.path.join(root, STATE_FILE)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as file:
            json.dump(state, file, ensure_ascii=False, indent=2)
    except OSError:
        pass


def should_offer(root: str) -> bool:
    """移行を尋ねるか(.venv がまだなく、「今後は尋ねない」が選ばれていない)"""
    if os.path.isfile(environment.venv_python(root)) or environment.in_venv(root):
        return False
    if not os.path.isfile(os.path.join(root, "pyproject.toml")):
        return False
    return not read_state(root).get("migration_declined")


def is_dedicated_python(root: str, prefix: str | None = None) -> bool:
    """
    今の Python が、このツール専用に置かれたものか(リポジトリと同じフォルダーの中にある)。
    専用なら、入っているライブラリは、このツールのために足したものと見てよい
    """
    parent = os.path.normcase(os.path.realpath(os.path.dirname(root)))
    prefix = os.path.normcase(os.path.realpath(sys.base_prefix if prefix is None else prefix))
    try:
        return os.path.commonpath([parent, prefix]) == parent
    except ValueError:
        return False


def initial_selection(candidates: list, dedicated: bool) -> list:
    """一覧で、初めからチェックを入れておくか(スクリプトが使っているもの。専用の Python なら、すべて)"""
    return [dedicated or candidate.used_by_scripts for candidate in candidates]


def choose_libraries(parent: tk.Misc, candidates: list, dedicated: bool) -> list | None:
    """引き継ぐライブラリを選ぶ画面。選ばれた名前の一覧を返す(閉じた場合は None)"""
    window = tk.Toplevel(parent)
    window.title(TITLE)
    window.geometry("560x480")
    ttk.Label(
        window,
        text="今の環境に入っているライブラリのうち、新しい環境に引き継ぐものを選んでください。\n"
        "(自作のスクリプトが使っているものには、初めからチェックが入っています。後から足すこともできます)",
        justify="left", wraplength=530,
    ).pack(anchor="w", padx=12, pady=(12, 6))  # fmt: skip
    outer = ttk.Frame(window)
    outer.pack(fill="both", expand=True, padx=12)
    canvas = tk.Canvas(outer, highlightthickness=0)
    scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
    inner = ttk.Frame(canvas)
    inner.bind("<Configure>", lambda _: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.create_window((0, 0), window=inner, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")
    canvas.bind_all("<MouseWheel>", lambda event: canvas.yview_scroll(-event.delta // 120, "units"))
    variables = []
    for candidate, selected in zip(candidates, initial_selection(candidates, dedicated)):
        variable = tk.BooleanVar(window, value=selected)
        variables.append(variable)
        used = f"(使用: {', '.join(candidate.used_by[:3])}{' ほか' if len(candidate.used_by) > 3 else ''})"
        text = f"{candidate.name}  {used}" if candidate.used_by_scripts else candidate.name
        ttk.Checkbutton(inner, text=text, variable=variable).pack(anchor="w")
    result = {"names": None}

    def accept() -> None:
        result["names"] = [candidate.name for candidate, variable in zip(candidates, variables) if variable.get()]
        window.destroy()

    buttons = ttk.Frame(window)
    buttons.pack(fill="x", padx=12, pady=12)
    ttk.Button(buttons, text="引き継ぐ", command=accept).pack(side="right")
    ttk.Button(buttons, text="中止", command=window.destroy).pack(side="right", padx=(0, 8))
    window.protocol("WM_DELETE_WINDOW", window.destroy)
    window.lift()
    window.grab_set()
    parent.wait_window(window)
    canvas.unbind_all("<MouseWheel>")
    return result["names"]


def migrate(root: str, parent: tk.Misc) -> bool:
    """移行を行う(尋ねた後)。できたら True"""
    candidates = added_libraries.detect(root)
    names = []
    if candidates:
        names = choose_libraries(parent, candidates, is_dedicated_python(root))
        if names is None:
            return False
    try:
        uv = uv_tool.ensure(root, lambda message: messagebox.askyesno(TITLE, message, parent=parent))
        if names:
            added_libraries.write_user_requirements(root, names)
        failed = environment.sync(root, uv)
    except uv_tool.UvError as e:
        messagebox.showerror(TITLE, f"{e}\n\n今までの環境のまま起動します。", parent=parent)
        return False
    message = "移行が完了しました。このまま、新しい環境で起動します。"
    if failed:
        message += "\n\n" + environment.describe_failures(failed)
    messagebox.showinfo(TITLE, message, parent=parent)
    return True


def offer(root: str, parent: tk.Misc, required: bool = False) -> bool:
    """
    必要なら移行を尋ねて、行う。移行したら True。
    required: 新しい版の取得に、移行が必要なとき(「今後は尋ねない」を選んでいても尋ねる。断っても、その選択は変えない)
    """
    if required:
        if os.path.isfile(environment.venv_python(root)):
            return False
        return messagebox.askyesno(TITLE, REQUIRED_OFFER + OFFER, parent=parent) and migrate(root, parent)
    if not should_offer(root):
        return False
    if messagebox.askyesno(TITLE, OFFER, parent=parent):
        return migrate(root, parent)
    if not messagebox.askyesno(TITLE, "次に起動したときも、この確認を表示しますか?", parent=parent):
        write_state(root, {**read_state(root), "migration_declined": True})
    return False
