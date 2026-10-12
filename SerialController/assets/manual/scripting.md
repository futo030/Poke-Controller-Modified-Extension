<!--
スクリプト(コマンド)の書き方の説明。
アプリケーションの ヘルプ > Instruction Manual にも、この文章がそのまま表示される(ウィンドウの画面・Web ブラウザ版の両方)。
「# 見出し」が Instruction Manual の1項目になる。書き方の決まりは、同じフォルダの manual.md と同じ。
-->

# スクリプトの作り方

自動化スクリプト(コマンド)は、Python のクラスとして書きます。

## 置き場所
- SerialController/Commands/PythonCommands フォルダ(その中のフォルダでも可)に、.py ファイルを置きます。
- ファイルを置いたら、Commands タブの Reload を押すと一覧に表示されます。

## ひな形から作る(新しい自動化スクリプトをつくる)
- メニューの ツール > 新しい自動化スクリプトをつくる を選ぶと、次の項目を入力する画面が開きます。作成 を押すと、そのまま実行できる .py ファイルを作り、エディタで開きます。
- スクリプト名: コマンドの一覧に表示する名前(NAME)です。日本語も使えます。
- 作成者名: スクリプト(BridgeFunctions を使用する場合の、プログラム情報の表示)と、README.md・License.txt に書く名前です。空にすると「(名前)」と書いておくので、後で書き換えます。一度入力すると、次に開いたときにも入っています(アプリケーションを起動し直しても、残ります)。
- ファイル名: .py ファイルの名前です。半角の英数字と「-」「_」だけが使えます(.py は自動で付きます)。クラスの名前は、ファイル名から作ります(my_script なら MyScript)。
- スクリプト格納場所: Commands/PythonCommands の中のフォルダーです。今あるフォルダーから選ぶか、新しい名前を入力します(なければ作ります。「A/B」のように重ねられます)。「(直下)」は、フォルダーに入れません。
- BridgeFunctions の使用: 使用する にすると、Poke-Controller Modified でも同じスクリプトを動かすための橋渡し関数(Commands/PythonCommands/bridge_functions)を使う形で作ります。中身は、bridge_functions/Sample/bf_sample.py と同じ流れ(橋渡し関数の用意 → プログラム情報の表示 → テンプレートのフォルダーの設定)です。
- どちらの場合も、ウィジェット(ダイアログ)の例を、コメントにして入れてあります。使うときは、その部分の行頭の「# 」を外します。BridgeFunctions を使用する場合は、設定を保存・選択できるダイアログの例、使用しない場合は、self.dialogue6widget と print だけを使った例です。
- 画像保存先: テンプレート画像を置くフォルダーです(なければ作ります)。初めは、ファイル名と同じ名前が入ります。空にすると、画像を使わないスクリプト(PythonCommand)を作ります。
- 画像保存先の場所は、「Template/」(SerialController/Template の中)か、「[スクリプト格納場所]/」(スクリプトと同じフォルダーの中)から選びます。「[スクリプト格納場所]/」を選べるのは、BridgeFunctions を使用する場合だけです(Poke-Controller Modified では場所を変えられないので、Template の中の画像が使われます)。
- スクリプト格納場所に、README.md(説明)と License.txt(利用の条件)のひな形も作ります。どちらも、bridge_functions フォルダーのものと同じ形です(License.txt は、商用利用を禁止する内容です)。要約と使い方の手順は、作った後に書き足してください。すでに同じ名前のファイルがある場合は、作りません。
- 同じ名前のファイルがすでにある場合は、上書きせず、その旨を表示します。
- 作ったコマンドは、一覧で選んだ状態になります。Start を押すと、開始と終了の文字を Output に表示するだけの動きをします。do の中を書き換えて、Reload を押してから実行してください。

## 基本の形
- PythonCommand を継承したクラスを作り、NAME に一覧に表示する名前を書きます。
- do(self) の中に、実行する処理を書きます。do が終わると、コマンドは終了します。
```
from Commands.Keys import Button, Direction, Hat
from Commands.PythonCommandBase import PythonCommand


class MashA(PythonCommand):
    NAME = "A連打"
    TAGS = ["Sample"]

    def __init__(self):
        super().__init__()

    def do(self):
        while True:
            self.wait(0.5)
            self.press(Button.A)
```
- TAGS は省略できます。書くと、Commands タブの Tags で絞り込めます。Commands タブのタグの絵のボタン(タグの編集画面)からも変更できます。
- 一覧には「NAME (フォルダ/ファイル名)」の形で表示されます。フォルダ名は「@フォルダ名」のタグにもなります。

