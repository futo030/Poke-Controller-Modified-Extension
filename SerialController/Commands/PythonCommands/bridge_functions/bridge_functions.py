#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations  # 3.7向け。廃止したい。

import os
from typing import List, Optional
from Commands.PythonCommandBase import ImageProcPythonCommand

"""
PokeCon橋渡し用関数
PokeCon Modified版とExtension版で処理を切り替える関数を定義する。(主にprint系)
developed by フウ
"""
# initにてPokeConの種類を判定する。


def convert_crop(crop_fmt: int | str = "", crop: List[int] = []) -> List[int]:
    """
    Extension版の crop_fmt と crop を、Modified版の crop([x軸始点, y軸始点, x軸終点, y軸終点])に変換する。
    crop_fmt を指定しない場合は、そのまま返す(Extension版でも同じ並びとして扱われる)
    """
    if crop is None or len(crop) != 4:
        return []
    c = list(crop)
    fmt = str(crop_fmt)
    if fmt == "2":  # [x軸始点, y軸始点, 横のサイズ, 縦のサイズ]
        return [c[0], c[1], c[0] + c[2], c[1] + c[3]]
    if fmt == "3":  # [x軸始点, x軸終点, y軸始点, y軸終点]
        return [c[0], c[2], c[1], c[3]]
    if fmt == "4":  # [x軸始点, 横のサイズ, y軸始点, 縦のサイズ]
        return [c[0], c[2], c[0] + c[1], c[2] + c[3]]
    if fmt == "11":  # [y軸始点, x軸始点, y軸終点, x軸終点]
        return [c[1], c[0], c[3], c[2]]
    if fmt == "12":  # [y軸始点, x軸始点, 縦のサイズ, 横のサイズ]
        return [c[1], c[0], c[1] + c[3], c[0] + c[2]]
    if fmt == "13":  # [y軸始点, y軸終点, x軸始点, x軸終点]
        return [c[2], c[0], c[3], c[1]]
    if fmt == "14":  # [y軸始点, 縦のサイズ, x軸始点, 横のサイズ]
        return [c[2], c[0], c[2] + c[3], c[0] + c[1]]
    return c  # crop_fmt=1 または指定なし: [x軸始点, y軸始点, x軸終点, y軸終点]


def remove_next_item(dialogue_list):
    dialogue_list_out = []
    for widget_list in dialogue_list:
        if widget_list[0].casefold() == "next".casefold():
            pass
        else:
            dialogue_list_out.append(widget_list)
    return dialogue_list_out


