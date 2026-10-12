#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from Commands.PythonCommandBase import PythonCommand
from Commands.SwitchKeyboard import KEY


class Keyboard_sample(PythonCommand):
    NAME = "Keyboard_sample"

    def __init__(self):
        super().__init__()

    def do(self):
        # キーボード機能に対応したファームウェアが必要です。
        # (CH552-SERIAL の場合は、ファームウェアは v2.4 以上を使用してください)
        #
        # Switchでキーボード画面(日本語 ローマ字入力)を開き、かなモードの状態で実行してください。
        # 送れるのは半角の文字だけです。かな・カナは、入力モードをキーで切り替えてローマ字を送ります。
        self.KeyBoard_Init()

        # かなモードのまま、ローマ字を打つ → 「ぽけこん」
        self.TypeString("pokekonn")
        self.TypeKey(KEY.ENTER)  # 確定
        self.wait(0.5)

        # 半角/全角キーで半角英数に切り替えて打つ → 「Pokecon」
        self.TypeKey(KEY.JP_HANZEN)
        self.TypeString("Pokecon")
        self.TypeKey(KEY.ENTER)  # 確定
        self.TypeKey(KEY.JP_HANZEN)  # かなモードに戻す
        self.wait(0.5)

        # ひらがな/カタカナキーでカタカナに切り替えて打つ → 「キーボード」
        self.TypeKey(KEY.JP_HIRAGANA)
        self.TypeString("ki-bo-do")
        self.TypeKey(KEY.ENTER)  # 確定
        self.TypeKey(KEY.JP_HIRAGANA)  # ひらがなに戻す

        self.finish()
