#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import List, TYPE_CHECKING

import pygame
import numpy as np
import datetime
from logging import getLogger, DEBUG, NullHandler

if TYPE_CHECKING:
    from Commands.Sender import Sender


class ProController:
    flag_procon = False

    def __init__(self):
        self.axis_dict = {
            0: "L-X",
            1: "L-Y",
            2: "R-X",
            3: "R-Y",
            4: "ZL",
            5: "ZR",
        }

        self.button_dict = {
            0: "A",
            1: "B",
            2: "X",
            3: "Y",
            4: "MINUS",
            5: "HOME",
            6: "PLUS",
            7: "LSTICK",
            8: "RSTICK",
            9: "L",
            10: "R",
            11: "UP",
            12: "DOWN",
            13: "LEFT",
            14: "RIGHT",
            15: "CAPTURE",
        }

        self.button_dict_shift = {
            0: 4,
            1: 3,
            2: 5,
            3: 2,
            4: 10,
            5: 14,
            6: 11,
            7: 12,
            8: 13,
            9: 6,
            10: 7,
            11: 0,
            12: 2,
            13: 3,
            14: 1,
            15: 15,
        }

        self.hat_dict = {
            0: 8,  # center
            1: 0,  # up
            2: 2,  # right
            3: 1,  # up-right
            4: 4,  # down
            5: 8,  # ありえないのでcenterにする
            6: 3,  # down-right
            7: 8,  # ありえないのでcenterにする
            8: 6,  # left
            9: 7,  # up-left
            10: 8,  # ありえないのでcenterにする
            11: 8,  # ありえないのでcenterにする
            12: 5,  # down-left
            13: 8,  # ありえないのでcenterにする
            14: 8,  # ありえないのでcenterにする
            15: 8,  # ありえないのでcenterにする
        }

        self.bits_16 = 0
        self.hat_status = 0
        self.stick_status_old = [128, 128, 128, 128]
        self.stick_status_new = [128, 128, 128, 128]
        self.flag_print = False
        self.filename = ""

        self._logger = getLogger(__name__)
        self._logger.addHandler(NullHandler())
        self._logger.setLevel(DEBUG)
        self._logger.propagate = True

    # stickの出力を0-255の範囲に補正する。
    def map_axis(self, val: float):
        val = round(val, 3)
        in_min = -1
        in_max = 1
        out_min = 0
        out_max = 255
        return int((val - in_min) * (out_max - out_min) / (in_max - in_min) + out_min)

    def joystick_move_detection(self, joystick: pygame.Joystick):
        # Lstickの位置を確認する。
        if np.sqrt((joystick.get_axis(0)) ** 2 + (joystick.get_axis(1)) ** 2) < 0.35:
            self.stick_status_new[0] = 128
            self.stick_status_new[1] = 128
        else:
            self.stick_status_new[0] = self.map_axis(joystick.get_axis(0))
            self.stick_status_new[1] = self.map_axis(joystick.get_axis(1))
        # 古い位置と比較して異なるならビットを立てる
        if (
            self.stick_status_new[0] == self.stick_status_old[0]
            and self.stick_status_new[1] == self.stick_status_old[1]
        ):
            self.bits_16 = self.bits_16 & ~(2)
        else:
            self.flag_print = True
            self.bits_16 = self.bits_16 | 2

        # Rstickの位置を確認する。
        if np.sqrt((joystick.get_axis(2)) ** 2 + (joystick.get_axis(3)) ** 2) < 0.35:
            self.stick_status_new[2] = 128
            self.stick_status_new[3] = 128
        else:
            self.stick_status_new[2] = self.map_axis(joystick.get_axis(2))
            self.stick_status_new[3] = self.map_axis(joystick.get_axis(3))
        # 古い位置と比較して異なるならビットを立てる
        if (
            self.stick_status_new[2] == self.stick_status_old[3]
            and self.stick_status_new[2] == self.stick_status_old[3]
        ):
            self.bits_16 = self.bits_16 & ~(1)
        else:
            self.flag_print = True
            self.bits_16 = self.bits_16 | 1

        if self.bits_16 & 3 == 1:
            self.stick_bits = " %02x %02x" % (self.stick_status_new[2], self.stick_status_new[3])
        elif self.bits_16 & 3 == 2:
            self.stick_bits = " %02x %02x" % (self.stick_status_new[0], self.stick_status_new[1])
        elif self.bits_16 & 3 == 3:
            self.stick_bits = " %02x %02x %02x %02x" % (
                self.stick_status_new[0],
                self.stick_status_new[1],
                self.stick_status_new[2],
                self.stick_status_new[3],
            )
        else:
            self.stick_bits = ""

        # deep copy
        self.stick_status_old[0] = self.stick_status_new[0]
        self.stick_status_old[1] = self.stick_status_new[1]
        self.stick_status_old[2] = self.stick_status_new[2]
        self.stick_status_old[3] = self.stick_status_new[3]

    def event_check(self, events: List[pygame.Event]):
        cnt = 0
        for i, event in enumerate(events):
            if event.type == 1536:
                if event.dict["axis"] < 4:
                    if abs(event.dict["value"]) < 0.3:
                        pass
                    else:
                        pass
                else:
                    if cnt & 0x1 == 0:
                        self.flag_print = True
                        if self.map_axis(event.dict["value"]) >= 128:
                            self.bits_16 = self.bits_16 | (1 << (event.dict["axis"] + 4))
                        else:
                            self.bits_16 = self.bits_16 & ~(1 << (event.dict["axis"] + 4))
                    cnt += 1
            elif event.type == 1539:
                self.flag_print = True
                if event.dict["button"] <= 10 or event.dict["button"] == 15:
                    self.bits_16 = self.bits_16 | (1 << self.button_dict_shift[event.dict["button"]])
                else:
                    self.hat_status = self.hat_status | (1 << self.button_dict_shift[event.dict["button"]])
            elif event.type == 1540:
                self.flag_print = True
                if event.dict["button"] <= 10 or event.dict["button"] == 15:
                    self.bits_16 = self.bits_16 & ~(1 << self.button_dict_shift[event.dict["button"]])
                else:
                    self.hat_status = self.hat_status & ~(1 << self.button_dict_shift[event.dict["button"]])

    def send_message(self, ser: Sender, flag_record: bool):
        # 送信するバイナリデータ生成
        self.message = "0x%04x %01d" % (self.bits_16, self.hat_dict[self.hat_status]) + self.stick_bits

        # コマンドが異なる場合のみ送る
        if self.flag_print and self.old_message != self.message:
            self.time0 = datetime.datetime.today()
            ser.writeRow_wo_perf_counter(self.message, is_show=False)

            # 記録モードになっている場合のみ
            if flag_record:
                self.record_message(False)

        # コマンドが異なることの検知のために保存
        self.old_message = self.message

    def record_message(self, flag_force_write: bool):
        # バイナリデータを追加する。
        message_log = str(self.time0) + "," + self.message + "\n"
        self.controller_log.append(message_log)

        # バイナリデータが100個たまった or 強制書き込み時
        if len(self.controller_log) == 100 or flag_force_write:
            self.f.writelines(self.controller_log)
            self.controller_log = []

    def end_sequence(self, ser: Sender, flag_record: bool):
        self.message = "0x0003 8 80 80 80 80"
        ser.writeRow_wo_perf_counter(self.message, is_show=False)
        if flag_record:
            self.record_message(True)
            self.f.close()
            self._logger.info(f"{self.filename} is closed.")
            print(f"{self.filename} is closed.")

    def controller_loop(self, ser: Sender, flag_record: bool, ControllerLogDir: str):
        self._logger.info("Activate Pro Controller")
        print("*****Activate Pro Controller*****")
        # pygame初期化
        pygame.init()
        joystick = pygame.joystick.Joystick(0)
        joystick.init()
        clock = pygame.time.Clock()

        if flag_record:
            start_time = datetime.datetime.today().strftime("%Y%m%d%H%M%S")
            self.filename = ControllerLogDir + "/controller_log_" + start_time + ".txt"
            self.f = open(self.filename, "w", encoding="UTF-8")
            self._logger.info(f"{self.filename} is opened.")
            print(f"{self.filename} is opened.")
            self.controller_log = []

        self.old_message = ""
        try:
            while self.flag_procon:
                # 60fpsでjoystickの状態を取得
                clock.tick(60)
                # イベント取得
                events = pygame.event.get()
                # print("1")
                # L/R-Stickの変化を検知
                self.joystick_move_detection(joystick)
                # print("2")
                # Button/Hatの処理
                self.event_check(events)
                # print("3")
                # シリアルデータの送信
                self.send_message(ser, flag_record)
                # print("4")
        except Exception:
            pass
        finally:
            # 終了処理
            self.end_sequence(ser, flag_record)
        pygame.quit()
        self._logger.info("Inactivate Pro Controller")
        print("*****Inactivate Pro Controller*****")
