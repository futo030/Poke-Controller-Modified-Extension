#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from Commands.PythonCommandBase import ImageProcPythonCommand
import os


class isContainTemplate_sample(ImageProcPythonCommand):
    NAME = '画像認識関数紹介(2) ver. 0.0.1'

    def __init__(self, cam):
        super().__init__(cam)

    def do(self):
        print("-------------------------------------")
        print("画像認識関数紹介(2) ver. 0.0.1")
        print("-------------------------------------")

        # 事前に準備したテンプレートマッチング対象画像がトリミングされていない場合
        # crop_template:テンプレート画像の位置。
        self.saveCapture(os.path.join(os.path.dirname(__file__), "capture_image"))
        res = self.isContainedImage(os.path.join(os.path.dirname(__file__), "capture_image.png"), crop_template=[944, 224, 1141, 414], show_only_true_rect=False, show_image=True)
        print(f"検出結果:{res}")

        # 事前に準備したテンプレートマッチング対象画像がトリミングされている状態の場合
        self.saveCapture(os.path.join(os.path.dirname(__file__), "capture_image"), crop=[267, 112, 825, 490])
        res = self.isContainedImage(os.path.join(os.path.dirname(__file__), "capture_image.png"), crop_template=[944, 224, 1141, 414], show_only_true_rect=False, show_image=True)
        print(f"検出結果:{res}")

        # 事前に準備したテンプレートマッチング対象画像がトリミングされておらず、テンプレートマッチング時にトリミングする場合
        # crop:テンプレートマッチング対象画像に対するトリミング位置。
        self.saveCapture(os.path.join(os.path.dirname(__file__), "capture_image"))
        res = self.isContainedImage(os.path.join(os.path.dirname(__file__), "capture_image.png"), crop=[
                                    267, 112, 825, 490], crop_template=[944, 224, 1141, 414], show_only_true_rect=False, show_image=True)
        print(f"検出結果:{res}")

        self.finish()
