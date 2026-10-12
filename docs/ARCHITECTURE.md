# フォルダの構成と、層の分け方

コードを読む人・直す人向けの説明です。

## 全体の形

画面を2種類(これまでのウィンドウの画面と、Web ブラウザ版)持つため、処理を「画面に依存しない部分」と「画面」に分けています。

```
            ┌────────────────────┐   ┌────────────────────┐
  画面      │ ui/ (tkinter)      │   │ web/ (FastAPI + JS) │
            │ Window.py が組み立て │   │ web/main.py が起動   │
            └─────────┬──────────┘   └─────────┬──────────┘
                      │                        │
            ┌─────────▼────────────────────────▼──────────┐
  処理      │ services/  画面に依存しない処理                │
            │ (設定、シリアル、コマンドの実行、出力、記録 …)   │
            └─────────┬────────────────────────────────────┘
                      │
            ┌─────────▼────────────────────────────────────┐
  土台      │ Commands/ (送信・入力の合成・コマンドの基底クラス) │
            │ Camera.py / Audio.py / Settings.py など         │
            └──────────────────────────────────────────────┘
```

- 上の層は下の層を使えますが、**下の層は上の層(画面)を読み込みません**。
- この決まりは、`tests/test_layering.py` が検査します(`services/` と土台のファイルが、tkinter・`ui`・`Window` を読み込んでいないこと)。

## SerialController の中

| 場所 | 内容 |
|---|---|
| `Window.py` | 起動時の引数の処理、ウィンドウの画面の組み立て、設定の読み込みと保存、終了の処理 |
| `Monitor.py` | 補助ツール(モニター)。複数起動したウィンドウの状態・Output・映像をまとめて表示する、別のプログラム。本体側のつなぎ役は `ui/monitor_link.py`(Web ブラウザ版は `web/monitor_link.py`) |
| `ui/` | ウィンドウの画面(tkinter)。タブ・機能ごとのファイルで、`Window.py` のクラスに Mixin として組み込む |
| `web/` | Web ブラウザ版。`server.py`(FastAPI。画面との通信)、`preview.py`(映像の配信)、`dialogue.py`(ダイアログ)、`monitor_link.py`(補助ツールとのつなぎ役)、`static/`(HTML・CSS・JavaScript。ツールの画面は `tools.js`、`outview.js`(出力画面の Serial / Log タブと検索)) |
| `services/` | 画面に依存しない処理。下の表を参照 |
| `Commands/` | シリアルへの送信(`Sender.py`)、入力の表し方と合成(`Keys.py`)、コマンドの基底クラス(`CommandBase.py` / `PythonCommandBase.py` / `McuCommandBase.py`)、コントローラー関連 |
| `Commands/transport/` | 送信方式。送るデータの形式(画面の Data Format)ごとの処理。下の「送るデータの形式を足すとき」を参照 |
| `Commands/PythonCommands/` | 利用者が置くスクリプト。`Samples/` と `bridge_functions/` だけをリポジトリに含める |
| `Camera.py` / `Audio.py` / `WindowCapture.py` | 映像・音声の取り込み |
| `Settings.py` / `Profile.py` | 設定ファイルと、プロファイル |
| `assets/` | Instruction Manual(`manual/`)と機能紹介(`introduction/`)の文章と画像 |
| `Theme.py` / `themes/` | テーマ(配色)と、利用者が作ったテーマのファイルの置き場所 |
| `tools/` | 開発用の道具。`make_introduction_images.py` は、機能紹介の画像を、アプリの画面から作り直す(画面を変えたときに実行する) |
| `tests/` | テスト(カメラ・シリアル・コントローラーをつながずに実行できるもの) |
| `profiles/` | プロファイルごとの設定(`default` の初期値だけをリポジトリに含める) |

### services/ の主なファイル