## 画像認識を使う場合
- ImageProcPythonCommand を継承します。__init__ は cam を受け取ります。
```
from Commands.Keys import Button
from Commands.PythonCommandBase import ImageProcPythonCommand


class WaitLogo(ImageProcPythonCommand):
    NAME = "ロゴが出るまでA"

    def __init__(self, cam):
        super().__init__(cam)

    def do(self):
        while not self.isContainTemplate("Samples/logo.png"):
            self.press(Button.A, wait=1.0)
        print("見つかりました")
```

## 止め方
- Stop を押すと、次に press や wait などを呼んだところで止まります。長い計算だけを続ける処理は止まらないので、途中で self.checkIfAlive() を呼んでください。
- 長い wait や、長く押す press の途中で Stop を押した場合は、待ち終わるのを待たずに、0.1 秒ほどで止まります。
- スクリプトの中から終わらせるときは、self.finish() を呼びます。

## 一時停止する場所
- Pause を押すと、次の場所で一時停止します。
- press / pressRep / hold / holdEnd / holdChange / wait / short_wait: 処理の後(press はボタンを離した後)
- isContainTemplate / isContainTemplate_max / isContainTemplateGPU / isContainedImage: 判定する前(再開後の画面で判定します)
- 上のどれも呼ばない処理(長い計算や、自分で書いたループ)の途中では止まりません。
- hold で押したままの入力は、一時停止中も押したままです。

## サンプル
- Commands/PythonCommands/Samples に、各機能のサンプルがあります。

# スクリプト: ボタン操作

PythonCommand で使える、入力を送るコマンドです。時間の単位は秒です。

## 入力の書き方(Commands.Keys)
- Button: Button.A / B / X / Y / L / R / ZL / ZR / MINUS / PLUS / LCLICK / RCLICK / HOME / CAPTURE。3DS 用の別名として SELECT(=MINUS)/ START(=PLUS)/ POWER / WIRELESS があります。
- Hat(十字キー): Hat.TOP / TOP_RIGHT / RIGHT / BTM_RIGHT / BTM / BTM_LEFT / LEFT / TOP_LEFT
- Direction(スティック): 左は Direction.UP / RIGHT / DOWN / LEFT / UP_RIGHT など、右は Direction.R_UP / R_RIGHT など。
- 角度と倒し量を指定する場合は Direction(Stick.LEFT, 角度, 倒し量) と書きます。角度は右が0度で反時計回り(上が90度)、倒し量は 0.0~1.0 です。
- Touchscreen(x, y): タッチスクリーン(Qingpi / 3DS)。x は 0~319、y は 0~239 です。
- 複数の入力を同時に送るときは、リストで渡します。例: [Button.A, Direction.UP]

## press(buttons, duration=0.1, wait=0.1)
- buttons を duration 秒押して離し、そのあと wait 秒待ちます。
```
self.press(Button.A)
self.press(Direction.UP, duration=1.0, wait=0.5)
self.press([Button.B, Hat.LEFT], wait=1.0)
```

## pressRep(buttons, repeat, duration=0.1, interval=0.1, wait=0.1)
- buttons を repeat 回押します。押す間隔は interval 秒、最後に wait 秒待ちます。

## hold(buttons, wait=0.1) / holdEnd(buttons)
- hold は buttons を押したままにし、holdEnd で離します。
```
self.hold(Direction.UP)
self.press(Button.B, wait=2.0)
self.holdEnd(Direction.UP)
```

## holdChange(buttons, wait=0.1)
- 押したままのスティックや十字キーの向きを、離さずに切り替えます。(holdEnd → hold では、一度ニュートラルに戻ります)

## wait(wait) / short_wait(wait)
- 指定した秒数だけ待ちます。どちらも同じ動作です。

## finish()
- スクリプトを終了します。

## checkIfAlive()
- Stop が押されていたら、ここで終了します。入力や wait を使わない長い処理の途中で呼びます。

## direct_serial(serialcommands, waittime)
- シリアルに文字列を直接送ります。serialcommands は送る文字列のリスト、waittime はそれぞれを送ったあとに待つ秒数のリストです。

