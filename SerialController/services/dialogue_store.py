#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
コマンドのダイアログで使う、ウィジェット名の確認と、入力した設定の保存・読み込み

画面(tkinter)には触れない。ダイアログの表示は PokeConDialogue.py が行う。
"""
from __future__ import annotations

import glob
import json
import os


def check_widget_name(dialogue_list: list, except_name: list | None = None) -> bool:
    """
    ウィジェットに同一名称がないかを確認
    except_name: ウィジェットの名前として使えない名前のリスト(None や省略時は、なし)
    """
    input_name = [setting[1] for setting in dialogue_list if len(setting) > 1] + list(except_name or [])
    checked_name = []
    output_name = [name for name in input_name if name not in checked_name and not checked_name.append(name)]

    return len(input_name) == len(output_name)


def get_setting(filename: str) -> dict | None:
    """
    保存した設定値を読み込む(ファイルが無い・読めない場合は None)
    """
    try:
        with open(filename, encoding="utf-8") as f:
            file = json.load(f)
            return file
    except Exception:
        return None


def save_setting(filename: str, settings: dict) -> None:
    """
    設定値を保存する
    """
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=4, ensure_ascii=False)


def generate_new_dialogue_list(dialogue_list: list, filename: str) -> list:
    """
    ダイアログの定義の、各ウィジェットの初期値(最後の要素)を、保存した設定値に置き換えて返す。
    dialogue_list の中のリストを書き換える。保存した設定が無い場合は、そのまま返す
    """
    settings = get_setting(filename)
    if not settings:
        return dialogue_list
    else:
        new_dialogue_list = []
        for setting in dialogue_list:
            if len(setting) < 2:
                pass
            else:
                try:
                    setting[-1] = settings[setting[1]]
                except Exception:
                    pass
            new_dialogue_list.append(setting)
    return new_dialogue_list


def save_dialogue_settings(new_dialogue_list: list, ret: list | dict, filename: str) -> None:
    """
    ダイアログで入力した値を、ウィジェット名 -> 値 の形で保存する。
    ret: ダイアログの戻り値(list の場合は、名前のあるウィジェットの順の値。dict の場合は、そのまま保存する)
    保存に失敗した場合は、メッセージを表示するだけで、例外にしない
    """
    try:
        settings = {}
        if isinstance(ret, list):
            cnt = 0
            for setting in new_dialogue_list:
                if len(setting) < 2:
                    pass
                else:
                    settings[setting[1]] = ret[cnt]
                    cnt += 1
            save_setting(filename, settings)
        else:
            save_setting(filename, ret)
    except Exception:
        print("Error: Configuration dump failed.")


def get_settings_list(dirname: str) -> list:
    """
    フォルダー(下の階層を含む)にある設定(.json)の名前の一覧(フォルダーからの相対パスで、拡張子なし)。
    名前が "_" で始まるものは除く。フォルダーが無い場合は作る
    """
    if os.path.isdir(dirname):
        pass
    else:
        os.makedirs(dirname)
    filename = os.path.join(dirname, "**", "*.json")
    settings_list = glob.glob(filename, recursive=True)

    len_pass = len(dirname) + 1
    settings_name_list = [file[len_pass:-5] for file in settings_list if file[len_pass] != "_"]

    return settings_name_list