class BridgeFunctions(object):
    def __init__(self, commands):
        self.commands = commands
        self.is_extension = os.path.exists("Constant.py")
        if not self.is_extension and not hasattr(
            self.commands.__class__, "dialogue6widget"
        ):  # 継承している関数にdialogue6widget関数が含まれるか? dialogue6widget関数はmodified版/extension版のみ。
            print("本家PokeConでは実行できません。\nまたは古いVersionのPokeConを使用しており更新が必要です。")

    def check_pokecon_extension(self) -> bool:
        """
        Poke-Controller Modified Extensionであるかを確認
        True: Poke-Controller Modified Extension
        False: Poke-Controller Modified
        None: Poke-Controller(本家)
        """
        return self.is_extension

    def _finish_if_canceled(self, ret):
        """
        Modified版でダイアログがキャンセルされた場合(戻り値が False / None)は、
        Extension版と同じようにスクリプトを終了する
        """
        if ret is False or ret is None:
            self.commands.finish()
        return ret

    def get_profile_name(self) -> str:
        """
        profile名を取得
        Extension版: profilename、Modified版/本家""
        """
        return ImageProcPythonCommand.profilename if self.is_extension else ""

    # Template画像のディレクトリを変更する。extension版であることかつ指定したディレクトリが存在する場合に実施。
    def set_template_directory(self, name1: str, name2: str) -> None:
        """
        テンプレートファイルのディレクトリ指定
        """
        if self.is_extension and os.path.isdir(os.path.join(name1, name2)):
            self.commands.setTemplateDir(name1 + "/")

    # Template画像のディレクトリを取得する。
    def get_template_directory(self) -> str:
        """
        テンプレートファイルのディレクトリ指定
        """
        return ImageProcPythonCommand.template_path_name if self.is_extension else "./Template/"

    # print関数。extension版の場合は関数によって上書きしたり、追記したりすることが可能。
    def bf_print(self, *objects: object, sep: str = " ", end: str = "\n") -> None:
        """
        print出力(上書きなし)
        """
        if self.is_extension:
            self.commands.print_tbs("a", *objects, sep=sep, end=end)
        else:
            print(*objects, sep=sep, end=end)

    def bf_print_w(self, *objects: object, sep: str = " ", end: str = "\n"):
        """
        print出力(上書き)
        """
        if self.is_extension:
            self.commands.print_tb("w", *objects, sep=sep, end=end)
        else:
            print(*objects, sep=sep, end=end)

    def bf_print_a(self, *objects: object, sep: str = " ", end: str = "\n"):
        """
        print出力(追記)
        """
        if self.is_extension:
            self.commands.print_tb("a", *objects, sep=sep, end=end)
        else:
            print(*objects, sep=sep, end=end)

    def bf_isContainTemplate(
        self,
        template_path: str,
        threshold: float = 0.7,
        use_gray: bool = True,
        show_value: bool = False,
        show_position: bool = True,
        show_only_true_rect: bool = True,
        ms: float = 2000,
        crop_fmt: int | str = "",
        crop: List[int] = [],
        mask_path: str = None,
        use_gpu: bool = False,
        BGR_range: Optional[dict] = None,
        threshold_binary: Optional[int] = None,
        crop_template: List[int] = [],
        show_image: bool = False,
        color: List[str] = ["blue", "red", "orange"],
    ) -> bool:
        if self.is_extension:
            return self.commands.isContainTemplate(
                template_path,
                threshold=threshold,
                use_gray=use_gray,
                show_value=show_value,
                show_position=show_position,
                show_only_true_rect=show_only_true_rect,
                ms=ms,
                crop_fmt=crop_fmt,
                crop=crop,
                mask_path=mask_path,
                use_gpu=use_gpu,
                BGR_range=BGR_range,
                threshold_binary=threshold_binary,
                crop_template=crop_template,
                show_image=show_image,
                color=color,
            )
        else:
            return self.commands.isContainTemplate(
                template_path,
                threshold=threshold,
                use_gray=use_gray,
                show_value=show_value,
                show_position=show_position,
                show_only_true_rect=show_only_true_rect,
                ms=ms,
                crop=convert_crop(crop_fmt, crop),
                mask_path=mask_path,
            )

    def bf_isContainTemplate_max(
        self,
        template_path_list: List[str],
        threshold: float = 0.7,
        use_gray: bool = True,
        show_value: bool = False,
        show_position: bool = True,
        show_only_true_rect: bool = True,
        ms: float = 2000,
        crop_fmt: int | str = "",
        crop: List[int] = [],
        mask_path_list: List[str] = [],
        BGR_range: Optional[dict] = None,
        threshold_binary: Optional[int] = None,
        crop_template: List[int] = [],
        show_image: bool = False,
        color: List[str] = ["blue", "red", "orange"],
    ) -> any:
        if self.is_extension:
            max_idx, max_val_list, judge_list = self.commands.isContainTemplate_max(
                template_path_list,
                threshold=threshold,
                use_gray=use_gray,
                show_value=show_value,
                show_position=show_position,
                show_only_true_rect=show_only_true_rect,
                ms=ms,
                crop_fmt=crop_fmt,
                crop=crop,
                mask_path_list=mask_path_list,
                BGR_range=BGR_range,
                threshold_binary=threshold_binary,
                crop_template=crop_template,
                show_image=show_image,
                color=color,
            )
        else:
            max_idx, max_val_list, judge_list = self.commands.isContainTemplate_max(
                template_path_list,
                threshold=threshold,
                use_gray=use_gray,
                show_value=show_value,
                show_position=show_position,
                show_only_true_rect=show_only_true_rect,
                ms=ms,
                crop=convert_crop(crop_fmt, crop),
            )

        return max_idx, max_val_list, judge_list

    def bf_dialogue(self, title: str, message: list | str, desc: str = None, need: type = list) -> list | dict:
        """
        ダイアログ関数(Entryのみ)
        ※Modified版の場合はdescなし
        """
        if self.is_extension:
            ret = self.commands.dialogue(title, message, desc=desc, need=need)
        else:
            ret = self._finish_if_canceled(self.commands.dialogue(title, message, need=need))
        return ret

    def bf_dialogue6widget(self, title: str, dialogue_list: list, desc: str = None, need: type = list) -> list | dict:
        """
        ダイアログ関数(6widget)
        ※Modified版の場合は["Next"]を削除する。
        """
        if self.is_extension:
            ret = self.commands.dialogue6widget(title, dialogue_list, desc=desc, need=need)
        else:
            dialogue_list = remove_next_item(dialogue_list)
            ret = self._finish_if_canceled(self.commands.dialogue6widget(title, dialogue_list, need=need))
        return ret

    def bf_dialogue6widget_save_settings(
        self, title: str, dialogue_list: list, filename: str, desc: str = None, need: type = list
    ) -> list | dict:
        """
        設定保存機能付きダイアログ関数
        ※Modified版の場合は通常のダイアログ関数が起動する。
        filename: 設定ファイル名。絶対パス。
        """
        if self.is_extension:
            ret = self.commands.dialogue6widget_save_settings(title, dialogue_list, filename, desc=desc, need=need)
        else:
            dialogue_list = remove_next_item(dialogue_list)
            ret = self._finish_if_canceled(self.commands.dialogue6widget(title, dialogue_list, need=need))
        return ret

    def bf_dialogue6widget_select_settings(
        self, title: str, dialogue_list: list, dirname: str, desc: str = None, need: type = list
    ) -> list | dict:
        """
        設定選択機能付きダイアログ関数
        ※Modified版の場合は通常のダイアログ関数が起動する。
        dirname: 設定ファイルを保存するディレクトリ名。絶対パス。
        """
        if self.is_extension:
            ret = self.commands.dialogue6widget_select_settings(title, dialogue_list, dirname, desc=desc, need=need)
        else:
            dialogue_list = remove_next_item(dialogue_list)
            ret = self._finish_if_canceled(self.commands.dialogue6widget(title, dialogue_list, need=need))
        return ret

    def bf_show_informations(
        self, name: str, developer: str | list, contributor: str | list = None, description: str = None
    ):
        """
        プログラムの詳細情報を表示する
        name | str: プログラム名
        developer | str/list: 開発者名(複数の場合はリストでinputする)
        contributor | str/list: 貢献者名(複数の場合はリストでinputする)
        description | str: 概要
        """
        developers = ", ".join(developer) if isinstance(developer, list) else developer

        text = "---------------------------------------------\n"

        # Extension版ではコマンド名の末尾に「 (フォルダ名)」が付くので、取り除く
        if self.is_extension and name.endswith(")") and " (" in name:
            name = name[: name.rfind(" (")]

        text += f"Name: {name}\nDeveloper: {developers}\n"

        if contributor:
            contributors = ", ".join(contributor) if isinstance(contributor, list) else contributor
            text += f"Contributor: {contributors}\n"

        if description:
            text += f"Description: {description}\n"

        text += "---------------------------------------------"

        self.bf_print(text)