## reload_com_port()
- シリアルのポートを開き直します。

# スクリプト: キーボード入力

マイコンをキーボードとしても認識させて、Switch のキーボード画面に文字やキーを打つコマンドです。PythonCommand で使えます。

## 必要なもの
- キーボード入力に対応したファームウェアを書き込んだマイコンが必要です。
- Arduino Leonardo: Poke-ControllerForLeonardo の v04 以降
- CH552-SERIAL: ファームウェアの v2.4 以上
- 注意: CH552-SERIAL の場合は、ファームウェアは v2.4 以上を使用してください。それより前の版では、Enter・BackSpace・矢印キーなどのキーが、別の文字として入力されます。
- Serial タブの Data の Format が Default または NX の場合に使えます。NX では、キーの操作を、コントローラーの状態と同じデータで送ります(スクリプトの書き方は同じです)。

## 入力できる文字
- 送れるのは、半角の英字・数字・記号・スペースだけです。全角の文字を渡すと、何も送らずに Output に表示します。
- かな・カナは、Switch のキーボードをローマ字入力にして、ローマ字を送ります(例: "neko" → ねこ)。
- キーボードから入力したときの言語は、Switch の本体設定の言語で決まります。

## KeyBoard_Init()
- キーボード入力を始める前に、1回呼びます。コントローラーを無入力にし、押したままのキーを離します。

## TypeString(text) / TypeStringln(text)
- text を1文字ずつ打ちます。TypeStringln は、最後に Enter を押します。
- 送れた場合は True、半角以外の文字が含まれていて送らなかった場合は False を返します。

## TypeKey(key, show_value=False)
- キーを1回押して離します。key は、下の KEY で指定します。
- show_value を True にすると、押したキーを Output に表示します。

## PressKey(key, show_value=False) / ReleaseKey(key, show_value=False)
- PressKey はキーを押したままにし、ReleaseKey で離します。離さないままコマンドが終わった場合は、終了時に離します。

## キーの書き方(Commands.SwitchKeyboard の KEY)
- KEY.ENTER / KEY.BACKSPACE / KEY.DELETE / KEY.SPACE
- KEY.RIGHT_ARROW / KEY.LEFT_ARROW / KEY.DOWN_ARROW / KEY.UP_ARROW
- KEY.JP_HANZEN(半角/全角)/ KEY.JP_HIRAGANA(ひらがな/カタカナ)/ KEY.JP_HENKAN(変換)/ KEY.JP_BACKSLASH

## 日本語のキーボード画面での動き
- ローマ字を打った後、KEY.SPACE(または KEY.JP_HENKAN)を押すたびに、候補を先頭から順に選びます。KEY.ENTER で確定します。
- KEY.RIGHT_ARROW / KEY.LEFT_ARROW は、候補が表示されている間は候補の選択を、表示されていないときは文字のカーソルを動かします。
- KEY.JP_HANZEN で、かなと半角英数を切り替えます。KEY.JP_HIRAGANA で、ひらがなとカタカナを切り替えます。
- 確定した後は、予測の候補が表示されます。KEY.DELETE を1回押すと、予測の候補を消せます。

## 例
```
from Commands.PythonCommandBase import PythonCommand
from Commands.SwitchKeyboard import KEY


class TypeNeko(PythonCommand):
    NAME = "ねこと入力"

    def __init__(self):
        super().__init__()

    def do(self):
        # Switch のキーボード画面(日本語 ローマ字入力・かな)を開いた状態で実行する
        self.KeyBoard_Init()
        self.TypeString("neko")
        self.TypeKey(KEY.ENTER)  # ねこ のまま確定
        self.TypeString("neko")
        self.TypeKey(KEY.SPACE)  # 変換
        self.TypeKey(KEY.ENTER)  # 選んだ候補で確定
```
- サンプル: Commands/PythonCommands/Samples/Keyboard_sample.py

# スクリプト: 画像認識

ImageProcPythonCommand で使えるコマンドです。テンプレート画像は SerialController/Template フォルダに置き、そこからの相対パスで指定します。

