#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
import tkinter as tk
import tkinter.ttk as ttk
import tkinter.messagebox as tkmsg
import tkinter.scrolledtext as st
import platform
import Constant
import pkg_resources

# ソースコードの見た目がよくないので、こっちで定義する。
QUESTION_TITLE = '''--------------------------質問をする際の注意事項--------------------------
・質問の前に自分なりにドキュメントを読むなど各自調査を実施してください。
・項目すべてを記入してください。(空白がある場合、OKを押しても何も起きません。)
・個人を誹謗中傷するような記述はしないでください。'''


class PokeConQuestionDialogue(object):
    """
    pokeconに対する問い合わせ用文章を出力する
    """

    def __init__(self, parent, command=None):
        self._ls = None
        self.isOK = None

        message = ["プログラム名：", "制作者様：", "質問内容(経緯などは簡潔に)", "試したこと(詳しく)"]
        title = QUESTION_TITLE

        # 最終実行コマンドから情報取得
        try:
            program_name = command.NAME
        except:
            program_name = ""
        try:
            program_name = program_name + " (" + command.FILENAME + ")"
        except:
            pass
        try:
            developer_name = command.DEVELOPER
        except:
            developer_name = ""
        self.message_dialogue = parent
        self.message_dialogue.title("Poke-Controller Modified Question Template Maker")
        self.message_dialogue.attributes("-topmost", True)
        self.message_dialogue.protocol("WM_DELETE_WINDOW", self.close_window)

        self.main_frame = tk.Frame(self.message_dialogue)
        self.inputs = ttk.Frame(self.main_frame)

        self.title_label = ttk.Label(self.main_frame, text=title, anchor='center')
        self.title_label.grid(column=0, columnspan=2, ipadx='10', ipady='10', row=0, sticky='nsew')

        self.dialogue_ls = {}
        if type(message) is not list:
            message = [message]
        n = len(message)
        x = self.message_dialogue.master.winfo_x()
        w = self.message_dialogue.master.winfo_width()
        y = self.message_dialogue.master.winfo_y()
        h = self.message_dialogue.master.winfo_height()
        w_ = self.message_dialogue.winfo_width()
        h_ = self.message_dialogue.winfo_height()
        self.message_dialogue.geometry(f"+{int(x+w/2-w_/2)}+{int(y+h/2-h_/2)}")

        self.box0 = tk.StringVar(value=program_name)
        self.label0 = ttk.Label(self.inputs, text=message[0])
        self.entry0 = ttk.Entry(self.inputs, textvariable=self.box0)
        self.label0.grid(column=0, row=0, sticky='nsew', padx=3, pady=3)
        self.entry0.grid(column=1, row=0, sticky='nsew', padx=3, pady=3)

        self.box1 = tk.StringVar(value=developer_name)
        self.label1 = ttk.Label(self.inputs, text=message[1])
        self.entry1 = ttk.Entry(self.inputs, textvariable=self.box1)
        self.label1.grid(column=0, row=1, sticky='nsew', padx=3, pady=3)
        self.entry1.grid(column=1, row=1, sticky='nsew', padx=3, pady=3)

        self.label2 = ttk.Label(self.inputs, text=message[2])
        self.entry2 = st.ScrolledText(self.inputs, width=50, height=10)
        self.label2.grid(column=0, row=2, sticky='nsew', padx=3, pady=3)
        self.entry2.grid(column=1, row=2, sticky='nsew', padx=3, pady=3)

        self.label3 = ttk.Label(self.inputs, text=message[3])
        self.entry3 = st.ScrolledText(self.inputs, width=50, height=10)
        self.label3.grid(column=0, row=3, sticky='nsew', padx=3, pady=3)
        self.entry3.grid(column=1, row=3, sticky='nsew', padx=3, pady=3)

        self.inputs.grid(column=0, columnspan=2, ipadx='10', ipady='10', row=1, sticky='nsew')
        self.inputs.grid_anchor('center')
        self.result = ttk.Frame(self.main_frame)
        self.OK = ttk.Button(self.result, command=self.ok_command)
        self.OK.configure(text='OK')
        self.OK.grid(column=0, row=1)
        self.Cancel = ttk.Button(self.result, command=self.cancel_command)
        self.Cancel.configure(text='Cancel')
        self.Cancel.grid(column=1, row=1, sticky='ew')
        self.result.grid(column=0, columnspan=2, pady=5, row=2, sticky='ew')
        self.result.grid_anchor('center')
        self.main_frame.pack()
        self.message_dialogue.master.wait_window(self.message_dialogue)

    def output_text(self):
        if self.isOK:
            txt = '---------------------------ここからコピペ---------------------------\n'
            txt += f'■プログラム名\n"{self._ls[0]}\n'
            txt += f'■製作者様\n{self._ls[1]}\n'
            txt += f'■使用ツール\n{Constant.NAME} {Constant.VERSION}\n'

            if platform.system() == 'Darwin':
                # MacOS
                txt += f'■OS\n{platform.mac_ver()}(Mac)\n'
            else:
                txt += f'■OS\n{platform.platform()}\n'
            txt += f'■Python version\n{sys.version.split(" ")[0]}\n'
            txt += f'■質問内容(詳しくご記述ください。)\n{self._ls[2]}\n'
            txt += f'■試したこと(詳しくご記述ください。)\n{self._ls[3]}\n'
            txt += '---------------------------ここまでコピペ---------------------------'
            print(txt)
            checktext = "添付資料を準備してください。(以下は一例です。)\n"\
                        "・動作の動画\n"\
                        "・Poke-Conのログ\n"\
                        "・コマンドプロンプト(コンソール)の画面\nエラーが十分に出力されていることをご確認ください。"
            tkmsg.showinfo("注意", checktext)

    def close_window(self):
        self.message_dialogue.destroy()
        self.isOK = False

    def ok_command(self):
        self._ls = [self.box0.get(), self.box1.get(), self.entry2.get("1.0", "end-1c"), self.entry3.get("1.0", "end-1c")]
        flag = True
        for text in self._ls:
            if text == "":
                flag = False
        if flag:
            self.message_dialogue.destroy()
            self.isOK = True

    def cancel_command(self):
        self.message_dialogue.destroy()
        self.isOK = False


