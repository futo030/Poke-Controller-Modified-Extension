#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
新しいスクリプトを作る画面(メニューの ツール > 新しい自動化スクリプトをつくる)

スクリプト名・作成者名・ファイル名・格納場所・BridgeFunctions を使うか・画像の保存先を入力してもらい、
ひな形の .py ファイルと、README.md・License.txt を作る(services/script_creator.py)。作った後の処理(一覧の更新、ファイルを開く)は、開いた側が行う。
"""
from __future__ import annotations

import tkinter as tk
import tkinter.ttk as ttk
from logging import getLogger, DEBUG, NullHandler
from typing import Callable

import Constant
import Theme
from services import script_creator
from services.script_creator import ScriptCreateError, ScriptResult, ScriptSpec

_logger = getLogger(__name__)
_logger.addHandler(NullHandler())
_logger.setLevel(DEBUG)
_logger.propagate = True

TITLE = "新しい自動化スクリプトをつくる"
# 格納場所の欄の、「フォルダーに入れない(Commands/PythonCommands の直下)」を表す文字
ROOT_FOLDER = "(直下)"
# 画像保存先の、種類の欄の文字(Template の中 / スクリプト格納場所の中)
LOCATION_LABELS = {script_creator.IN_TEMPLATE: "Template/", script_creator.IN_SCRIPT_FOLDER: "[スクリプト格納場所]/"}
ENTRY_WIDTH = 34


class ScriptCreatorWindow:
    """
    新しいスクリプトを作る画面
    """


    def __init__(
        self,
        root: tk.Tk,
        on_created: Callable[[ScriptResult], None] | None = None,
        base_dir: str = script_creator.BASE_DIR,
    ):
        """
        root: メインウィンドウ(この位置を基準に表示する)
        on_created: ファイルを作った後に呼ぶ関数(作った結果を渡す)
        base_dir: SerialController フォルダー(テスト用に変えられる)
        """
        self.root = root
        self.on_created = on_created
        self.base_dir = base_dir
        # 画像の保存先を、ファイル名に合わせて自動で入れているか(利用者が書き換えたら、合わせるのをやめる)
        self._template_follows = True

        self.window = tk.Toplevel(root)
        self.window.title(TITLE)
        self.window.resizable(False, False)
        root_geometry = root.geometry().split("+")
        self.window.geometry("%+d%+d" % (120 + int(root_geometry[1]), 100 + int(root_geometry[2])))
        self.window.bind("<Escape>", lambda event: self.close())
        self.window.bind("<Return>", lambda event: self.create())

        body = ttk.Frame(self.window, padding=12)
        body.pack(fill="both", expand=True)
        body.columnconfigure(2, weight=1)
        muted = Theme.color("muted")

        def row(index: int, label: str, note: str) -> int:
            """1 項目分の見出しと、その下の説明を置く。入力欄を置く行の番号を返す"""
            ttk.Label(body, text=label).grid(column=0, row=index * 2, sticky="w", padx=(0, 10), pady=(6, 0))
            ttk.Label(body, text=note, foreground=muted).grid(column=1, columnspan=2, row=index * 2 + 1, sticky="w", pady=(0, 2))
            return index * 2

        # スクリプト名
        line = row(0, "スクリプト名:", "コマンドの一覧に表示する名前です(日本語も使えます)。")
        self.name = tk.StringVar()
        self.name_entry = ttk.Entry(body, textvariable=self.name, width=ENTRY_WIDTH)
        self.name_entry.grid(column=1, columnspan=2, row=line, sticky="ew", pady=(6, 0))
        # 作成者名
        line = row(1, "作成者名:", "スクリプト・README.md・License.txt に書く名前です。空にすると「(名前)」と書いておきます。")
        # 前に作ったときの作成者名を、初めの値にする(アプリケーションを起動し直しても、残る)
        self.author = tk.StringVar(value=script_creator.load_author(base_dir))
        self.author_entry = ttk.Entry(body, textvariable=self.author, width=ENTRY_WIDTH)
        self.author_entry.grid(column=1, columnspan=2, row=line, sticky="ew", pady=(6, 0))
        # ファイル名
        line = row(2, "ファイル名:", "半角の英数字と「-」「_」だけが使えます。")
        self.file_name = tk.StringVar()
        file_f = ttk.Frame(body)
        file_f.grid(column=1, columnspan=2, row=line, sticky="ew", pady=(6, 0))
        self.file_name_entry = ttk.Entry(file_f, textvariable=self.file_name, width=ENTRY_WIDTH - 5)
        self.file_name_entry.pack(side="left", fill="x", expand=True)
        ttk.Label(file_f, text=".py").pack(side="left", padx=(2, 0))
        self.file_name.trace_add("write", self._onFileNameChanged)
        # 格納場所
        line = row(3, "スクリプト格納場所:", "Commands/PythonCommands の中のフォルダーです。新しい名前を入力すると、作ります。")
        self.folder = tk.StringVar(value=ROOT_FOLDER)
        self.folder_cb = ttk.Combobox(
            body, textvariable=self.folder, width=ENTRY_WIDTH - 3,
            values=[ROOT_FOLDER] + script_creator.script_folders(base_dir),
        )
        self.folder_cb.grid(column=1, columnspan=2, row=line, sticky="ew", pady=(6, 0))
        # BridgeFunctions
        line = row(4, "BridgeFunctions の使用:", "Poke-Controller Modified でも同じスクリプトを動かすための、橋渡し関数です。")
        self.use_bridge = tk.BooleanVar(value=False)
        bridge_f = ttk.Frame(body)
        bridge_f.grid(column=1, columnspan=2, row=line, sticky="w", pady=(6, 0))
        self.bridge_yes = ttk.Radiobutton(bridge_f, text="使用する (Y)", value=True, variable=self.use_bridge)
        self.bridge_yes.pack(side="left")
        self.bridge_no = ttk.Radiobutton(bridge_f, text="使用しない (N)", value=False, variable=self.use_bridge)
        self.bridge_no.pack(side="left", padx=(12, 0))
        # 画像保存先
        line = row(
            5, "画像保存先:",
            "テンプレート画像を置くフォルダーです。空にすると、画像を使わないスクリプトを作ります。\n"
            "BridgeFunctions を使用する場合は、スクリプト格納場所の中にも置けます。",
        )
        self.template_folder = tk.StringVar()
        template_f = ttk.Frame(body)
        template_f.grid(column=1, columnspan=2, row=line, sticky="ew", pady=(6, 0))
        self.location = tk.StringVar(value=LOCATION_LABELS[script_creator.IN_TEMPLATE])
        self.location_cb = ttk.Combobox(
            template_f, textvariable=self.location, values=list(LOCATION_LABELS.values()), state="disabled", width=19
        )
        self.location_cb.pack(side="left", padx=(0, 2))
        self.location_cb.bind("<<ComboboxSelected>>", lambda event: self._onLocationChanged())
        self.template_cb = ttk.Combobox(
            template_f, textvariable=self.template_folder, width=ENTRY_WIDTH - 22,
            values=script_creator.template_folders(base_dir),
        )
        self.template_cb.pack(side="left", fill="x", expand=True)
        # 利用者が書き換えたら、ファイル名に合わせるのをやめる
        self.template_cb.bind("<KeyRelease>", lambda event: self._stopFollowing())
        self.template_cb.bind("<<ComboboxSelected>>", lambda event: self._stopFollowing())

        # 作るファイルの場所と、入力の誤り
        self.preview = tk.StringVar()
        ttk.Label(body, textvariable=self.preview, foreground=muted, wraplength=470, justify="left").grid(
            column=0, columnspan=3, row=12, sticky="w", pady=(10, 0)
        )
        self.message = tk.StringVar()
        ttk.Label(body, textvariable=self.message, foreground=Theme.color("danger"), wraplength=470, justify="left").grid(
            column=0, columnspan=3, row=13, sticky="w", pady=(4, 0)
        )
        buttons = ttk.Frame(body)
        buttons.grid(column=0, columnspan=3, row=14, sticky="e", pady=(10, 0))
        self.create_button = ttk.Button(buttons, text="作成", width=10, command=self.create)
        self.create_button.pack(side="left")
        ttk.Button(buttons, text="キャンセル", width=10, command=self.close).pack(side="left", padx=(6, 0))

        self.use_bridge.trace_add("write", lambda *args: self._onBridgeChanged())
        for variable in (self.name, self.author, self.file_name, self.folder, self.template_folder, self.use_bridge, self.location):
            variable.trace_add("write", lambda *args: self._updatePreview())
        self._updatePreview()
        self.name_entry.focus_set()
        _logger.debug("Create script creator window")

    # ---------------------------------------------------------------- 入力

    def _onFileNameChanged(self, *args: object) -> None:
        """ファイル名を書き換えたとき: 画像の保存先を、同じ名前にする(利用者が、保存先を書き換えるまで)"""
        if self._template_follows:
            self.template_folder.set(self.file_name.get().strip())

    def _stopFollowing(self) -> None:
        """画像の保存先を、利用者が書き換えたとき: ファイル名に合わせるのをやめる(ファイル名と同じ間は、続ける)"""
        self._template_follows = self.template_folder.get().strip() == self.file_name.get().strip()

    def templateLocation(self) -> str:
        """画像保存先の種類(script_creator.IN_TEMPLATE / IN_SCRIPT_FOLDER)"""
        labels = {label: location for location, label in LOCATION_LABELS.items()}
        return labels.get(self.location.get(), script_creator.IN_TEMPLATE)

    def _onBridgeChanged(self) -> None:
        """BridgeFunctions の使用を切り替えたとき: 使用する場合だけ、画像保存先の種類を選べるようにする(使用しない場合は Template)"""
        if self.use_bridge.get():
            self.location_cb.configure(state="readonly")
        else:
            self.location.set(LOCATION_LABELS[script_creator.IN_TEMPLATE])
            self.location_cb.configure(state="disabled")
            self._onLocationChanged()

    def _onLocationChanged(self) -> None:
        """画像保存先の種類を変えたとき: フォルダーの候補を、その場所のものにする(スクリプト格納場所の中は、候補なし)"""
        in_template = self.templateLocation() == script_creator.IN_TEMPLATE
        self.template_cb["values"] = script_creator.template_folders(self.base_dir) if in_template else []

    def spec(self) -> ScriptSpec:
        """入力されている内容"""
        folder = self.folder.get().strip()
        return ScriptSpec(
            name=self.name.get(),
            author=self.author.get(),
            file_name=self.file_name.get(),
            folder="" if folder == ROOT_FOLDER else folder,
            use_bridge=bool(self.use_bridge.get()),
            template_folder=self.template_folder.get(),
            template_location=self.templateLocation(),
        ).normalized()

    def _updatePreview(self) -> None:
        """入力に合わせて、作るファイルの場所(と、新しく作るフォルダー)を表示する。誤りの表示は消す"""
        self.message.set("")
        self.preview.set("\n".join(script_creator.preview_lines(self.spec(), self.base_dir)))

    # ---------------------------------------------------------------- 作成

    def create(self) -> None:
        """作成: 入力を確かめて、ファイルを作る。作れないときは、理由を表示して、画面を残す"""
        try:
            result = script_creator.create_script(self.spec(), self.base_dir, app_version=Constant.VERSION)
        except ScriptCreateError as error:
            self.message.set(str(error))
            return
        script_creator.save_author(self.author.get(), self.base_dir)
        self.window.destroy()
        if self.on_created is not None:
            self.on_created(result)

    def isOpen(self) -> bool:
        """ウィンドウが開いているか"""
        return bool(self.window.winfo_exists())

    def lift(self) -> None:
        """ウィンドウを前面に出す"""
        self.window.deiconify()
        self.window.lift()
        self.window.focus_force()

    def close(self) -> None:
        """キャンセル: 何も作らずに閉じる"""
        self.window.destroy()
        _logger.debug("Close script creator window")