## isContainTemplate(template_path, threshold=0.7, use_gray=True, ...)
- 今のカメラ画像の中に、テンプレート画像があるかを調べ、True / False を返します。
- threshold: 一致の度合いのしきい値(0~1)。大きいほど厳しくなります。
- use_gray: True なら白黒にして比べます(速い)。色の違いを区別したいときは False にします。
- show_value: True にすると、一致の度合いを Output に表示します。
- show_position / ms: 見つかった場所の枠を、プレビューに ms ミリ秒表示します。
- crop_fmt / crop: カメラ画像のうち、調べる範囲を指定します(下の「範囲の指定」を参照)。
- mask_path: 比べない部分を指定するマスク画像。
- BGR_range / threshold_binary: 色の範囲での抽出や、2値化をしてから比べます。
```
if self.isContainTemplate("Samples/logo.png", threshold=0.8, show_value=True):
    self.press(Button.A)
```

## isContainTemplate_max(template_path_list, threshold=0.7, ...)
- 複数のテンプレート画像を調べ、(一致の度合いが最も高い画像の番号, それぞれの一致の度合いのリスト, それぞれの判定結果のリスト) を返します。

## isContainTemplateGPU(template_path, ...)
- isContainTemplate と同じ判定を、GPU を使って行います(対応した OpenCV が必要です)。

## isContainedImage(image_path, threshold=0.7, ...)
- isContainTemplate の逆で、今のカメラ画像(または crop で切り出した部分)が、指定した画像の中にあるかを調べます。

## getCameraImage(crop_fmt="", crop=[])
- 今のカメラ画像(OpenCV の画像、BGR)を返します。自分で画像処理をするときに使います。

## getInterframeDiff(frame1, frame2, frame3, threshold)
- 連続する3枚の画像から、動いた部分が白くなる2値の画像を返します。動きの検出に使います。

## openImage(filename, mode="t")
- 画像ファイルを読み込みます。mode="t" なら Template フォルダ、"c" なら Captures フォルダからの相対パスです。

## saveCapture(filename=None, crop_fmt="", crop=[], mode=True)
- 今のカメラ画像を Captures フォルダに保存します。filename を省略すると、日時が名前になります(拡張子 .png は自動で付きます)。

## popupImage(crop_fmt="", crop=[], title="image")
- 今のカメラ画像を、別のウィンドウに表示します。

## displayRectangle(max_loc, width, height, tag=None, ms=2000, color=["blue", "orange"], ...)
- プレビューに、四角形を ms ミリ秒表示します。max_loc は左上の座標(カメラ画像の座標)です。

## displayText(position, txt, tag=None, ms=2000, font=..., fontsize=20, color="black")
- プレビューに、文字を ms ミリ秒表示します。

## setTemplateDir(path) / get_filespec(filename, mode="t")
- setTemplateDir は、テンプレート画像を探すフォルダを変えます。
- get_filespec は、Template("t")または Captures("c")フォルダからの相対パスを、実際のパスにして返します。

## 範囲の指定(crop_fmt と crop)
- crop は4つの数値のリストで、並び方を crop_fmt で指定します。座標は画像の左上が原点です。
- crop_fmt=1: [x始点, y始点, x終点, y終点]
- crop_fmt=2: [x始点, y始点, 幅, 高さ]
- crop_fmt=3: [x始点, x終点, y始点, y終点]
- crop_fmt=4: [x始点, 幅, y始点, 高さ]
- crop_fmt=11~14: 上の1~4の、x と y を入れ替えた並び(OpenCV の順)
```
self.isContainTemplate("Samples/logo.png", crop_fmt=2, crop=[100, 50, 300, 200])
```

# スクリプト: 出力とダイアログ

## 出力
- print(...): Others タブの Stdout で選んだ Output に表示します。
- print_t1(...) / print_t2(...): Output#1 / Output#2 に表示します。
- print_ts(...): Stdout に選んでいる方の Output に表示します。print_t(...) は、選んでいない方に表示します。
- print_s(...): print と同じです。
- print_t1b(mode, ...) / print_t2b(mode, ...) / print_tb(mode, ...) / print_tbs(mode, ...): mode で書き込み方を選べます。"w" は今の内容を消して書く、"a" は追記、"d" は内容を消すだけです。
```
self.print_t1b("w", f"{count} 回目")
```