class PokeConVersionCheck(object):
    """
    PokeCon/pythonおよびライブラリのversionを確認する
    """

    def __init__(self, parent, pokeconname: str, pokeconversion: str):
        txt = f'■{pokeconname}\n{pokeconversion}\n\n'
        if platform.system() == 'Darwin':
            # MacOS
            txt += f'■OS\n{platform.mac_ver()}(Mac)\n\n'
        else:
            txt += f'■OS\n{platform.platform()}\n\n'
        txt += f'■Python version\n{sys.version.split(" ")[0]}\n\n'
        txt += '■Libraries version\n'
        with open('../requirements.txt', 'r') as file:
            for line in file:
                library_name = line.strip()
                try:
                    version = pkg_resources.get_distribution(library_name).version
                    txt += f"{library_name}: {version}\n"
                except pkg_resources.DistributionNotFound:
                    txt += f"{library_name}: Not installed\n"
                except:
                    pass
        self.window = parent
        self.window.title("Version確認")
        self.window.attributes("-topmost", True)
        self.window.protocol("WM_DELETE_WINDOW", self.close_window)

        self.main_frame = tk.Frame(self.window)
        self.main_text = ttk.Label(self.main_frame, text=txt, anchor='center')
        self.main_text.grid(column=0, ipadx='10', ipady='10', row=0, sticky='nsew')

        self.OK = ttk.Button(self.main_frame, command=self.close_window)
        self.OK.configure(text='OK')
        self.OK.grid(column=0, padx='10', pady='10', row=1)
        self.OK.grid_anchor('center')
        self.main_frame.pack()

        self.window.master.wait_window(self.window)

    def close_window(self):
        self.window.destroy()


class PokeConChangeLog(object):
    '''
    更新履歴を表示する
    '''

    def __init__(self, parent):
        try:
            with open('../changelog.txt', 'r', encoding='utf-8') as f:
                txt = "".join(f.readlines())
        except:
            print("changelog.txtが開けません。")

        self.window = parent
        self.window.title("更新履歴")
        self.window.attributes("-topmost", True)
        self.window.protocol("WM_DELETE_WINDOW", self.close_window)

        self.main_frame = tk.Frame(self.window)

        scrollbar = ttk.Scrollbar(self.main_frame)
        scrollbar.pack(side="right", fill="y")

        self.text_widget = tk.Text(self.main_frame, yscrollcommand=scrollbar.set)
        self.text_widget.pack(side="top", fill="both", expand=True, padx=10, pady=10)

        scrollbar.config(command=self.text_widget.yview)

        # テキストウィジェットへのテキストの追加
        self.text_widget.insert("1.0", txt)

        # テキストウィジェットを書き込み禁止にする
        self.text_widget.config(state="disabled")

        self.OK = ttk.Button(self.main_frame, command=self.close_window)
        self.OK.configure(text='OK')
        self.OK.pack(pady=10)  # OKボタンの下に余白を追加
        self.main_frame.pack()

        self.window.master.wait_window(self.window)

    def close_window(self):
        self.window.destroy()


class PokeConCopyright(object):
    """
    pokeconでLicenseを表示する
    """

    def __init__(self, parent):
        try:
            with open('../LICENSE', 'r') as f:
                txt = "".join(f.readlines())
        except:
            print("LICENSEファイルが開けません。")
            return

        self.window = parent
        self.window.title("LICENSE")
        self.window.attributes("-topmost", True)
        self.window.protocol("WM_DELETE_WINDOW", self.close_window)

        self.main_frame = tk.Frame(self.window)
        self.main_text = ttk.Label(self.main_frame, text=txt, anchor='center')
        self.main_text.grid(column=0, ipadx='10', ipady='10', row=0, sticky='nsew')

        self.OK = ttk.Button(self.main_frame, command=self.close_window)
        self.OK.configure(text='OK')
        self.OK.grid(column=0, padx='10', pady='10', row=1)
        self.OK.grid_anchor('center')
        self.main_frame.pack()

        self.window.master.wait_window(self.window)

    def close_window(self):
        self.window.destroy()
