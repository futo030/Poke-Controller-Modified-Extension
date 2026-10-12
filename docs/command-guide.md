# コマンド作成ガイド

コマンド(自動化スクリプト)を作る人向けの補足です。
関数の詳しい説明は、[スクリプトの書き方](../SerialController/assets/manual/scripting.md)(アプリケーションの ヘルプ > Instruction Manual と同じ文章)にあります。

## 作るときの流れ

1. `SerialController/Commands/PythonCommands` の中にフォルダを作り、`.py` ファイルを置きます。
   - メニューの ツール > 新しい自動化スクリプトをつくる を使うと、スクリプト名や格納場所を入力するだけで、そのまま実行できるひな形を作れます。
2. `PythonCommand`(画像認識を使う場合は `ImageProcPythonCommand`)を継承したクラスを書き、`NAME` と `do(self)` を書きます。
3. アプリケーションで Reload を押すと、一覧に表示されます。ファイルを直したときも、Reload で読み込み直せます(再起動は不要です)。
4. テンプレート画像は、プレビュー上で Ctrl + Alt + 左ドラッグ で範囲を選ぶと、名前を付けて保存できます。保存先は `SerialController/Template` の中にします。

## 関数の早見表

`self.関数名(...)` の形で呼びます。「画像」の欄に ○ があるものは、`ImageProcPythonCommand` を継承したクラスでだけ使えます。

### 入力

| 関数 | 内容 | 画像 |
|---|---|---|
| `press(buttons, duration=0.1, wait=0.1)` | 押して離し、待つ | |
| `pressRep(buttons, repeat, duration=0.1, interval=0.1, wait=0.1)` | 繰り返し押す | |
| `hold(buttons, wait=0.1)` / `holdEnd(buttons)` | 押したままにする / 離す | |
| `holdChange(buttons, wait=0.1)` | 押したままの向きを、離さずに切り替える | |
| `wait(wait)` / `short_wait(wait)` | 待つ(秒)。待っている途中でも、Stop を押すと止まります | |
| `KeyBoard_Init()` / `TypeString(text)` / `TypeStringln(text)` | Switch のキーボード画面に文字を打つ | |
| `TypeKey(key)` / `PressKey(key)` / `ReleaseKey(key)` | キーを押す / 押したままにする / 離す | |
| `direct_serial(serialcommands, waittime)` | シリアルに文字列を直接送る | |

### 画像認識と画像

| 関数 | 内容 | 画像 |
|---|---|---|
| `isContainTemplate(template_path, threshold=0.7, ...)` | カメラ画像の中に、テンプレート画像があるか | ○ |
| `isContainTemplate_max(template_path_list, threshold=0.7, ...)` | 複数のテンプレート画像のうち、最も一致するもの | ○ |
| `isContainTemplateGPU(template_path, ...)` | GPU を使った判定 | ○ |
| `isContainedImage(image_path, threshold=0.7, ...)` | カメラ画像が、指定した画像の中にあるか | ○ |
| `getCameraImage(crop_fmt="", crop=[])` | カメラ画像を取得する | ○ |
| `getInterframeDiff(frame1, frame2, frame3, threshold)` | 動いた部分を取り出す | ○ |
| `openImage(filename, mode="t")` | 画像ファイルを読み込む | ○ |
| `saveCapture(filename=None, crop_fmt="", crop=[], mode=True)` | カメラ画像を保存する | ○ |
| `popupImage(crop_fmt="", crop=[], title="image")` | カメラ画像を別の画面に表示する | ○ |
| `displayRectangle(...)` / `displayText(...)` | プレビューに、四角形・文字を表示する | ○ |
| `setTemplateDir(path)` / `get_filespec(filename, mode="t")` | テンプレート画像のフォルダを変える / 実際のパスを得る | ○ |

### 出力とダイアログ

| 関数 | 内容 | 画像 |
|---|---|---|
| `print(...)` | Stdout に選んだ Output に表示する | |
| `print_t1(...)` / `print_t2(...)` | Output#1 / Output#2 に表示する | |
| `print_ts(...)` / `print_t(...)` | Stdout に選んでいる方 / 選んでいない方に表示する | |
| `print_t1b(mode, ...)` / `print_t2b(mode, ...)` / `print_tb(mode, ...)` / `print_tbs(mode, ...)` | 書き込み方を選んで表示する("w": 消して書く、"a": 追記、"d": 消すだけ) | |
| `dialogue(title, message, ...)` | 入力欄だけのダイアログ | |
| `dialogue6widget(title, dialogue_list, ...)` | いろいろな部品を使えるダイアログ | |
| `dialogue6widget_save_settings(...)` / `dialogue6widget_select_settings(...)` | 入力内容を保存できるダイアログ | |
| `show_var()` | self に持たせた変数の一覧を表示する | |

### 通知と通信

| 関数 | 内容 | 画像 |
|---|---|---|
| `discord_text(content="", index=0, keys=..., name=None)` | Discord に文字を送る | |
| `discord_image(content="", index=0, crop_fmt="", crop=[], keys=..., name=None)` | Discord に、文字とカメラ画像を送る | ○ |
| `socket_connect()` / `socket_transmit_message(message)` / `socket_receive_message(header)` など | Socket 通信 | |
| `mqtt_transmit_message(roomid, message)` / `mqtt_receive_message(roomid, header)` など | MQTT 通信 | |

### 実行の制御

| 関数 | 内容 | 画像 |
|---|---|---|
| `finish()` | スクリプトを終了する | |
| `checkIfAlive()` | Stop が押されていたら、ここで終了する(入力や wait を使わない長い処理の途中で呼ぶ) | |
| `reload_com_port()` | シリアルのポートを開き直す | |

## 動きを確かめるときに使える機能

- **一時停止(Pause)**: 止まった位置(ファイルと行)と変数が Output に表示されます。
- **画像認識の表示**: `show_value=True` で一致の度合いを Output に、`show_position=True` で見つかった場所をプレビューに表示します。設定で、スクリプトの書き方によらず常に表示することもできます。
- **座標と色の確認**: プレビュー上で Ctrl + 左クリック すると、その位置の座標と色が Output に表示されます。
- **範囲の保存**: プレビュー上で Ctrl + Shift + 左ドラッグ すると、選んだ範囲を Captures フォルダに保存します。
- **送ったデータとログ**: 右側のパネルの Serial タブに、機器へ送ったデータが、Log タブに、ログが表示されます。出力画面をクリックして Ctrl + F を押すと、出力の中を検索できます。
- **つながっている機器の確認**: 左下の Status タブに、カメラ・音声・シリアルの機器と、実行中のコマンド(開始した時刻)が表示されます。

## ウィンドウの画面と Web ブラウザ版の両方で動かすには

- 値の入力には、`self.dialogue...` の関数を使ってください。どちらの画面でも表示されます。
- スクリプトの中で tkinter を直接使って独自のウィンドウを開くと、Web ブラウザ版では動きません。
- プレビューへの表示は、`displayRectangle` / `displayText` を使ってください。

## Poke-Controller Modified から移すとき

- Modified 版のスクリプトは、そのまま `PythonCommands` に置いて使えます。
- この Extension 版で追加された関数(`print_t1` などの出力、`dialogue6widget...`、Socket・MQTT、キーボード入力など)を使ったスクリプトは、Modified 版では動きません。
- 両方で動くスクリプトにしたい場合は、[bridge_functions](../SerialController/Commands/PythonCommands/bridge_functions) を使うと、版の違いを吸収できます。
- 設定は、プロファイルごとに `SerialController/profiles/プロファイル名` に保存されます。Discord の通知先などは、プロファイルごとに設定します。