| ファイル | 内容 |
|---|---|
| `app_core.py` | 画面なしで動く本体(`AppCore`)。下の部品を組み立て、変化を画面へ知らせる。Web ブラウザ版はこれを使う |
| `settings_store.py` / `settings_control.py` | 設定の読み書き、設定の変更と候補の一覧 |
| `serial_service.py` / `device_service.py` / `audio_service.py` | シリアルの接続、カメラ・音声のデバイスの一覧、音声の取り込み |
| `command_service.py` / `command_catalog.py` | コマンドの読み込み・開始・停止、一覧の絞り込みと並び替え、実行履歴 |
| `run_list.py` / `run_schedule.py` | 実行リスト(コマンドの連続実行。保存と、中のコマンドを順に動かすコマンド)、開始と停止の予約 |
| `sleep_watch.py` | PC がスリープから戻ったことの検知(戻ったら、実行中のコマンドを止める) |
| `note_store.py` / `diagnostics.py` | Note タブの内容の読み書き(プロファイルごと)、環境の診断(調べるだけ) |
| `log_buffer.py` | ログを、Output の Log タブに渡す受け渡し(溜めるだけ。文字にするのは、表示するとき) |
| (リポジトリ直下の `bootstrap/`) | 環境の用意と起動。uv を探す・入れる(`uv_tool.py`)、`.venv` を作る・そろえる(`environment.py`)、`.venv` の Python で起動し直す(`relaunch.py`)、以前からの環境からの移行(`migrate.py`、`added_libraries.py`)、bat からの入口(`__main__.py`、初回だけ `setup.ps1`)。**本体のコードを読み込まず、Python の標準の機能だけで書く**(`tests/test_bootstrap.py` が検査する)。本体は、`Window.py` などの先頭の数行(起動し直し)を除いて、uv のことを知らない |
| `update_check.py` / `release_update.py` | 更新の確認(GitHub の最新の Release が、手元のバージョンより新しいか。標準の機能で通信する)と、git を使わない更新(Release の ZIP を取得して、版の間で変わったファイルだけを入れ替える)。確認は、tkinter 版のメニュー・Web ブラウザ版・起動前の `PokeConUpdateChecker.py` が使う。更新は、`PokeConUpdateChecker.py` が行う(git で取得したフォルダーでは `git pull`) |
| `status_text.py` | Status タブに表示する文字(つながっている機器と、実行中のコマンド)を作る |
| `command_usage.py` | コマンドを実行した回数の記録(使用頻度での並び替え。プロファイルに関係なく共通) |
| `output_service.py` / `dialogue_store.py` | Output への書き込みの受け渡し、ダイアログの入力内容の保存 |
| `record_service.py` / `software_controller.py` / `controller_setup_service.py` | 操作の記録、画面上のコントローラー、コントローラーのボタンの割り当て |
| `editor_service.py` / `tools_service.py` | ショートカット・Mask・キーの対応などの編集、Capture・履歴・ヘルプなどの道具 |
| `tag_session.py` / `keyboard_session.py` / `monitor_relay.py` | タグの編集・Keyboard・モニターの画面の中身(画面を持たない版。Web ブラウザ版が使う)。読み書きや送信は、`tag_editor.py`・`keyboard_typer.py`・`monitor_client.py` が行う |
| `monitor_server.py` / `monitor_client.py` | 補助ツール(モニター)とのやり取り。本体側の窓口(`--monitor` のときだけ開く。127.0.0.1 のみ)と、補助ツール側の接続。形式は `monitor_server.py` の先頭に記載 |

## 機能を足すときの置き場所

1. **処理**は `services/` に書きます(tkinter を import しない)。テストも `tests/` に足します。
2. **ウィンドウの画面**は `ui/` の該当するファイルに、**Web ブラウザ版**は `web/server.py` の操作と `web/static/` に足します。画面の側は、`services/` を呼ぶだけにします。
3. **スクリプトから使う関数**は `Commands/PythonCommandBase.py`(共通のものは `CommandBase.py`)に足し、`assets/manual/scripting.md` に説明を書きます。
4. 設定の項目を足す場合は、`Settings.py` と `services/settings_store.py` / `settings_control.py` に足します。

