#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import tkinter as tk
import tkinter.ttk as ttk
# from logging import getLogger, DEBUG, NullHandlerxx


class PokeConDialogue(object):
    """
    コマンドやメニューから開く、入力用のダイアログ(作ると表示され、閉じられるまで待つ。結果は ret_value で受け取る)
    """

    def __init__(
        self,
        parent: tk.Toplevel,
        title: str,
        message: int | str | list,
        desc: str | None = None,
        mode: int = 0,
        pos: int = 2,
    ):
        """
        pokecon用ダイアログ生成関数(注意:mode=0と1でmessageの取り扱いが大きく異なる。)
        parent | tk.Toplevel: ダイアログにするウィンドウ(呼び出し側で作って渡す。親のウィンドウの中央に表示する)
        desc | str: ダイアログの上部に表示する説明(Noneのとき、タイトルを表示する)
        mode | int: 0のときEntryのみ、1のとき6種類のwidgetに対応
        pos | int: OK/Cancelの位置(1のときTOP、2のときBOTTOM、3のときBOTH)
        title | str: タイトル
        message | mode=0の場合 : int/str/list: Entryのラベル、mode=1の場合 : list[widget, widget, ...]: widgetごとの設定をリスト化したもの
        widget | list : widgetごとの設定(ウィジェットの種類によってリストの中身は異なる。以下を参照。)
        checkbox/entryの場合 : [type, subtitle, init] (例) ["check", "Check(例)", True]、["ENTRY", "Entry(例)", "初期値"]
        combobox/radiobutton/spinboxの場合 : [type, subtitle, selectlist, init] (例) ["Combo", "Combo(例)", ["hello", "world"], "hello"]、["RADIO", "Radio(例)", ["dog", "cat"],"dog"]、["Spin", "Spin(例)", list(map(str, range(10))), "3"]
        scaleの場合 : [type, subtitle, min, max, init, digit] (例) ["Scale", "scale(例)", 0, 100, 50.1, 2]
        type | str: widgetの種類(check/combo/entry/radio/spin/scaleのいずれか。大文字小文字は問わない)
        subtitle | str : widgetのタイトル
        init | checkboxの場合bool,scaleの場合int/float,その他str : 初期値
        selectlist | list : 項目のリスト
        min/max | int/float : scaleの最小値と最大値
        digit | int : 有効桁数
        return : なし
        """
        self._ls = None
        self.isOK = None

        self.message_dialogue = parent
        self.message_dialogue.title(title)
        self.message_dialogue.attributes("-topmost", True)
        self.message_dialogue.protocol("WM_DELETE_WINDOW", self.close_window)

        self.main_frame = tk.Frame(self.message_dialogue)

        description = desc if desc is not None else title
        self.description_label = ttk.Label(self.main_frame, text=description, anchor="center")
        self.description_label.grid(column=0, columnspan=2, ipadx="10", ipady="10", row=0, sticky="nsew")

        cnt = 1
        if pos in [1, 3]:
            self.result = ttk.Frame(self.main_frame)
            self.OK = ttk.Button(self.result, command=self.ok_command)
            self.OK.configure(text="OK")
            self.OK.grid(column=0, row=1, padx=5, pady=5)
            self.Cancel = ttk.Button(self.result, command=self.cancel_command)
            self.Cancel.configure(text="Cancel")
            self.Cancel.grid(column=1, row=1, sticky="ew", padx=5, pady=5)
            self.result.grid(column=0, columnspan=2, pady=5, row=cnt, sticky="ew")
            self.result.grid_anchor("center")
            cnt += 1

        self.inputs = ttk.Frame(self.main_frame)

        self.dialogue_ls = {}
        x = self.message_dialogue.master.winfo_x()
        w = self.message_dialogue.master.winfo_width()
        y = self.message_dialogue.master.winfo_y()
        h = self.message_dialogue.master.winfo_height()
        w_ = self.message_dialogue.winfo_width()
        h_ = self.message_dialogue.winfo_height()
        self.message_dialogue.geometry(f"+{int(x + w / 2 - w_ / 2)}+{int(y + h / 2 - h_ / 2)}")

        if mode == 0:
            self.mode0(message)
        else:
            self.mode1(message)

        self.inputs.grid(column=0, columnspan=2, ipadx="10", ipady="10", row=cnt, sticky="nsew")
        self.inputs.grid_anchor("center")
        cnt += 1

        if pos in [2, 3]:
            self.result2 = ttk.Frame(self.main_frame)
            self.OK2 = ttk.Button(self.result2, command=self.ok_command)
            self.OK2.configure(text="OK")
            self.OK2.grid(column=0, row=1, padx=5, pady=5)
            self.Cancel2 = ttk.Button(self.result2, command=self.cancel_command)
            self.Cancel2.configure(text="Cancel")
            self.Cancel2.grid(column=1, row=1, sticky="ew", padx=5, pady=5)
            self.result2.grid(column=0, columnspan=2, pady=5, row=cnt, sticky="ew")
            self.result2.grid_anchor("center")

        self.main_frame.pack()
        self.message_dialogue.master.wait_window(self.message_dialogue)

    def mode0(self, message: int | str | list) -> None:
        """
        mode=0 の入力欄を作る: 項目ごとに、ラベルと Entry を1行ずつ並べる
        message: 項目名(ラベルの文字)、またはそのリスト
        """
        if type(message) is not list:
            message = [message]
        n = len(message)

        for i in range(n):
            self.dialogue_ls[message[i]] = tk.StringVar()
            label = ttk.Label(self.inputs, text=message[i])
            entry = ttk.Entry(self.inputs, textvariable=self.dialogue_ls[message[i]])
            label.grid(column=0, row=i, sticky="nsew", padx=3, pady=3)
            entry.grid(column=1, row=i, sticky="nsew", padx=3, pady=3)

    def mode1(self, dialogue_list: list) -> None:
        """
        mode=1 の入力欄を作る: widgetごとの設定のリストから、Check / Combo / Entry / Radio / Spin / Scale を並べる
        dialogue_list: widgetごとの設定のリスト(__init__ の message を参照。["Next"] を入れると、次の列に移る)
        """
        n = len(dialogue_list)
        frame = []

        scale_label_list = []  # scaleの値を表示するlabelを格納するリスト
        scale_index_list = []  # scaleが何番目のwidgetなのかを格納するリスト
        scale_digit_list = []  # scaleの有効桁数を格納するリスト

        def change_scale_value(event: str | None = None) -> None:  # scaleのバーを動かしたときにlabelの値を変更するための関数
            """すべての Scale の値を、有効桁数で丸めて、横のラベルに表示する。event: 使わない(Scale から渡される値)"""
            for i, (index, fmt) in enumerate(zip(scale_index_list, scale_digit_list)):
                if fmt != 0:
                    val = round(self.dialogue_ls[dialogue_list[index][1]].get(), fmt)
                    scale_label_list[i]["text"] = "%s" % val
                    self.dialogue_ls[dialogue_list[index][1]].set(val)
                else:
                    scale_label_list[i]["text"] = "%s" % self.dialogue_ls[dialogue_list[index][1]].get()

        column0 = 0
        row0 = 0
        for i in range(n):
            if dialogue_list[i][0].casefold() == "next".casefold():
                column0 += 1
                row0 = 0
                frame.append(None)
            else:
                # widgetはすべてframeの中に入れる。scaleの場合、値を示すlabelもフレームの中に入れる。
                frame.append(ttk.LabelFrame(self.inputs, text=dialogue_list[i][1]))

                # Checkbox
                if dialogue_list[i][0].casefold() == "check".casefold():
                    self.dialogue_ls[dialogue_list[i][1]] = tk.BooleanVar(value=dialogue_list[i][2])
                    widget = ttk.Checkbutton(frame[i], variable=self.dialogue_ls[dialogue_list[i][1]])
                    widget.grid(column=0, row=0, sticky="nsew", padx=3, pady=3)
                # Combobox
                elif dialogue_list[i][0].casefold() == "combo".casefold():
                    text_length = 10
                    for name in dialogue_list[i][2]:
                        if text_length < len(str(name)) + 5:
                            text_length = len(str(name)) + 5
                    self.dialogue_ls[dialogue_list[i][1]] = tk.StringVar(value=dialogue_list[i][3])
                    widget = ttk.Combobox(
                        frame[i],
                        values=dialogue_list[i][2],
                        textvariable=self.dialogue_ls[dialogue_list[i][1]],
                        width=text_length,
                        state="readonly",
                    )
                    widget.grid(column=0, row=0, sticky="nsew", padx=3, pady=3)
                    # widget.current(0)
                # Entry
                elif dialogue_list[i][0].casefold() == "entry".casefold():
                    self.dialogue_ls[dialogue_list[i][1]] = tk.StringVar(value=dialogue_list[i][2])
                    widget = ttk.Entry(frame[i], textvariable=self.dialogue_ls[dialogue_list[i][1]])
                    widget.grid(column=0, row=0, sticky="nsew", padx=3, pady=3)
                # Radiobutton
                elif dialogue_list[i][0].casefold() == "radio".casefold():
                    self.dialogue_ls[dialogue_list[i][1]] = tk.StringVar(value=dialogue_list[i][3])
                    for j, text0 in enumerate(dialogue_list[i][2]):
                        widget = ttk.Radiobutton(
                            frame[i], text=text0, variable=self.dialogue_ls[dialogue_list[i][1]], value=text0
                        )
                        widget.grid(column=j, row=0, sticky="nsew", padx=3, pady=3)
                # Scale
                elif dialogue_list[i][0].casefold() == "scale".casefold():
                    scale_index_list.append(i)
                    scale_digit_list.append(dialogue_list[i][5])
                    if dialogue_list[i][5] != 0:  # 浮動小数点数
                        self.dialogue_ls[dialogue_list[i][1]] = tk.DoubleVar(value=dialogue_list[i][4])
                        scale_label_list.append(
                            tk.Label(
                                frame[i],
                                width=10,
                                text="%s" % round(self.dialogue_ls[dialogue_list[i][1]].get(), dialogue_list[i][5]),
                            )
                        )
                    else:  # 整数
                        self.dialogue_ls[dialogue_list[i][1]] = tk.IntVar(value=dialogue_list[i][4])
                        scale_label_list.append(
                            tk.Label(frame[i], width=10, text="%s" % self.dialogue_ls[dialogue_list[i][1]].get())
                        )
                    widget = ttk.Scale(
                        frame[i],
                        from_=dialogue_list[i][2],
                        to=dialogue_list[i][3],
                        variable=self.dialogue_ls[dialogue_list[i][1]],
                        command=change_scale_value,
                    )
                    scale_label_list[-1].grid(column=0, row=0, sticky="nsew", padx=3, pady=3)
                    widget.grid(column=1, row=0, sticky="nsew", padx=3, pady=3)
                # Spinbox
                elif dialogue_list[i][0].casefold() == "spin".casefold():
                    self.dialogue_ls[dialogue_list[i][1]] = tk.StringVar(value=dialogue_list[i][3])
                    widget = ttk.Spinbox(
                        frame[i], values=dialogue_list[i][2], textvariable=self.dialogue_ls[dialogue_list[i][1]]
                    )
                    widget.grid(column=0, row=0, sticky="nsew", padx=3, pady=3)

                frame[i].grid(column=column0, row=row0, sticky="nsew", padx=3, pady=3)
                row0 += 1

        # widgetのサイズをフレームのサイズに合わせる
        for i in range(n):
            if dialogue_list[i][0].casefold() == "next".casefold():
                pass
            else:
                if dialogue_list[i][0].casefold() == "scale".casefold():
                    frame[i].grid_columnconfigure(0, weight=1)
                    frame[i].grid_columnconfigure(1, weight=3)
                elif dialogue_list[i][0].casefold() != "radio".casefold():
                    frame[i].grid_columnconfigure(0, weight=1)
                else:
                    pass

    def ret_value(self, need: type) -> list | dict | bool:
        """
        ダイアログの入力結果を返す
        need: 戻り値の型(list: 値を並べたリスト / dict: 項目名 -> 値 の辞書。それ以外は、メッセージを表示して list)
        戻り値: OK で閉じた場合は入力結果。Cancel や × ボタンで閉じた場合は False
        """
        if self.isOK:
            if need is dict:  # needは型なのでisinstanceは使えない
                return {k: v.get() for k, v in self.dialogue_ls.items()}
            elif need is list:  # needは型なのでisinstanceは使えない
                return self._ls
            else:
                print("Wrong arg. Try Return list.")
                return self._ls
        else:
            return False

    def close_window(self) -> None:
        """ウィンドウの × ボタン: 入力を使わずに閉じる"""
        self.message_dialogue.destroy()
        self.isOK = False

    def ok_command(self) -> None:
        """OK ボタン: 入力された値を覚えて閉じる"""
        self._ls = [v.get() for k, v in self.dialogue_ls.items()]
        self.message_dialogue.destroy()
        self.isOK = True

    def cancel_command(self) -> None:
        """Cancel ボタン: 入力を使わずに閉じる"""
        self.message_dialogue.destroy()
        self.isOK = False


# 画面に依存しない関数は services/dialogue_store.py にある(これまでの import のために、ここからも使えるようにする)
from services.dialogue_store import (  # noqa: E402,F401
    check_widget_name,
    get_setting,
    save_setting,
    generate_new_dialogue_list,
    save_dialogue_settings,
    get_settings_list,
)
