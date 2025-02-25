#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from Commands.Keys import Button, Direction
from Commands.PythonCommandBase import ImageProcPythonCommand
from PIL import Image


# Egg hatching at count times
# すべての孵化(キャプボあり)
# 現在は手持ちのみ
class AllHatching(ImageProcPythonCommand):
    NAME = 'エグゼ比較用キャプチャ'

    def __init__(self, cam):
        super().__init__(cam)
        self.hatched_num = 0
        self.count = 5
        self.place = 'wild_area'

    def do(self):
        path_pre="./Template/Macro/rokkuman_exe/"
        # crop_and_save_png(path_pre+"2025-02-12_20-42-58.png", path_pre+"トレード相手選択可能t.png", 600, 200, 620, 220)
        # crop_and_save_png(path_pre+"2025-02-12_20-43-03.png", path_pre+"トレード申込確認t.png", 420, 325, 880, 500)
        # crop_and_save_png(path_pre+"2025-02-12_20-43-19.png", path_pre+"トレード成功2t.png", 550, 300, 740, 480)
        # crop_and_save_png(path_pre+"2025-02-12_20-41-26.png", path_pre+"通信相手なし_リスト更新t.png", 410, 170, 830, 500)
        # crop_and_save_png(path_pre+"2025-02-12_20-43-23.png", path_pre+"ネットワーク初期画面t.png", 120, 120, 400, 150)
        # crop_and_save_png(path_pre+"2025-02-13_12-39-50.png", path_pre+"trade_acceptance_selection.png", 780, 200, 800, 220)
        # crop_and_save_png(path_pre+"2025-02-17_20-04-19.png", path_pre+"network_battle_list.png", 1040, 144, 1162, 175)
        # crop_and_save_png(path_pre+"2025-02-17_20-04-33.png", path_pre+"return_top_confirm.png", 430, 250, 840, 480)
        crop_and_save_png(path_pre+"2025-02-21_23-29-09.png", path_pre+"communication_error.png", 400, 220, 850, 500)
        
        
   

def crop_and_save_png(input_path, output_path, x1, y1, x2, y2):
    """
    指定したPNG画像を(x1, y1, x2, y2)で切り取り、新しい画像として保存する。

    Args:
        input_path (str): 入力PNG画像のファイルパス
        output_path (str): 出力PNG画像のファイルパス
        x1, y1, x2, y2 (int): 切り取る矩形の座標（左上 (x1, y1) ～ 右下 (x2, y2)）
    """
    try:
        # 画像を開く
        img = Image.open(input_path)

        # 指定範囲を切り取る
        cropped_img = img.crop((x1, y1, x2, y2))

        # 新しいPNG画像として保存
        cropped_img.save(output_path, format="PNG")
        print(f"✅ 画像を切り取って保存しました: {output_path}")
    
    except Exception as e:
        print(f"⚠️ エラーが発生しました: {e}")

# 使用例
# crop_and_save_png("input.png", "output.png", 100, 50, 400, 300)