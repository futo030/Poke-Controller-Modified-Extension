import datetime
import logging
from io import TextIOWrapper

import numpy as np
import pygame

from pokecontrollerext.api.v0_1_8.command.sender import Sender

logger = logging.getLogger(__name__)


class ProController:
    flag_procon = False

    def __init__(self) -> None:
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
        self.message = ""
        self.old_message = ""
        self.controller_log: list[str] = []
        self.stick_bits = ""
        self.time0 = datetime.datetime.today()
        self.f: TextIOWrapper | None = None

    # stickの出力を0-255の範囲に補正する。
    # noinspection PyMethodMayBeStatic
    def map_axis(self, val: float) -> int:
        val = round(val, 3)
        in_min = -1
        in_max = 1
        out_min = 0
        out_max = 255
        return int((val - in_min) * (out_max - out_min) / (in_max - in_min) + out_min)

    def joystick_move_detection(self, joystick: pygame.joystick.JoystickType) -> None:
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
            self.bits_16 = self.bits_16 & ~2
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
            self.bits_16 = self.bits_16 & ~1
        else:
            self.flag_print = True
            self.bits_16 = self.bits_16 | 1

        if self.bits_16 & 3 == 1:
            self.stick_bits = " %02x %02x" % (
                self.stick_status_new[2],
                self.stick_status_new[3],
            )
        elif self.bits_16 & 3 == 2:
            self.stick_bits = " %02x %02x" % (
                self.stick_status_new[0],
                self.stick_status_new[1],
            )
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

    def event_check(self, events: list[pygame.event.Event]) -> None:
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
                            self.bits_16 = self.bits_16 | (
                                1 << (event.dict["axis"] + 4)
                            )
                        else:
                            self.bits_16 = self.bits_16 & ~(
                                1 << (event.dict["axis"] + 4)
                            )
                    cnt += 1
            elif event.type == 1539:
                self.flag_print = True
                if event.dict["button"] <= 10 or event.dict["button"] == 15:
                    self.bits_16 = self.bits_16 | (
                        1 << self.button_dict_shift[event.dict["button"]]
                    )
                else:
                    self.hat_status = self.hat_status | (
                        1 << self.button_dict_shift[event.dict["button"]]
                    )
            elif event.type == 1540:
                self.flag_print = True
                if event.dict["button"] <= 10 or event.dict["button"] == 15:
                    self.bits_16 = self.bits_16 & ~(
                        1 << self.button_dict_shift[event.dict["button"]]
                    )
                else:
                    self.hat_status = self.hat_status & ~(
                        1 << self.button_dict_shift[event.dict["button"]]
                    )

    def send_message(self, ser: Sender, flag_record: bool) -> None:
        # 送信するバイナリデータ生成
        self.message = (
            "0x%04x %01d" % (self.bits_16, self.hat_dict[self.hat_status])
            + self.stick_bits
        )

        # コマンドが異なる場合のみ送る
        if self.flag_print and self.old_message != self.message:
            self.time0 = datetime.datetime.today()
            ser.writeRow_wo_perf_counter(self.message, is_show=False)

            # 記録モードになっている場合のみ
            if flag_record:
                self.record_message(False)

        # コマンドが異なることの検知のために保存
        self.old_message = self.message

    def record_message(self, flag_force_write: bool) -> None:
        # バイナリデータを追加する。
        message_log = str(self.time0) + "," + self.message + "\n"
        self.controller_log.append(message_log)

        # バイナリデータが100個たまった or 強制書き込み時
        if len(self.controller_log) == 100 or flag_force_write:
            if (opened_file := self.f) is not None:
                opened_file.writelines(self.controller_log)
            self.controller_log = []

    def end_sequence(self, ser: Sender, flag_record: bool) -> None:
        self.message = "0x0003 8 80 80 80 80"
        ser.writeRow_wo_perf_counter(self.message, is_show=False)
        if flag_record:
            self.record_message(True)
            if (opened_file := self.f) is not None:
                opened_file.close()
            logger.info(f"{self.filename} is closed.")

    def controller_loop(
        self,
        ser: Sender,
        flag_record: bool,
        ControllerLogDir: str,  # noqa
    ) -> None:
        logger.info("Activate Pro Controller")
        # pygame初期化
        pygame.init()
        joystick = pygame.joystick.Joystick(0)
        joystick.init()

        if flag_record:
            start_time = datetime.datetime.today().strftime("%Y%m%d%H%M%S")
            self.filename = ControllerLogDir + "/controller_log_" + start_time + ".txt"
            self.f = open(self.filename, "w", encoding="UTF-8")
            logger.info(f"{self.filename} is opened.")
            self.controller_log = []

        self.old_message = ""
        try:
            while self.flag_procon:
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
        except Exception:  # noqa
            pass
        finally:
            # 終了処理
            self.end_sequence(ser, flag_record)
        pygame.quit()
        logger.info("Inactivate Pro Controller")
