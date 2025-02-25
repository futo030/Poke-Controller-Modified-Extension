#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from Commands.Keys import Button, Direction, Hat
from Commands.PythonCommandBase import ImageProcPythonCommand


# Egg hatching at count times
# すべての孵化(キャプボあり)
# 現在は手持ちのみ
class AllHatching(ImageProcPythonCommand):
    NAME = 'エグゼ交換受け側'

    def __init__(self, cam):
        super().__init__(cam)
        self.hatched_num = 0
        self.count = 5
        self.place = 'wild_area'

    def do(self):
        while True:
            try:
                self.recv_trade()
            except Exception as e:
                self._logger.info("全チップ交換完了")
                return
    
    def recv_trade(self):
        #while True:
        #{
        # トレード
        self.press(Hat.BTM, 0.2, 0.2)
        self.press(Button.A, 0.2, 0.2)

        # ローカルトレード
        self.press(Hat.TOP, 0.2, 0.2)
        self.press(Button.A, 0.2, 0.2)

        # チップトレード
        self.press(Button.A, 0.2, 0.2)

        # 待ち受ける
        self.press(Button.A, 0.2, 0.2)

        # next
        self.press(Button.A, 0.2, 0.2)

        count = 0
        # 画面判定
        while True:
            self._logger.info("画面遷移判定開始")
            # トレード画面マッチング用画像取得
            # Snipping(306, 200, 30, 240)
            # トレード画面への遷移をチェック
            if not self.isContainTemplate("Macro/rokkuman_exe/trade_chip_frame.png", threshold=0.85, crop=[203, 134, 224, 300]):
                self._logger.info("トレード画面遷移失敗")
                if count >= 10:
                    return
                # 画面遷移失敗
            else:
                # 画面遷移成功
                self._logger.info("トレード画面への遷移成功")
                # no data 選択
                while True:
                    if not self.isContainTemplate("Macro/rokkuman_exe/no_data_check.png", threshold=0.85, crop=[250, 120, 450, 290]):
                        self._logger.info("no_dataを選択します")
                        # 位置リセット
                        self.press(Button.START, 0.2, 0.2)
                        # Nodataへ移動
                        self.press(Hat.TOP, 0.2, 0.2)
                    else:
                        # No dataに合ったので、次に進む
                        self._logger.info("no_dataにカーソルが合っています")
                        break
                # チップ選択
                self.press(Button.A, 0.2, 0.2)
                # メッセージ選択
                self.press(Button.A, 0.2, 0.2)
                # トレード相手待ち
                while True:
                    # Snipping(790, 300, 530, 20)
                    
                    if self.isContainTemplate("Macro/rokkuman_exe/trade_acceptance_selection.png", threshold=0.85, crop=[780, 200, 800, 220]):
                        # トレード相手が見つかるパターン
                        self._logger.info("トレード相手を見つけました")
                        while True:
                            # トレード相手を待つケースはnot判定なので、例外処理パターンを先に記載してます。
                            if self.isContainTemplate("Macro/rokkuman_exe/network_battle_list.png", threshold=0.85, crop=[1040, 144, 1162, 175]):
                                # 通信エラーが発生した場合、ネットワーク対戦の待機リストに行ってしまう。
                                # それを防ぐための処理です。
                                # b -> confirm a -> top check
                                # 確認画面を出す。（エラーの復帰ケースなので、気持ちの余裕を持って待つ）
                                self.press(Button.B, 0.2, 2.0)
                                # 確認画面表示待ち
                                while not self.isContainTemplate("Macro/rokkuman_exe/return_top_confirm.png", threshold=0.85, crop=[430, 250, 840, 480]):
                                    pass
                                # はいを選択（エラーの復帰ケースなので、気持ちの余裕を持って待つ）
                                self.press(Button.A, 0.2, 2.0)
                                while not self.isContainTemplate("Macro/rokkuman_exe/network_initial_screen.png", threshold=0.85, crop=[120, 120, 400, 150]):
                                    pass
                                # 状況がリセットされるので、次のループに入る
                                return
                            elif not self.isContainTemplate("Macro/rokkuman_exe/trade_application_confirmation.png", threshold=0.85, crop=[420, 325, 880, 500]):
                                # トレード相手選択
                                self._logger.info("トレード相手を選択します")
                                self.press(Button.A, 0.2, 0.2)
                            else:
                                # elifの条件がnotだから、わかりにくいが、トレード相手選択確認画面に遷移できた場合は、breakでループを抜ける。
                                break
                        while not self.isContainTemplate("Macro/rokkuman_exe/trade_application_confirmation.png", threshold=0.85, crop=[420, 325, 880, 500]):
                            pass
                        # トレード申し込み確認
                        self._logger.info("トレード相手を確定します")
                        self.press(Button.A, 0.2, 0.2)

                        # 交換完了まで待機
                        while not self.isContainTemplate("Macro/rokkuman_exe/successful_trade.png", threshold=0.85, crop=[550, 300, 740, 480]):
                            # Snipping(800, 420, 300, 280)
                            self._logger.info("交換中")
                        # OK　選択
                        self._logger.info("交換成功")
                        self.press(Button.A, 0.2, 0.2)
                        
                        # 画面遷移待ち
                        while not self.isContainTemplate("Macro/rokkuman_exe/network_initial_screen.png", threshold=0.85, crop=[120, 120, 400, 150]):
                            pass
                        self._logger.info("初期画面へ戻りました。")
                        # 交換完了のため、次の交換へ
                        return
                    
                        
                    else:
                        # 通信エラー
                        # Snipping(560, 294, 800, 450)
                        # 終了させる
                        if self.isContainTemplate("Macro/rokkuman_exe/communication_error.png", threshold=0.85, crop=[400, 220, 850, 500]):
                            self._logger.info("通信エラーが発生しました")
                            self.press(Button.A, 0.2, 0.2)
                            # 画面遷移待ち
                            while not self.isContainTemplate("Macro/rokkuman_exe/network_initial_screen.png", threshold=0.85, crop=[120, 120, 400, 150]):
                                # 通信エラーのOKを押せないパターンがあったため
                                if self.isContainTemplate("Macro/rokkuman_exe/communication_error.png", threshold=0.85, crop=[400, 220, 850, 500]):
                                    self.press(Button.A, 0.2, 0.2)
                            return

            self._logger.info("次のループへ移動")
