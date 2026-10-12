#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
直した不具合が、元に戻らないことを確かめるテスト
(画像認識のマスク、画像の保存、ポートの開閉、ダイアログのキャンセル、Socket / MQTT、通知の確認結果)

画面・カメラ・通信は使わない(代役を使う)。

SerialController フォルダで実行する:
    python -m unittest discover -s tests
"""
from __future__ import annotations

import contextlib
import io
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import transport_scenarios  # noqa: E402

import Camera as camera_module  # noqa: E402
import DiscordNotify  # noqa: E402
import ExternalTools  # noqa: E402
import LineNotify  # noqa: E402
from Commands import PythonCommandBase  # noqa: E402
from Commands.McuCommandBase import McuCommand  # noqa: E402
from Commands.CommandBase import Command  # noqa: E402
from Commands.Sender import Sender  # noqa: E402
from ImageProcessing import ImageProcessing  # noqa: E402


def frame_image():
    """決まった乱数で作った画像(64x48、BGR)"""
    return np.random.default_rng(3).integers(0, 256, size=(48, 64, 3), dtype=np.uint8)


class TempFolder(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(self.folder, ignore_errors=True))
        self.output = io.StringIO()

    def printed(self):
        return self.output.getvalue()


class ImageProcessingTest(TempFolder):
    def test_template_max_accepts_mask_images(self):
        image = frame_image()
        templates = [image[10:20, 10:22].copy(), image[30:40, 40:52].copy()]
        masks = [np.full((10, 12), 255, np.uint8), np.full((10, 12), 255, np.uint8)]
        with contextlib.redirect_stdout(self.output):
            index, values, places, _, _, judged = ImageProcessing().isContainTemplate_max(image, templates, masks)
            without_mask = ImageProcessing().isContainTemplate_max(image, templates)
            mismatch = ImageProcessing().isContainTemplate_max(image, templates, masks[:1])
        # マスクの数が合っていれば、比べる(以前は、マスクを渡すと必ず -1 だった)
        self.assertIn(int(index), (0, 1))
        self.assertEqual(len(values), 2)
        self.assertEqual([tuple(place) for place in places], [(10, 10), (40, 30)])
        self.assertEqual(judged, [True, True])
        self.assertEqual(len(without_mask[1]), 2)
        # 数が合わないときだけ、-1
        self.assertEqual(mismatch, (-1, [], [], [], [], []))
        self.assertEqual(self.printed().count("don't match"), 1)

    def test_save_image_reports_the_result(self):
        image = frame_image()
        saved = os.path.join(self.folder, "new folder", "画像.png")
        with contextlib.redirect_stdout(self.output):
            ImageProcessing().saveImage(image, filename=saved)
        self.assertTrue(os.path.isfile(saved))
        self.assertIn("capture succeeded: " + saved, self.printed())

    def test_save_image_without_a_name_or_with_a_bad_name_does_not_raise(self):
        image = frame_image()
        bad = os.path.join(self.folder, "image.unknown_format")
        with contextlib.redirect_stdout(self.output):
            ImageProcessing().saveImage(image)
            ImageProcessing().saveImage(image, filename="")
            # 保存できない形式: 以前は、保存できていないのに「capture succeeded」と表示していた
            ImageProcessing().saveImage(image, filename=bad)
        self.assertFalse(os.path.exists(bad))
        self.assertNotIn("capture succeeded", self.printed())
        self.assertEqual(self.printed().count("Capture Failed"), 3)

    def test_save_image_into_the_current_folder(self):
        # フォルダーの部分がない名前でも、エラーにならない
        current = os.getcwd()
        os.chdir(self.folder)
        self.addCleanup(lambda: os.chdir(current))
        with contextlib.redirect_stdout(self.output):
            ImageProcessing().saveImage(frame_image(), filename="plain.png")
        self.assertTrue(os.path.isfile(os.path.join(self.folder, "plain.png")))


class CameraSaveTest(TempFolder):
    def setUp(self):
        super().setUp()
        self.camera = camera_module.Camera()
        self.camera._frame = frame_image()

    def save(self, name, **options):
        with contextlib.redirect_stdout(self.output):
            self.camera.saveCapture(os.path.join(self.folder, name), **options)
        return cv2.imdecode(np.fromfile(os.path.join(self.folder, name + ".png"), np.uint8), cv2.IMREAD_COLOR)

    def test_img_is_saved_instead_of_the_camera_image(self):
        other = np.full((20, 30, 3), 77, np.uint8)
        # 以前は、crop を指定しないと、img を渡してもカメラの画像が保存されていた
        self.assertTrue(np.array_equal(self.save("given", img=other), other))
        self.assertTrue(np.array_equal(self.save("camera"), self.camera._frame))
        cropped = self.save("cropped", crop=1, crop_ax=[2, 3, 12, 9], img=other)
        self.assertEqual(cropped.shape, (6, 10, 3))
        from_camera = self.save("camera_cropped", crop="2", crop_ax=[4, 5, 10, 8])
        self.assertTrue(np.array_equal(from_camera, self.camera._frame[5:13, 4:14]))
        self.assertEqual(self.printed().count("capture succeeded: "), 4)

    def test_failure_is_reported(self):
        self.camera._frame = None
        with contextlib.redirect_stdout(self.output):
            self.camera.saveCapture(os.path.join(self.folder, "none"))
        self.assertFalse(os.path.exists(os.path.join(self.folder, "none.png")))
        self.assertIn("Capture Failed", self.printed())
        self.assertNotIn("capture succeeded", self.printed())


class ContainedImageTest(unittest.TestCase):
    def test_rectangle_is_shown_when_crop_template_is_omitted(self):
        for name in ("Line_Notify", "Discord_Notify"):
            patcher = mock.patch(f"Commands.PythonCommandBase.{name}")
            patcher.start()
            self.addCleanup(patcher.stop)
        frame = frame_image()
        camera, gui = mock.Mock(), mock.Mock()
        camera.readFrame.return_value = frame
        command = PythonCommandBase.ImageProcPythonCommand(camera, gui)
        # 探される側の画像は、スクリーンショットより大きいもの(全体がテンプレートになる)
        image = np.zeros((60, 80, 3), np.uint8)
        image[5:53, 7:71] = frame
        with contextlib.redirect_stdout(io.StringIO()):
            found = command.isContainedImage(image, threshold=0.9)
        self.assertTrue(found)
        # 以前は、ここで IndexError になっていた。四角形は、左上の角から、テンプレートの大きさで表示する
        gui.ImgRect.assert_called_once()
        self.assertEqual(gui.ImgRect.call_args.args, (0, 0, 65, 49))


class SenderTest(unittest.TestCase):
    def setUp(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.sender = Sender(False)

    def test_close_without_an_open_port_does_nothing(self):
        self.assertIsNone(self.sender.ser)
        self.sender.closeSerial()
        port = mock.Mock()
        self.sender.ser = port
        self.sender.closeSerial()
        port.close.assert_called_once()

    def test_port_name_is_opened_with_the_given_baudrate(self):
        with mock.patch("Commands.Sender.serial.Serial") as serial_class, contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(self.sender._openSerial(0, "PORT_A", 115200))
            self.assertTrue(self.sender._openSerial(0, "PORT_B"))
        # 以前は、名前で開くと、いつも 9600 だった
        self.assertEqual([call.args for call in serial_class.call_args_list], [("PORT_A", 115200), ("PORT_B", 9600)])


class StickCommandTest(unittest.TestCase):
    """Commands/StickCommand.py(今は、画面からは使っていない)"""

    def setUp(self):
        from Commands import StickCommand

        self.module = StickCommand
        with contextlib.redirect_stdout(io.StringIO()):
            self.sender = Sender(False)
        self.sender.ser = transport_scenarios.FakeSerial([])
        self.rows = []
        self.sender.writeRow = lambda row, is_show=False: self.rows.append(row)

    def test_end_marks_the_command_as_finished(self):
        with contextlib.redirect_stdout(io.StringIO()):
            left = self.module.StickLeft(self.sender)
            left.start(self.sender)
            self.assertTrue(left.isRunning)
            left.end(self.sender)
        # 以前は、終えた後も isRunning が True のままだった
        self.assertFalse(left.isRunning)

    def test_start_log_names_the_left_stick(self):
        with contextlib.redirect_stdout(io.StringIO()):
            left = self.module.StickLeft(self.sender)
            left._logger = mock.Mock()
            left.start(self.sender)
        left._logger.debug.assert_called_with("Start LeftStick Serial Connection")

    def test_duration_is_waited_after_sending(self):
        with contextlib.redirect_stdout(io.StringIO()):
            left = self.module.StickLeft(self.sender)
            right = self.module.StickRight()
            left.start(self.sender)
            right.start(self.sender)
            # 以前は、duration を使っていなかった
            with mock.patch.object(self.module, "sleep") as sleep:
                left.LStick(0, 1.0, duration=0.25)
                right.RStick(90, 1.0)
        self.assertEqual([call.args for call in sleep.call_args_list], [(0.25,), (0.015,)])
        self.assertEqual(self.rows, ["3 8 0xff 0x80 80 80", "3 8 80 80 0x80 0x0"])


class DialogueCancelTest(unittest.TestCase):
    def test_cancel_in_a_command_without_its_own_finish(self):
        original = Command.dialogue_handler
        self.addCleanup(lambda: setattr(Command, "dialogue_handler", original))
        Command.dialogue_handler = lambda *args, **kwargs: False
        with contextlib.redirect_stdout(io.StringIO()):
            command = McuCommand("sync")
            # 以前は、finish がなく、AttributeError になっていた
            self.assertIsNone(command.dialogue("Title", "a"))
            self.assertIsNone(command.dialogue6widget("Title", [["Entry", "name", "x"]]))
        self.assertIsNone(Command.finish(command))


class ExternalToolsTest(TempFolder):
    def setUp(self):
        super().setUp()
        # 接続先の設定は、一時フォルダーに作らせる(プロファイルの設定ファイルには触れない)
        path = os.path.join(self.folder, "external_token.ini")
        for target in (ExternalTools.SocketCommunications, ExternalTools.MQTTCommunications):
            name = "SOCKET_TOKEN_PATH" if target is ExternalTools.SocketCommunications else "MQTT_TOKEN_PATH"
            patcher = mock.patch.object(target, name, path)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_change_port_is_used_for_the_connection(self):
        with contextlib.redirect_stdout(self.output):
            communication = ExternalTools.SocketCommunications()
        communication.change_ipaddr("192.0.2.1")
        communication.change_port(50001)
        self.assertEqual((communication.PORT, communication.port), (50001, 50001))
        with mock.patch("ExternalTools.socket.socket") as socket_class:
            communication.sock_connect()
        socket_class.return_value.connect.assert_called_once_with(("192.0.2.1", 50001))

    @unittest.skipUnless(ExternalTools.isMQTT, "paho-mqtt が入っていない")
    def test_mqtt_client_can_be_made_and_errors_are_shown(self):
        with contextlib.redirect_stdout(self.output):
            communication = ExternalTools.MQTTCommunications("tester")
            # 以前は、paho-mqtt 2.x で、ここが例外になっていた
            client = communication._new_client()
            self.assertTrue(hasattr(client, "connect"))
            # 送信用のトークンがない: 接続せず、切断もしない(以前は、ない接続を切断しようとしていた)
            self.assertIsNone(communication.pub_token)
            self.assertIsNone(communication.transmit_message("room", "text"))
        self.assertIn("token error(readonly)", self.printed())
        self.assertNotIn("[mqtt:error]", self.printed())
        self.assertNotIn("may not be installed", self.printed())
        # 通信の失敗は、内容を表示する(「入っていない」とは表示しない)
        communication.change_pub_token("dummy")
        failing = mock.Mock()
        failing.connect.side_effect = OSError("no route")
        with mock.patch.object(communication, "_new_client", return_value=failing), \
                contextlib.redirect_stdout(self.output):
            self.assertEqual(communication.transmit_message("room", "text"), "")
        self.assertIn("[mqtt:error]:OSError: no route", self.printed())
        self.assertNotIn("may not be installed", self.printed())

    @unittest.skipUnless(ExternalTools.isMQTT, "paho-mqtt が入っていない")
    def test_mqtt_wait_message_names_mqtt(self):
        with contextlib.redirect_stdout(self.output):
            communication = ExternalTools.MQTTCommunications("tester")
            client = mock.Mock()
            with mock.patch.object(communication, "_new_client", return_value=client), \
                    mock.patch("ExternalTools.time.sleep"):
                # alive が False なので、1 回確かめて戻る
                self.assertIsNone(communication.receive_message2("room", ["a", "b"]))
        self.assertIn("[mqtt:wait]:a,b,", self.printed())
        self.assertNotIn("[socket:wait]", self.printed())
        client.disconnect.assert_called_once()


class NotifyTest(unittest.TestCase):
    @staticmethod
    def response(limit="5"):
        headers = {"X-RateLimit-Limit": limit, "X-RateLimit-ImageLimit": "1", "X-RateLimit-Remaining": "4",
                   "X-RateLimit-ImageRemaining": "1", "X-RateLimit-Reset": "1700000000"}
        return mock.Mock(headers=headers)

    def make(self, cls, statuses):
        notify = object.__new__(cls)
        notify._logger = mock.Mock()
        notify.status = statuses
        return notify

    def test_str_is_always_text(self):
        cases = (
            (LineNotify.Line_Notify, [200], "LINE-Token Check OK!"),
            (LineNotify.Line_Notify, [401, 200], "LINE Token Check FAILED."),
            (LineNotify.Line_Notify, [], "LINE Token Check: not confirmed."),
            (LineNotify.Line_Notify, [500], "LINE Token Check: not confirmed."),
            (DiscordNotify.Discord_Notify, [200], "DISCORD API Check OK!"),
            (DiscordNotify.Discord_Notify, [401], "DISCORD API Check FAILED."),
            (DiscordNotify.Discord_Notify, [], "DISCORD API Check: not confirmed."),
            (DiscordNotify.Discord_Notify, [404], "DISCORD API Check: not confirmed."),
        )
        for cls, statuses, expected in cases:
            with self.subTest(cls=cls.__name__, statuses=statuses):
                # 以前は、どれにも当たらないと None を返し、print で TypeError になっていた
                self.assertEqual(str(self.make(cls, statuses)), expected)

    def test_rate_limit_after_sending(self):
        line = self.make(LineNotify.Line_Notify, [200])
        line.token_list, line.token_num = {"token": "x"}, 1
        line._check_res = [self.response("11")]
        line.res = mock.Mock()  # send_message の後は、リストではない
        discord = self.make(DiscordNotify.Discord_Notify, [200])
        discord.webhook_keys = ["hook"]
        discord._check_res = [self.response("22")]
        discord.res = mock.Mock()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            line.getRateLimit()
            discord.getRateLimit()
            # 確認の応答がないとき(接続を確かめられなかったとき)も、例外にしない
            discord._check_res = []
            discord.getRateLimit()
        self.assertIn("X-RateLimit-Limit: 11", output.getvalue())
        self.assertIn("X-RateLimit-Limit: 22", output.getvalue())


class SmallFixesTest(TempFolder):
    """エラーになる場面をなくした修正と、表示の修正"""

    def test_camera_is_not_opened_before_opening(self):
        # 以前は、一度も開いていないと AttributeError だった
        self.assertIs(camera_module.Camera().isOpened(), False)

    def test_ports_without_a_number_are_listed_last_and_skipped(self):
        from services import serial_service

        ports = [mock.Mock(description=text) for text in ("B (COM12)", "usbserial-A", "A (COM3)", "ttyUSB0")]
        service = serial_service.SerialService(mock.Mock())
        with mock.patch.object(serial_service.list_ports, "comports", return_value=ports):
            # 以前は、番号のないポートがあると、並べ替えで AttributeError だった
            descriptions = service.list_port_descriptions()
        self.assertEqual(descriptions, ["A (COM3)", "B (COM12)", "usbserial-A", "ttyUSB0"])
        self.assertEqual(service.find_description(descriptions, 12), "B (COM12)")
        self.assertIsNone(service.find_description(descriptions, 4))

    def test_panel_handlers_ignore_values_they_cannot_use(self):
        from ui.camera_panel import CameraPanelMixin
        from ui.controller_panel import ControllerPanelMixin
        from ui.serial_panel import SerialPanelMixin

        # 一覧にないカメラの名前: 以前は、Camera ID に None を入れていた
        panel = mock.Mock(camera_dic={0: "Camera A"}, window_ids={}, capture_window="keep")
        panel.camera_name_cb.get.return_value = "No.9: Unknown"
        CameraPanelMixin.set_cameraid(panel)
        panel.camera_id.set.assert_not_called()
        self.assertEqual(panel.capture_window, "keep")
        panel.camera_name_cb.get.return_value = "No.0: Camera A"
        CameraPanelMixin.set_cameraid(panel)
        panel.camera_id.set.assert_called_once_with(0)
        # 番号のないポートを選んだとき: 以前は AttributeError だった
        panel = mock.Mock()
        panel.serial_device_name.get.return_value = "ttyUSB0"
        SerialPanelMixin.set_device(panel)
        panel.com_port.set.assert_not_called()
        panel.serial_device_name.get.return_value = "CH340 (COM7)"
        SerialPanelMixin.set_device(panel)
        panel.com_port.set.assert_called_once_with(7)
        # 開いていない Controller Simulator を閉じる: 以前は AttributeError だった
        panel = mock.Mock(controller=None)
        ControllerPanelMixin.closingController(panel)
        window = mock.Mock()
        panel = mock.Mock(controller=window)
        ControllerPanelMixin.closingController(panel)
        window.destroy.assert_called_once()
        self.assertIsNone(panel.controller)

    def test_keyboard_directions_that_are_not_diagonal_send_nothing(self):
        import Keyboard as keyboard_module
        from Commands.Keys import Direction

        Key = keyboard_module.Key
        controller = object.__new__(keyboard_module.SwitchKeyboardController)
        controller._logger = mock.Mock()
        controller.key = mock.Mock()
        controller.key_map = {Key.up: Direction.UP, Key.down: Direction.DOWN}
        for keys in ([Key.up, Key.down], [Key.left, Key.right], [Key.right, Key.left]):
            controller.inputDir(keys)
        # 以前は、空のリストを送っていた
        controller.key.input.assert_not_called()
        controller.inputDir([Key.up, Key.right])
        controller.key.input.assert_called_once_with([Direction.UP_RIGHT])

    def test_question_text_and_history(self):
        from services.tools_service import ToolError, ToolsService

        core = mock.Mock()
        core.settings.command_history = [
            {"class": "Python", "name": "a"}, {"class": "Mcu", "name": "a"}, {"class": "Python", "name": "b"},
        ]
        tools = ToolsService(core)
        with contextlib.redirect_stdout(self.output):
            text = tools.question_text("Program", "Dev", "Q", "T")
        # 以前は、プログラム名の前に、閉じていない " が入っていた
        self.assertIn("■プログラム名\nProgram\n■製作者様\nDev\n", text)
        self.assertNotIn('"', text)
        # 種別は、書き方が違っても見つける(以前は "py" では見つからなかった)
        tools.delete_history("py", "a")
        self.assertEqual(core.settings.command_history, [{"class": "Mcu", "name": "a"}, {"class": "Python", "name": "b"}])
        tools.delete_history("MCU", "a")
        self.assertEqual(core.settings.command_history, [{"class": "Python", "name": "b"}])
        with self.assertRaises(ToolError):
            tools.delete_history("Python", "none")

    def test_bom_check_closes_the_file_and_accepts_an_empty_file(self):
        empty, with_bom, plain = (os.path.join(self.folder, name) for name in ("empty.ini", "bom.ini", "plain.ini"))
        open(empty, "w").close()
        with open(with_bom, "w", encoding="utf-8-sig") as file:
            file.write("[A]\n")
        with open(plain, "w", encoding="utf-8") as file:
            file.write("[A]\n")
        for cls in (LineNotify.Line_Notify, DiscordNotify.Discord_Notify, ExternalTools.SocketCommunications,
                    ExternalTools.MQTTCommunications):
            with self.subTest(cls=cls.__name__):
                target = object.__new__(cls)
                # 以前は、空のファイルで IndexError だった
                self.assertIs(target.is_utf8_file_with_bom(empty), False)
                self.assertIs(target.is_utf8_file_with_bom(with_bom), True)
                self.assertIs(target.is_utf8_file_with_bom(plain), False)
        # 閉じているので、すぐに消せる
        os.remove(with_bom)

    def test_line_rate_limit_logs_the_image_limit(self):
        line = object.__new__(LineNotify.Line_Notify)
        line._logger = mock.Mock()
        line.token_list, line.token_num = {"token": "x"}, 1
        line._check_res = [NotifyTest.response("11")]
        with contextlib.redirect_stdout(self.output):
            line.getRateLimit()
        logged = [call.args[0] for call in line._logger.info.call_args_list]
        # 以前は、ImageLimit のログに Limit の値(11)を出していた
        self.assertIn("LINE API - ImageLimit: 1", logged)
        self.assertIn("LINE API - Limit: 11", logged)

    def test_logger_color_and_log_folder(self):
        import logging

        import PokeConLogger

        self.assertEqual(PokeConLogger.mapping["WARN"], PokeConLogger.mapping["WARNING"])
        root = logging.getLogger()
        before, level = list(root.handlers), root.level
        urllib3_logger = logging.getLogger("urllib3")
        urllib3_level = urllib3_logger.level
        current = os.getcwd()
        os.chdir(self.folder)
        try:
            # 以前は、./log フォルダーが無いと FileNotFoundError だった
            PokeConLogger.root_logger()
            # 以前は、urllib3 の DEBUG のログ(接続先の URL。Discord の Webhook の URL を含む)が、ログのファイルに書かれた
            connection_logger = logging.getLogger("urllib3.connectionpool")
            self.assertFalse(connection_logger.isEnabledFor(logging.DEBUG))
            self.assertTrue(connection_logger.isEnabledFor(logging.WARNING))
            self.assertTrue(logging.getLogger("Commands.Sender").isEnabledFor(logging.DEBUG))
        finally:
            os.chdir(current)
            for handler in [handler for handler in root.handlers if handler not in before]:
                root.removeHandler(handler)
                handler.close()
            root.setLevel(level)
            urllib3_logger.setLevel(urllib3_level)
        self.assertTrue(os.path.isdir(os.path.join(self.folder, "log")))

    def test_backup_path_keeps_the_folders(self):
        try:
            import PokeConUpdateChecker
        except ImportError:
            self.skipTest("GitPython が入っていない")
        backup = PokeConUpdateChecker.backup_path
        # 以前は、ファイル名だけで退避していたので、別のフォルダーの同じ名前のファイルが上書きされた
        first, second = backup("old", "SerialController/Window.py"), backup("old", "SerialController/ui/Window.py")
        self.assertNotEqual(first, second)
        self.assertEqual(first, os.path.join("old", "SerialController", "Window.py"))
        self.assertEqual(backup("old", "../../x.py"), os.path.join("old", "x.py"))
        self.assertEqual(backup("old", "C:\\a\\b.py"), os.path.join("old", "a", "b.py"))

    def test_check_widget_name_default_is_not_shared(self):
        from services.dialogue_store import check_widget_name

        widgets = [["Entry", "a", ""], ["Check", "b", True]]
        self.assertTrue(check_widget_name(widgets))
        self.assertTrue(check_widget_name(widgets, None))
        self.assertTrue(check_widget_name(widgets, ["c"]))
        self.assertFalse(check_widget_name(widgets, ["b"]))
        self.assertFalse(check_widget_name(widgets + [["Entry", "a", ""]]))
        # 渡したリストは、書き換えない
        names = ["c"]
        check_widget_name(widgets, names)
        self.assertEqual(names, ["c"])

    def test_menu_exit_uses_the_same_steps_as_the_close_button(self):
        import Menubar

        menubar = object.__new__(Menubar.PokeController_Menubar)
        menubar._logger = mock.Mock()
        menubar.app = mock.Mock()
        menubar.ser = mock.Mock()
        menubar.settings = mock.Mock()
        menubar.exit()
        # 以前は、メニューの側だけで終了し、確認も、画面の今の設定の保存もしていなかった
        menubar.app.exit.assert_called_once_with()
        menubar.ser.closeSerial.assert_not_called()
        menubar.settings.save.assert_not_called()

    def test_select_area_is_removed_later_without_blocking(self):
        import time
        import tkinter as tk

        import GuiAssets

        try:
            root = tk.Tk()
        except tk.TclError:
            self.skipTest("画面を使えない環境")
        root.withdraw()
        self.addCleanup(root.destroy)

        class Area(tk.Canvas):
            _select_area_after = None
            _cancelSelectAreaRemoval = GuiAssets.CaptureArea._cancelSelectAreaRemoval
            _removeSelectAreaLater = GuiAssets.CaptureArea._removeSelectAreaLater

        def pump(seconds):
            end = time.perf_counter() + seconds
            while time.perf_counter() < end:
                root.update()
                time.sleep(0.005)

        area = Area(root)
        area.create_rectangle(1, 1, 5, 5, tag="SelectArea")
        start = time.perf_counter()
        area._removeSelectAreaLater()
        # 以前は、ここで画面の処理が 0.25 秒止まっていた
        self.assertLess(time.perf_counter() - start, 0.1)
        self.assertEqual(len(area.find_withtag("SelectArea")), 1)  # すぐには消えない
        pump(0.4)
        self.assertEqual(len(area.find_withtag("SelectArea")), 0)  # 0.25 秒後に消える
        self.assertIsNone(area._select_area_after)
        # 消える前に、次の範囲を選び始めた場合: 新しい枠は消さない
        area.create_rectangle(1, 1, 5, 5, tag="SelectArea")
        area._removeSelectAreaLater()
        area._cancelSelectAreaRemoval()
        area.delete("SelectArea")
        area.create_rectangle(2, 2, 6, 6, tag="SelectArea")
        pump(0.4)
        self.assertEqual(len(area.find_withtag("SelectArea")), 1)

    def test_information_files_are_read_from_the_repository_folder(self):
        import PokeConShowInfo

        # 以前は、今のフォルダーからの相対パス(../)で開いていた
        for name in ("requirements.txt", "changelog.txt", "LICENSE"):
            self.assertTrue(os.path.isfile(os.path.join(PokeConShowInfo.REPOSITORY_DIR, name)), name)


if __name__ == "__main__":
    unittest.main()
