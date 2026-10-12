fileencoding=utf-8

Poke-Controller Modified/Extension 橋渡し関数 ver.0.0.3 作成者：フウ(@dragonite303)

■要約
　本プログラムはPoke-Controller Modified ExtensionとPoke-Controller Modifiedの互換性を保持するための関数です。

■開発環境
　python v3.12.2

■事前準備
* SerialController\Commands\PythonCommandsのフォルダにフォルダごとおいてください。
　SerialController\Commands\PythonCommands\bridge_functions\bridge_functions.pyとなる想定です。

■使用方法
* 以下の通り、本ライブラリをimportします。
  from Commands.PythonCommands.bridge_functions.bridge_functions import BridgeFunctions
* do関数内で以下のコードを記載します。
  self.bf = BridgeFunctions(self)
  このとき、selfはImageProcPythonCommandを継承している必要があります。
* self.bf.[BridgeFunctionsに記載されている関数](引数) にて使用が可能です。

■できること一覧
* check_pokecon_extension: [Extension版] Trueを返します。[Modified版] Falseを返します。
* get_profile_name: [Extension版] プロファイル名を文字列で返します。[Modified版] ""を返します。
* set_template_directory: [Extension版] テンプレートファイルの場所を変更する関数が呼び出されます。[Modified版] passされます。
* get_template_directory: [Extension版] テンプレートファイルの場所を文字列で返します。[Modified版] "./Template/"を返します。
* bf_print: [Extension版] 標準出力に割り当てられているエリアに文字列を出力する関数が呼び出されます。[Modified版] 通常のprint関数が呼び出されます。
* bf_print_w: [Extension版] 標準出力に割り当てられていないエリアに文字列を出力する関数が呼び出されます。上書きです。[Modified版] 通常のprint関数が呼び出されます。
* bf_print_a: [Extension版] 標準出力に割り当てられていないエリアに文字列を出力する関数が呼び出されます。追記です。[Modified版] 通常のprint関数が呼び出されます。
* bf_isContainTemplate: [Extension版] Extension版に追加された引数が使用できます。[Modified版] 通常のテンプレートマッチング関数が呼び出されます。crop_fmtとcropは、Modified版のcropの並びに変換して渡します。
* bf_isContainTemplate_max: [Extension版] Extension版に追加された引数が使用できます。[Modified版] 通常のテンプレートマッチング関数(複数の画像)が呼び出されます。crop_fmtとcropは、Modified版のcropの並びに変換して渡します。
* bf_dialogue: [Extension版] 説明(desc)付きのダイアログ関数(Entryのみ)が呼び出されます。[Modified版] 通常のダイアログ関数が呼び出されます(descは表示されません)。
* bf_dialogue6widget: [Extension版] 説明(desc)付きのダイアログ関数が呼び出されます。[Modified版] ["Next"]を取り除いて、通常のダイアログ関数が呼び出されます(descは表示されません)。
* bf_dialogue6widget_save_settings: [Extension版] Extension版に追加された設定保存機能付きダイアログ関数が呼び出されます。[Modified版] 通常のダイアログ関数が呼び出されます。
* bf_dialogue6widget_select_settings: [Extension版] Extension版に追加された設定選択機能付きダイアログ関数が呼び出されます。[Modified版] 通常のダイアログ関数が呼び出されます。
* bf_show_informations: [Extension版] [Modified版] プログラムの詳細情報を表示する関数です。(本関数はおまけであり、互換性の保持を目的としていません。)

■Extension版とModified版で動きが変わる点
* ダイアログをキャンセルした場合は、どちらの版でもスクリプトを終了します。(ver.0.0.3より。Modified版では、ダイアログ関数がFalseまたはNoneを返した場合に終了します。)
* bf_isContainTemplate / bf_isContainTemplate_max のcrop_fmtは、Modified版でも使用できます。(ver.0.0.3より。crop_fmtを指定しない場合は、[x軸始点, y軸始点, x軸終点, y軸終点]として扱います。)
* 次の引数は、Modified版では無視されます。これらの引数を使うと、Extension版とModified版で判定の結果が変わる場合があります。
  use_gpu / BGR_range / threshold_binary / crop_template / show_image / color / mask_path_list
* set_template_directoryは、Modified版ではテンプレートファイルの場所を変更しません。Modified版では、Templateフォルダにあるファイルが使われます。
* bf_print_wは、Modified版では上書きされず、通常のprint関数と同じように追記されます。
* 設定保存機能・設定選択機能付きダイアログは、Modified版では保存・選択ができません(毎回、初期値が表示されます)。

■橋渡し関数にない関数を使う場合
* press / pressRep / hold / holdEnd / wait / finish などの基本の関数は、どちらの版でもそのまま使用できます。
* discord_text / discord_image の通知先は、name="通知先の名前" で指定すると、どちらの版でも使用できます。(Extension版はver.0.2.0以降。)
* Extension版にしかない関数(getCameraImage / saveCapture / holdChange / キーボード入力の関数など)を使う場合は、check_pokecon_extensionで処理を分けてください。
* getInterframeDiffは、Extension版ではver.0.2.0以降で使用できます。

■対象のバージョン
* Poke-Controller Modified Extension ver.0.2.0
* Poke-Controller Modified ver.3.1.3 / ver.4.0.2(開発中のrelease/v4.0ブランチ)
  ※Modified版は、関数の定義に合わせて作成しています。ver.4.0のスクリプトのzip配布機能では、本ライブラリを使うスクリプトは導入できません。

■利用上の注意
* 勝手に改変して使用いただいて構いません。
* License.txtに記載の通り改変しての配布は禁止とさせていただきます。
* 想定外の動作をした場合でも責任はとれません。自己責任で利用ください。
* 商用利用/自作発言はお控えください。

■その他
* 質問などありましたら作成者までお問い合わせください。なお、返信には数日ほどかかる場合もありますのでご承知おきください。常識やマナーを守って問い合わせいただければ幸いです。
* 改変のない再配布は自由に可能です。
* 本プログラムの挙動に関して、他の方に問い合わせをするのはご迷惑をおかけする可能性があるため基本的におやめください。
* 修正および機能追加を希望される場合は作成者までご連絡ください。

■ライセンス
　License.txtを確認して下さい。

■更新履歴
* ver.0.0.1 初版
* ver.0.0.2 get_template_directory関数を追加、bf_show_informationsのバグを修正、利用上の注意とその他に加筆
* ver.0.0.3 Modified版でダイアログをキャンセルした場合にスクリプトを終了するよう変更、Modified版でcrop_fmtを使用できるよう変更、bf_show_informationsでプログラム名が空になる場合があるバグを修正、できること一覧と注意点を加筆
