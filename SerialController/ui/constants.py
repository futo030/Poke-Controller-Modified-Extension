#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
メイン画面で使う定数
"""
from __future__ import annotations

import os

try:
    from plyer import notification  # noqa: F401 (読み込めるかどうかを調べる)

    flag_import_plyer = True
except Exception:
    flag_import_plyer = False

# 出力画面(Notebook)のページ数
OUTPUT_PAGE_NUM = 3
# 出力画面(Notebook)のタブ表示で消費する高さ(Textの行数換算、各Output毎)
OUTPUT_NB_TAB_LINES = 1
# 出力画面の最小の行数(これより少ないと、スクロールバーの最小の高さの方が大きくなる)
OUTPUT_MIN_LINES = 4
# 出力画面(各Textウィジェット)に保持する最大行数(超えた分は古い行から削除)
OUTPUT_MAX_LINES = 10000
# 出力キューを出力画面に反映する間隔(ms)
OUTPUT_FLUSH_INTERVAL_MS = 50
# スレッド切り替え間隔(秒)。Pythonの既定値は0.005
# コマンド実行スレッドがGILを待つ時間の上限を短くし、待機やボタン操作のタイミングのずれを抑える
GIL_SWITCH_INTERVAL = 0.001
# Shortcutタブのボタンの列数 (行数はショートカット数から決まる)
SHORTCUT_COLUMNS = 4
# ミニ画面: ウィンドウの中身の幅(Software-Controllerの幅380pxが収まる幅)
MINI_WIDTH = 399
# ミニ画面: Shortcutタブのボタンの列数、コマンド一覧(Commandsの小タブ)の幅
MINI_SHORTCUT_COLUMNS = 3
MINI_COMMAND_NB_WIDTH = 362
# ミニ画面: 出力画面の行数(表示サイズに連動させず固定する)。Output#1、Output#2、片方だけ表示する場合
MINI_OUTPUT_LINES_1 = 4
MINI_OUTPUT_LINES_2 = 5
MINI_OUTPUT_LINES_SINGLE = 9
# ミニ画面でパネルを右に置いたときの出力画面の行数。1画面(1920x1080)に2×2で4つ並べられる高さにする
MINI_RIGHT_OUTPUT_LINES_1 = 3
MINI_RIGHT_OUTPUT_LINES_2 = 4
MINI_RIGHT_OUTPUT_LINES_SINGLE = 8
# 右側のパネル(Output・Software-Controller)の位置と、Panelボタンに表示する文字(押すたびに 右 → 下 → 表示しない の順)
PANEL_POSITIONS = ("right", "bottom", "hidden")
PANEL_BUTTON_TEXTS = {"right": "Panel ▶", "bottom": "Panel ▼", "hidden": "Panel ✕"}
# パネルを下に置いたとき(通常の画面)の出力画面の行数。Output と Software-Controller を横に並べ、高さをそろえる
BOTTOM_OUTPUT_LINES_1 = 4
BOTTOM_OUTPUT_LINES_2 = 5
BOTTOM_OUTPUT_LINES_SINGLE = 11
# 通常の画面で、中身に合わせた大きさにするときの出力画面の行数(右側のパネル)
DEFAULT_OUTPUT_LINES_1 = 10
DEFAULT_OUTPUT_LINES_2 = 14
# 出力画面の幅(文字数)。パネルを下に置いて横に並べるときは、詰める
OUTPUT_TEXT_WIDTH = 50
OUTPUT_TEXT_WIDTH_HORIZONTAL = 20
# コマンド一覧(Python/Mcu)に表示する行数: 通常画面、ミニ画面
COMMAND_TREE_LINES = 3
MINI_COMMAND_TREE_LINES = 4
# ミニ画面: 上段のPause/Reloadボタンを、Commandsタブのボタンの状態に合わせる間隔(ms)
MINI_BUTTON_SYNC_INTERVAL_MS = 150
# Commandsの小タブの名前(通常画面、ミニ画面)
COMMAND_TAB_NAMES = (("Python Command", "Python"), ("Mcu Command", "Mcu"))
# Shortcutボタンに表示するコマンド名の最大文字数
SHORTCUT_TEXT_LENGTH = 12
# Proコントローラーのスレッドの停止を待つ時間の上限(秒)
PROCON_STOP_TIMEOUT = 3.0
# 操作記録の生ログを書き出すフォルダ
CONTROLLER_LOG_DIR = "Controller_Log"
# 目隠し(Mask)を書き出すファイルの置き場所
# Screenshotで透明にする、ウィンドウの四隅の丸みの半径(Windows 11の丸みは8px。枠を削った分を含めて少し大きめに切る)
WINDOW_CORNER_RADIUS = 9
# プレビュー(Main Panel)の高さの下限(px)。ミニ画面のプレビューもこの高さになる
PREVIEW_MIN_HEIGHT = 160
# ミニ画面のプレビューの高さの下限(px)。ミニ画面に切り替えたときは、この高さにする
MINI_PREVIEW_MIN_HEIGHT = 180
# Main Panel の大きさが変わってから、プレビューの大きさを合わせるまでの時間(ms)。
# 枠や仕切り線をドラッグしている間は何度も大きさが変わるので、止まってから合わせる
PREVIEW_RESIZE_DELAY_MS = 150
# プレビューの明るさ(表示だけ): ゲイン(%)とガンマの範囲と初めの値
PREVIEW_GAIN_RANGE = (50, 300)
PREVIEW_GAMMA_RANGE = (0.5, 2.5)
DEFAULT_PREVIEW_GAIN = 100
DEFAULT_PREVIEW_GAMMA = 1.0
# スクリーンショットの保存で、明るさを変える前の画像に描き直してから撮るまでの待ち時間(秒)
SCREENSHOT_REDRAW_WAIT_S = 0.05
# 仕切り線の太さ(px)。色はテーマの sash(目立たないよう、背景よりわずかに濃い平らな線)
SASH_WIDTH = 3
# ウィンドウの大きさが変わってから、仕切り線を比率の位置に置き直すまでの時間(ms)
SASH_PLACE_DELAY_MS = 40
# プレビューのまわりの余白(px)
PREVIEW_PAD = 5
# 右側のパネル・下のパネルの大きさの下限(px)
PANEL_MIN_WIDTH = 389
PANEL_MIN_HEIGHT = 120
# Output#1 と Output#2 の高さの比率(Others タブの Size)の初めの値(%)
DEFAULT_AREA_SIZE = 20
# ミニ画面の Widget Mode・Clear Outputs の行の下の余白(px)
MINI_PANEL_PAD = 4
# 入力したプレビューの大きさを、画面に収まる大きさに制限するときの余白(px。タスクバーやタイトルバーの分)
PREVIEW_SCREEN_MARGIN = 80
# 起動してから機能紹介を表示するまでの時間(ms)。メイン画面の大きさが決まった後に表示する
INTRODUCTION_DELAY_MS = 800
# 出力画面の、クリックで処理を行うリンク(OutputLinks)の文字に付けるタグ
ACTION_LINK_TAG = "action_link"
ACTION_LINK_TAG_PREFIX = "action_link_"
# リンクを押してから離すまでに、この距離(px)より動いた場合は、文字を選択するドラッグとして扱う
ACTION_LINK_DRAG_PIXELS = 3
# 出力画面で、画像を保存したときの行(この文字の後ろが保存先のパス)をリンクにする
CAPTURE_LINK_PREFIX = "capture succeeded: "
CAPTURE_LINK_TAG = "capture_link"
# Note タブ: 書き換えてから、保存するまでの待ち時間(ms)
NOTE_SAVE_DELAY_MS = 1000
# Log タブで、ログのレベルごとに付けるタグ(services.log_buffer のレベルの分け方 -> タグ。レベルの低い順)。
# 文字の色を変えるのと、レベルでの絞り込み(タグごとに隠す)に使う。INFO は、色を変えない
LOG_LEVEL_TAGS = {"debug": "log_debug", "info": "log_info", "warning": "log_warning", "error": "log_error"}
# Log タブの、レベルでの絞り込みの選択肢: (そのレベル以上を表示する分け方, 表示名)
LOG_LEVEL_CHOICES = (
    ("debug", "すべて (DEBUG 以上)"),
    ("info", "INFO 以上"),
    ("warning", "WARNING 以上"),
    ("error", "ERROR 以上"),
)
# WARNING の文字の色(明るいテーマ用, 暗いテーマ用)。DEBUG と ERROR は、テーマの「薄い文字」「赤」の色を使う
LOG_WARNING_COLORS = ("#9a6700", "#e0b341")
# コマンド一覧の並び順(Command列の見出しクリックで選ぶ): (キー, 表示名, 見出しに付ける表示)
COMMAND_SORT_DEFAULT = "default"
COMMAND_SORTS = (
    (COMMAND_SORT_DEFAULT, "既定の順", ""),
    ("name_asc", "名前 (昇順)", "名前 ▲"),
    ("name_desc", "名前 (降順)", "名前 ▼"),
    ("mtime_asc", "更新日時 (古い順)", "更新日時 ▲"),
    ("mtime_desc", "更新日時 (新しい順)", "更新日時 ▼"),
    ("usage_desc", "使用頻度 (多い順)", "使用頻度 ▼"),
    ("usage_asc", "使用頻度 (少ない順)", "使用頻度 ▲"),
)
# (このファイルは SerialController/ui にあるので、1つ上のフォルダを基準にする)
MASK_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Masks")
# AudioタブのOutputで、既定の再生デバイスを表す選択肢
AUDIO_OUTPUT_DEFAULT = "Default"
# Audioタブの音量メーターを更新する間隔(ms)と、メーターの下限(dBFS)
AUDIO_METER_INTERVAL_MS = 100
AUDIO_METER_MIN_DB = -60.0
# 音声がこの時間(秒)届かなければ、Audioタブに「No signal」と表示する
AUDIO_NO_SIGNAL_SECONDS = 1.0