## 送るデータの形式を足すとき

送るデータの形式(画面の Data Format)ごとの違いは、`Commands/transport/` にまとめています。`Sender.py` や画面は、形式の名前で分岐せず、今の形式の送信方式(`Transport`)に問い合わせます。

| ファイル | 内容 |
|---|---|
| `base.py` | 共通の型 `Transport`(下の表の項目を持つ) |
| `text_serial.py` | Default(文字列の行) |
| `nx_macro.py` | NX(NX Macro Controller の形式。11 バイト。キーボードの操作も同じデータで送る) |
| `qingpi.py` / `controller_3ds.py` | Qingpi / 3DS Controller(11 バイト) |
| `ds_ft.py` | FTDI 直結の DS 基板(ピンの状態。COM ポートではなく FTDI のデバイスを開く) |
| `registry.py` | 登録簿(形式の名前 → `Transport`)。画面の一覧は、登録した順に並ぶ |

`Transport` が持つ項目:

| 項目 | 内容 |
|---|---|
| `name` | 形式の名前。画面に表示し、設定ファイルにも保存する(変えると、保存済みの設定が合わなくなる) |
| `baud_rate` | 形式で決まるボーレート(`None`: 使わない) |
| `button_conversion` | Button → 送るビット の対応 |
| `has_touchscreen` / `supports_text` | タッチスクリーンを送れるか / 文字列の行(キーボード入力の関数など)を送れるか |
| `allows_raw_write` | 入力の合成を経由しない送信(Mcu コマンドなど)を、そのまま送ってよいか |
| `end_row` | コマンドの終了時に送る行(`None`: 入力を離した状態を送る) |
| `skip_unchanged` | 前回と同じデータなら送らないか |
| `is_available()` | この環境で使えるか(必要なライブラリが入っているか) |
| `open(...)` | ポートの開き方(既定は COM ポート) |
| `encode(state, last_sent, encoder, port)` | 合成した入力を、送るデータにする(文字列・bytes・数値のリスト。`None` は送らない) |
| `keyboard_steps(kind, value)` / `encode_keyboard(...)` | Switch へのキーボード入力の手順(送るものと、待つ時間)。使えない形式は `None` |

手順:

1. `Transport` を継承したクラスを書き、`name` と `encode` を決めます(必要な項目だけ上書きします)。
2. `registry.py` に `register(...)` を1行足します。これで、画面の一覧・ボーレート・送信に反映されます。
3. `tests/transport_scenarios.py` の `FORMATS` に名前を足し、`python tests/transport_scenarios.py --write` で、送るデータの記録を作ります。記録の内容が意図どおりかを確認してください。
4. `tests/test_transport_golden.py` は、どの形式でも、送るデータが記録と変わらないことを確かめます。

## スレッド

- コマンドは、専用のスレッドで実行します。画面(tkinter)の操作は、画面のスレッドに渡して行います(`UiDispatcher.py`)。
- カメラの読み取り、シリアルの送信、音声の取り込みも、それぞれ専用のスレッドです。
- 入力は、入力源(コマンド、キーボード、コントローラー、画面上のコントローラー、マウス)ごとの状態を、優先度に従って合成して送ります(`Commands/Sender.py`)。

## 文書の置き場所

| 文書 | 場所 |
|---|---|
| Instruction Manual(ウィンドウの画面) | `assets/manual/manual.md` |
| Instruction Manual(Web ブラウザ版) | `assets/manual/manual_web.md` |
| スクリプトの書き方(両方の Instruction Manual に表示) | `assets/manual/scripting.md` |
| 機能紹介 | `assets/introduction/introduction.md` / `introduction_web.md` |
| 更新履歴 | `changelog.txt`(リポジトリの直下) |