## ダイアログ(実行中に値を入力する)
- dialogue(title, message, desc=None, need=list): 入力欄だけのダイアログです。message は入力欄の名前のリストです。
- dialogue6widget(title, dialogue_list, desc=None, need=list): いろいろな部品を使えるダイアログです。
- dialogue6widget_save_settings(title, dialogue_list, filename, ...): 前回の入力内容をファイルに保存し、次回の初期値にします。
- dialogue6widget_select_settings(title, dialogue_list, dirname, ...): 保存した設定を選んで呼び出せます。
- need=list なら入力値のリスト、need=dict なら {名前: 入力値} の辞書を返します。キャンセルした場合は、スクリプトを終了します。
- dialogue6widget の部品の名前は、重ならないようにしてください(重なっていると、スクリプトを終了します)。

## dialogue6widget の部品の書き方
- ["Entry", 名前, 初期値]: 入力欄
- ["Check", 名前, 初期値(True / False)]: チェックボックス
- ["Combo", 名前, 選択肢のリスト, 初期値]: コンボボックス
- ["Radio", 名前, 選択肢のリスト, 初期値]: ラジオボタン
- ["Spin", 名前, 選択肢のリスト, 初期値]: スピンボックス
- ["Scale", 名前, 最小, 最大, 初期値, 小数の桁数]: スライダー
- ["Next"]: 次の列に進む
```
ret = self.dialogue6widget(
    "設定",
    [["Entry", "回数", "10"], ["Check", "通知する", True], ["Combo", "モード", ["A", "B"], "A"]],
    need=dict,
)
count = int(ret["回数"])
```

## show_var()
- self に持たせた変数の一覧を表示します。一時停止中の確認に使えます。

# スクリプト: 通知と通信

## 通知
- LINE_text(txt, token="token"): LINE に文字を送ります。
- discord_text(content="", index=0, keys="DISCORD_WEBHOOK", name=None): Discord に文字を送ります。送信できれば True を返します。
- LINE_image(txt, crop_fmt="", crop=[], token="token"): LINE に、文字と今のカメラ画像を送ります。(ImageProcPythonCommand)
- discord_image(content="", index=0, crop_fmt="", crop=[], keys="DISCORD_WEBHOOK", name=None): Discord に、文字と今のカメラ画像を送ります。(ImageProcPythonCommand)
- Discord の通知先は、name(または keys)に 設定 > Discord の通知先... で付けた名前を指定して選びます。index(0 始まりの番号。0 は DISCORD_WEBHOOK、1 以降は登録順)でも選べます。両方を指定した場合は名前が優先で、その名前の通知先が無ければ index の通知先に送ります。
- 送り先の Webhook やトークンは、設定 > Discord の通知先... / LINE の通知先... で設定します。

## Socket 通信
- socket_change_ipaddr(addr) / socket_change_port(port): 接続先を変えます。
- socket_connect() / socket_disconnect(): 接続・切断します。
- socket_transmit_message(message): 文字列を送ります。
- socket_receive_message(header, show_msg=False): 先頭が header の文字列を受け取るまで待ち、受け取った文字列を返します。
- socket_receive_message2(headerlist, show_msg=False): 先頭がリストのどれかに一致する文字列を受け取ります。
- socket_change_alive(flag): 受信待ちを続けるかどうかを切り替えます。

## MQTT 通信
- mqtt_change_broker_address(broker_address) / mqtt_change_id(id) / mqtt_change_pub_token(pub_token) / mqtt_change_sub_token(sub_token) / mqtt_change_clientId(clientId): 接続の設定を変えます。
- mqtt_transmit_message(roomid, message): roomid(トピック)に文字列を送ります。
- mqtt_receive_message(roomid, header, show_msg=False): 先頭が header の文字列を受け取るまで待ち、受け取った文字列を返します。
- mqtt_receive_message2(roomid, headerlist, show_msg=False): 先頭がリストのどれかに一致する文字列を受け取ります。
- 接続先の初期値は、プロファイルのフォルダの external_token.ini に書きます。

# Mcu コマンド

- Mcu Command は、マイコン側に書き込まれた動作を呼び出すコマンドです。PC側は開始と終了の合図だけを送ります。
- SerialController/Commands/McuCommands に置きます。McuCommand を継承し、NAME と、マイコン側の動作の名前を指定します。
```
from Commands.McuCommandBase import McuCommand


class Mash_A(McuCommand):
    NAME = "A連打"

    def __init__(self, sync_name="mash_a"):
        super().__init__(sync_name)
```
- マイコン側に、その名前の動作が書き込まれている必要があります。
- Mcu コマンドは、一時停止(Pause)できません。
