# Architecture

`apps/poke-controller-modified-extension` ディレクトリのアプリケーションアーキテクチャについて説明します。

## 機能

Poke-Controller Modified Extensionは、主に以下の機能を提供しています。

- ゲーム画面の取得
  - キャプチャデバイスからゲーム画面を取得
- ゲーム画面に対する画像処理
  - 範囲切り出し
  - テンプレートマッチング
  - グレースケール変換
  - 2値化
- ゲームの操作
  - ハードウェア(ProControllerやキーボードなど)の入力をゲーム機に送信
  - アプリケーションが提供するソフトウェアコントローラーからの入力を取得しゲーム機に送信
- ゲームの操作の自動化
  - ユーザー独自の自動化スクリプトを定義可能(Commandパターンによる拡張)
    - 自動化スクリプトからゲーム操作のAPIを呼び出すことで、ゲームの操作を自動化
    - 自動化スクリプトから画像処理のAPIを呼び出すことで、表示されている画面に応じた処理を実行

## アーキテクチャ概要

### Poke-Controller PAPICO

Poke-Controllerの公開APIを複数バージョンに渡って互換性を保った状態で提供するための仕組みです。  
PAPICOはPublic API Compatible Orchestratorの略で、公開APIのバージョンによって適切な実装を選択して実行するのが役割です。  
この仕組みにより、例えば過去バージョンのコマンドを実行できるようにしつつ、まったく新規のコマンドAPIを提供することもできます。  
APIバージョンごとの実装は `PapicoHandler` 抽象基底クラスのサブクラスとして定義され、コマンドの実行や設定ファイルの読み込みなど
APIのバージョンによって異なる処理を登録することができます。

### `singletons` モジュール

アプリケーション全体から参照されるリソースや状態をシングルトンとして保持するためのモジュールです。  
ランタイム全体で利用可能なシングルトンを定義している `singletons.runtime` モジュールと、 
`App` クラス初期化時に同時に初期化されるシングルトンを定義している `singletons.app` モジュールに
大別されます。

### `runner.py`

アプリケーションをエントリーポイントを定義します。
アプリケーションの実行に必要なリソースや状態をシングルトンとして初期化する、PAPICOのハンドラーの登録を行うなどの処理を実行します。  
`runner.py` で初期化されたリソースは、適切にクローズされるように設計されています。

### `app` モジュール

TkinterのTkクラスの拡張およびアプリケーションで利用する状態のクラスを定義しています。  
`App` クラスの初期化では、 `singletons.app` モジュールのシングルトンクラスを同時に初期化しています。  

### `widget` および `windows` モジュール

`widget` モジュールはTkinterのウィジェットの拡張クラスを定義しています。  
`windows` モジュールはアプリケーションで表示するウィンドウを定義しています。

### `api` モジュール

ユーザーが利用できるAPIを定義するモジュールです。  
`api.v0_1_8` モジュールは、もともとルートディレクトリの `SerialController` で定義されていた
APIの移植と型付けして、APIを壊さない範囲で一部リファクタリングしています。

## Tkinterウィジェットの実装方針

### ウィジェットやウィンドウの実装

アプリケーションで表示されるウィンドウやウィジェットはある程度の粒度でクラスとして定義されています。  
一般的な決まりがあるわけではなさそうですが、特に理由がなければ `__init__` メソッドで `tkinter.Variable` などの状態の初期化を、
`build_ui` メソッドでウィジェットの生成やレイアウトなどを行っています。  
また、ユーザーのインタラクションやコマンドの動作などによって、アプリケーションの内部状態が変化するので、
それに伴うUIの状態や遷移的な状態の変化に追随するために `tkinter.Variable` のtrace機能を利用しています。  
独自拡張されている `Frame` や `Labelframe` などのコンテナクラスには、 `destroy` 呼び出し時に適切にtraceを解除するような仕組みを
取り入れています。  
これらによって、GUI定義のファイルを過度に肥大化させず、不要になったtraceの処理は適切に開放できるようにしています。  


### おまけ: `tkinter.Variable` のtrace機能について

Tkinterは `Variable` を利用することで特定の値とUIの状態の変更を統合できますが、traceの機能を利用することで
Reactのhookのような遷移的な状態変更を行うこともできます。  

例えば、コマンド実行中に実行ボタンを押せなくするには以下のように書けます。

```python
# variables
is_running = tk.BooleanVar(value=False)

# is_runningの状態に応じてstart_buttonの状態を変更する
def on_is_running_changed(*_):
    if is_running.get():
        start_button.config(state=tk.DISABLED)
    else:
        start_button.config(state=tk.NORMAL)

# traceを登録する
# 第1引数 "write" の指定は、変数の値がセットされた場合に第2引数で渡した関数が実行される
is_running.trace_add("write", on_is_running_changed)


def start_command():
    is_running.set(True) # ここでon_is_running_changedが呼び出される
    ...

def stop_command():
    is_running.set(False) # ここでon_is_running_changedが呼び出される
    ...
```