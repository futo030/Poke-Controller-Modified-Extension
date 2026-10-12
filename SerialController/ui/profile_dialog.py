#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
起動時にプロファイルを選ぶ画面
"""
from __future__ import annotations

import tkinter as tk
import tkinter.ttk as ttk
import tkinter.messagebox as tkmsg
import tkinter.simpledialog as tksimpledialog
import Constant
import Profile
from Profile import DEFAULT_PROFILE, list_profiles


def selectProfile(root: tk.Tk) -> str | None:
    """
    起動時にプロファイルを選ぶ画面を表示し、選ばれた名前を返す(キャンセルした場合はNone)
    プロファイルが1つしかない場合は、画面を出さずにその名前を返す(1つもない場合は default)
    root: メインウィンドウ(選んでいる間は隠す)
    """
    profiles = list_profiles()
    if len(profiles) == 0:
        return DEFAULT_PROFILE
    if len(profiles) == 1:
        return profiles[0]
    result = {"profile": None}
    root.withdraw()
    dialog = tk.Toplevel(root)
    dialog.title(f"{Constant.NAME} ver.{Constant.VERSION}")
    dialog.resizable(False, False)
    frame = ttk.Frame(dialog, padding="15")
    frame.pack(expand="true", fill="both")
    ttk.Label(frame, text="起動するプロファイルを選んでください。").grid(
        column="0", columnspan="3", pady=(0, 10), row="0", sticky="w"
    )
    ttk.Label(frame, text="Profile:").grid(column="0", padx=(0, 5), row="1", sticky="w")
    name = tk.StringVar(value=DEFAULT_PROFILE if DEFAULT_PROFILE in profiles else profiles[0])
    profile_cb = ttk.Combobox(frame, state="readonly", textvariable=name, values=profiles, width="30")
    profile_cb.grid(column="1", columnspan="2", row="1", sticky="ew")

    def ok(*event: tk.Event) -> None:
        """OK ボタン、または Enter キー: 選んでいる名前を結果に入れて、画面を閉じる"""
        result["profile"] = name.get()
        dialog.destroy()

    button_f = ttk.Frame(frame)
    button_f.grid(column="0", columnspan="3", pady=(15, 0), row="2", sticky="e")
    ok_button = ttk.Button(button_f, text="OK", command=ok)
    ok_button.pack(padx=(0, 5), side="left")
    ttk.Button(button_f, text="Cancel", command=dialog.destroy).pack(side="left")
    dialog.bind("<Return>", ok)
    dialog.bind("<Escape>", lambda event: dialog.destroy())
    dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
    # 画面の中央に表示する
    dialog.update_idletasks()
    x = (dialog.winfo_screenwidth() - dialog.winfo_reqwidth()) // 2
    y = (dialog.winfo_screenheight() - dialog.winfo_reqheight()) // 2
    dialog.geometry(f"+{x}+{y}")
    ok_button.focus_set()
    dialog.lift()
    root.wait_window(dialog)
    if result["profile"] is not None:
        root.deiconify()
    return result["profile"]


def selectProfileAllRunning(root: tk.Tk) -> str | None:
    """
    --auto で対象のプロファイルがすべて起動されているときの画面
    defaultで起動するか、新しいプロファイルを作ってそれで起動するかを選び、起動するプロファイル名を返す
    (キャンセルした場合はNone)
    root: メインウィンドウ(選んでいる間は隠す)
    """
    root.withdraw()
    while True:
        result = {"choice": None}
        dialog = tk.Toplevel(root)
        dialog.title(f"{Constant.NAME} ver.{Constant.VERSION}")
        dialog.resizable(False, False)
        frame = ttk.Frame(dialog, padding="15")
        frame.pack(expand="true", fill="both")
        ttk.Label(
            frame,
            text="--auto の対象のプロファイルは、すべて起動されています。\n"
            f"「{DEFAULT_PROFILE}」で起動するか、新しいプロファイルを作成するかを選んでください。\n\n"
            f"(起動中のプロファイルで起動した場合、このウィンドウで変更した設定は保存されません。\n"
            " 新しいプロファイルは、すべての設定が初期値になり、設定を保存できます。)",
        ).pack(anchor="w", pady=(0, 15))

        def choose(choice: str) -> None:
            """ボタンを押したとき: 選んだ内容("default" / "new")を結果に入れて、画面を閉じる"""
            result["choice"] = choice
            dialog.destroy()

        button_f = ttk.Frame(frame)
        button_f.pack(anchor="e")
        ttk.Button(
            button_f, text=f"{DEFAULT_PROFILE} で起動", width="18", command=lambda: choose("default")
        ).pack(padx=(0, 5), side="left")
        new_button = ttk.Button(
            button_f, text="新しいプロファイルを作成", width="24", command=lambda: choose("new")
        )
        new_button.pack(padx=(0, 5), side="left")
        ttk.Button(button_f, text="Cancel", command=dialog.destroy).pack(side="left")
        dialog.bind("<Escape>", lambda event: dialog.destroy())
        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() - dialog.winfo_reqwidth()) // 2
        y = (dialog.winfo_screenheight() - dialog.winfo_reqheight()) // 2
        dialog.geometry(f"+{x}+{y}")
        dialog.lift()
        root.wait_window(dialog)

        if result["choice"] is None:
            return None
        if result["choice"] == "default":
            root.deiconify()
            return DEFAULT_PROFILE
        # 新しいプロファイルの名前を入力する。使えない名前の場合は警告して、選ぶ画面に戻る
        name = tksimpledialog.askstring(
            "New Profile",
            "新しいプロファイルの名前を入力してください。\n(アルファベット・数字・「-」・「_」のみ)",
            parent=root,
        )
        if name is None:
            continue
        name = name.strip()
        error = Profile.check_profile_name(name)
        if error is not None:
            tkmsg.showwarning("New Profile", error)
            continue
        kind = None
        if Profile.has_uv_environment():
            # uv の環境では、起動用の bat の形を選べる
            answer = tkmsg.askyesnocancel(
                "New Profile",
                "起動用の bat ファイルを、uv の環境向けの形で作りますか?\n\n"
                f"はい: {Profile.BAT_LABELS[Profile.BAT_UV]}\n"
                f"いいえ: {Profile.BAT_LABELS[Profile.BAT_CLASSIC]}",
                parent=root,
            )
            if answer is None:
                continue
            kind = Profile.BAT_UV if answer else Profile.BAT_CLASSIC
        try:
            Profile.create_profile(name)
            bat_path = Profile.create_profile_bat(name, kind)
        except OSError as e:
            tkmsg.showerror("New Profile", f"プロファイルを作成できませんでした。\n{e}")
            continue
        tkmsg.showinfo(
            "New Profile",
            f"プロファイル「{name}」を作成しました。このプロファイルで起動します。\n\n"
            + (
                f"起動ファイル: {bat_path}"
                if bat_path is not None
                else "(同じ名前の起動ファイルがすでにあるため、起動ファイルは作成していません。)"
            ),
        )
        root.deiconify()
        return name
