# Directory Structure

このプロジェクトでは、[uv](https://docs.astral.sh/uv/)を用いて依存関係の管理やスクリプトの実行を行っています。  
uvを用いることで、実行環境におけるPythonのバージョンや依存関係の統一をすることができます。
`uv run` は自動的にvenvをアクティベートするため、依存関係の統一が容易に行えます。  
また、[Ruff](https://docs.astral.sh/ruff/)および[mypy](https://mypy.readthedocs.io/en/stable/)
を使用してコードの可読性や安全性を可能な限り保証するようにしています。

```
.
├── .python-version
├── pyproject.toml
├── uv.lock
├── SerialController
├── packages
├── apps
├── scripts
├── mypy.ini
├── ruff.toml
└── taskfile.yml
```

## [`.python-version`](https://docs.astral.sh/uv/guides/projects/#python-version)

Pythonのバージョンを指定するファイルです。  
このファイルは、`uv run` でvenvをアクティベートする際に参照されます。

## [`pyporject.toml`](https://packaging.python.org/ja/latest/guides/writing-pyproject-toml/)

Pythonプロジェクトにおける設定ファイルです。  
このプロジェクトでは、`[project]` テーブル以外だと[uv workspace](https://docs.astral.sh/uv/concepts/projects/workspaces/)の設定をしています。

## [`uv.lock`](https://docs.astral.sh/uv/guides/projects/#uvlock)

uvでインストールした依存関係のバージョン情報などが保持されているファイルです。  

## `SerialController`

Poke-Controller Modified Extensionのエントリーポイントや、その他実行に必要な実装が含まれているディレクトリです。  
後述の `packages` や `apps` から必要なモジュールを利用しています。

## `packages`

アプリケーションで利用するモジュールが含まれているディレクトリです。  
GUI(Tkinterなど)に依存しない、汎用的なモジュールが定義されています。

## `apps`

アプリケーションの実装が含まれているディレクトリです。  
GUI(Tkinterなど)に依存するモジュールが定義されています。

## `scripts`

アプリケーションの実行に直接関係しないスクリプトが含まれるディレクトリです。

## [`mypy.ini`](https://mypy.readthedocs.io/en/stable/config_file.html)

mypyの設定ファイルです。

## [`ruff.toml`](https://docs.astral.sh/ruff/configuration/)

Ruffの設定ファイルです。

## [`taskfile.yml`](https://taskfile.dev/docs/guide#running-taskfiles)

[Taskfile](https://taskfile.dev/)の設定ファイルです。  
このプロジェクトでは、ローカル開発環境でのTaskfileの導入は任意ですが、
Taskfileを用いてアプリケーションの実行や開発に必要なタスク群を定義しています。  
Taskfileを導入しない場合は `taskfile.yml` の内容を参考にして直接コマンドを実行してください。  

# `packages` ディレクトリについての詳細

`packages` ディレクトリは、アプリケーションで利用するモジュールが含まれています。  
このディレクトリ内のモジュールは、GUI(Tkinterなど)に依存しない汎用的な機能を提供しています。  
各モジュールは、アプリケーションの主要な機能を実装するための基礎となる機能を提供します。

## `packages/poke-controller`

uv workspaceによって定義されたパッケージです。  
このパッケージは、Poke-Controller Modified Extensionの主要な機能を提供しています。

- `core`: アプリケーションのコアとなる機能が含まれています
  - `camera`: カメラデバイスからの映像を取得するための機能
  - `controller`: Nintendo Switchや3DSのコントローラーの機能をエミュレートする機能
  - `dynamic`: 動的クラスローダー
  - `exception`: パッケージで利用される例外クラス
  - `image`: 画像処理の機能
  - `notification`: ユーザーに通知を表示するための機能
  - `serial`: シリアル通信に必要な機能
- `utils`: あると便利な実装が含まれています
  - `collection`: コレクション操作に必要な機能
  - `config`: 設定ファイルの読み込みや保存に必要な機能
  - `datetime`: 日時操作に必要な機能
  - `logging`: ログ出力に必要な機能
  - `math`: 数学的な計算に必要な機能
  - `platform`: 実行されているOS環境を識別するための機能
  - `translation`: 多言語対応に必要な機能
- `gui`: cv2で画像を表示するウィンドウを提供する機能

# `apps` ディレクトリについての詳細

## `apps/poke-controller-modified-extension`

uv workspaceによって定義されたパッケージです。  
このパッケージは、Poke-Controller Modified Extensionのアプリケーションが実装されています。

- `app`: アプリケーションの自体の実装や、アプリケーションの実行に必要な型などが定義されています
- `command`: アプリケーションとコマンドが連携するための型が実装されています
- `singletons`: アプリケーションの状態を管理するシングルトンオブジェクトが実装されています
  - `runtime`: アプリケーションのランタイム全体に渡って有効なシングルトンオブジェクトが提供されるモジュールです
  - `app`: アプリケーション初期化中に有効となるシングルトンオブジェクトが提供されるモジュールです
  - `widget`: アプリケーションの初期化後に有効となるシングルトンオブジェクトが提供されるモジュールです
- `widgets`: アプリケーションで使用するtkinterのウィジェットが実装されています
- `windows`: アプリケーションで使用するtkinterのウィンドウが実装されています
- `api`: 外部に公開するためのAPIが含まれています
  - `v0_1_8`: バージョン0.1.8のAPI実装
    - v0.1.8以下のコマンドの後方互換性を保つための実装が提供されます
      - このモジュールのAPIを変更すると、従来のコマンドが動かなくなる可能性があります
    - リポジトリルートの `SerialController` ディレクトリにあった実装が配置されています
      - 現在の `SerialController` ディレクトリの実装のほとんどは、このモジュールの実装の再エクスポートによって提供されています
- `papico`: ユーザーに公開するAPIを、複数バージョンに渡って適切に処理するための機能を実現しているモジュールです
  - Public API Compatible Orchestratorの略称です
  - ユーザー設定やコマンドの取得、保存、実行などを担っています
