#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from Commands.Keys import Button, Direction, Hat
from Commands.PythonCommandBase import ImageProcPythonCommand
# auto egg hatching using image recognition
# 自動卵孵化(キャプボあり)
class send_exe_trade(ImageProcPythonCommand):
    NAME = 'エグゼ交換送り側'

    def __init__(self, cam):
        super().__init__(cam)
        self.cam = cam
        self.party_num = 1  # don't count eggs
        self.hatched_num = 0
        self.hatched_box_num = 0
        self.itr_max = 6

    def do(self):
        while True:
            try:
                self.send_trade()
            except Exception as e:
                self._logger.info("全チップ交換完了")
                return


    def send_trade(self):
        # 通信エラー
        # Snipping(560, 294, 800, 450)
        # return
        #Loop()
        #{
        # トレード
        self.press(Hat.BTM, 0.2, 0.2)
        self.press(Button.A, 0.2, 0.2)

        # ローカルトレード
        self.press(Hat.TOP, 0.2, 0.2)
        self.press(Button.A, 0.2, 0.2)

        # チップトレード
        self.press(Button.A, 0.2, 0.2)

        # 申し込む
        self.press(Hat.BTM, 0.2, 0.2)
        self.press(Button.A, 0.2, 0.2)

        # next
        self.press(Button.A, 0.2, 0.2)

        # 画面判定
        while True:
            self._logger.info('画面遷移判定開始')
            # トレード画面マッチング用画像取得
            # Snipping(306, 200, 30, 240)
            # トレード画面への遷移をチェック
            self._logger.info("文字化け確認：Macro/rokkuman_exe/trade_chip_frame.png")
            if not self.isContainTemplate("Macro/rokkuman_exe/trade_chip_frame.png", threshold=0.85, crop=[203, 134, 224, 300]):
                # 画面遷移失敗
                self._logger.info("トレード画面遷移失敗")
            else:
                # 画面遷移成功
                self._logger.info("トレード画面への遷移成功")
                # 交換可能
                # 枚数まで画面切り替え
                for _ in range(0, 5):
                    self.press(Button.START, 0.2, 0.2)
                # 枚数が最も少ないものを選ぶ
                self.press(Hat.TOP, 0.2, 0.2)
                self.press(Hat.TOP, 0.2, 0.3)
                # チップの有無チェック
                if self.isContainTemplate("Macro/rokkuman_exe/no_data_check.png", threshold=0.85, crop=[250, 120, 450, 290]):
                    self._logger.info("交換不可")
                    # 交換不可
                    raise Exception("交換不可")
                self._logger.info("交換可能")
                # チップ選択
                self.press(Button.A, 0.2, 0.2)
                # メッセージ選択
                self.press(Button.A, 0.2, 0.2)
                # 申し込み先待機
                while True:
                    self._logger.info("申込先が見つかるのを待つ")
                    # リスト更新が必要か判定
                    # Snipping(770, 300, 250, 20)
                    if self.isContainTemplate("Macro/rokkuman_exe/choice_of_trading_partner.png", threshold=0.85, crop=[600, 200, 620, 220]):
                        self._logger.info("申込先を選択する")
                        while True:
                            # Snipping(564, 455, 770, 290)
                            if not self.isContainTemplate("Macro/rokkuman_exe/trade_application_confirmation.png", threshold=0.85, crop=[420, 325, 880, 500]):
                                self._logger.info("申し込み確定")
                                self.press(Button.A, 0.2, 0.2)
                                break
                        while True:
                            # Snipping(564, 455, 770, 290)
                            if self.isContainTemplate("Macro/rokkuman_exe/trade_application_confirmation.png", threshold=0.85, crop=[420, 325, 880, 500]):
                                self._logger.info("申し込み確定")
                                self.press(Button.A, 0.2, 0.2)
                                break
                        while True:
                            if self.isContainTemplate("Macro/rokkuman_exe/successful_trade.png", threshold=0.85, crop=[550, 300, 740, 480]):
                                # OK　選択
                                self._logger.info("交換成功")
                                self.press(Button.A, 0.2, 0.2)
                                # 画面遷移待ち
                                while True:
                                    # Snipping(190, 180, 410, 40)
                                    self._logger.info("交換スクリプト完了")
                                    if self.isContainTemplate("Macro/rokkuman_exe/network_initial_screen.png", threshold=0.85, crop=[120, 120, 400, 150]):
                                        return
                    # 通信エラーのせいで変な画面に飛んだ場合の対処
                    elif self.isContainTemplate("Macro/rokkuman_exe/no_communication_partner_update_list.png", threshold=0.85, crop=[410, 170, 830, 500]):
                            self._logger.info("リスト更新")
                            # 更新が必要
                            # はい　にカーソルを移す
                            self.press(Hat.TOP, 0.2, 0.2)
                            # はい　選択
                            self.press(Button.A, 0.2, 0.2)
                    # 通信エラーになった場合の対処
                    elif self.isContainTemplate("Macro/rokkuman_exe/communication_error.png", threshold=0.85, crop=[400, 220, 850, 500]):
                            self._logger.info("通信エラー")
                            self.press(Button.A, 0.2, 0.2)
                            # 画面遷移待ち
                            while not self.isContainTemplate("Macro/rokkuman_exe/network_initial_screen.png", threshold=0.85, crop=[120, 120, 400, 150]):
                                # 通信エラーのOKを押せないパターンがあったため
                                if self.isContainTemplate("Macro/rokkuman_exe/communication_error.png", threshold=0.85, crop=[400, 220, 850, 500]):
                                    self.press(Button.A, 0.2, 0.2)
                            return
                    else:
                        self._logger.info("トレード相手を待つ")
                        pass
