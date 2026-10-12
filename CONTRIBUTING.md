# 開発に参加するには

不具合の報告、要望、修正の提案を歓迎します。

## 不具合の報告・要望

[Issues](https://github.com/futo030/Poke-Controller-Modified-Extension/issues) から、ひな形(不具合の報告 / 要望・提案)を選んで書いてください。

- 不具合の報告には、ヘルプ > 環境の診断 の内容(「マスクしてコピー」で、フォルダーの場所を隠してコピーできます)と、再現の手順を書いてください。
- **Discord の Webhook の URL や、トークンは貼らないでください。**
- 個別のスクリプトについての質問は、そのスクリプトの作者へお願いします(ヘルプ から、質問用の文章を作れます)。

## Pull Request

1. このリポジトリを Fork し、ブランチを作って変更します。
2. 下の「検査とテスト」が通ることを確認します。
3. 利用者に見える変更は、`changelog.txt` の一番上のバージョンに1行追記します。
4. Pull Request を作り、変更の内容と、確認したことを書きます。

大きな変更(画面の構成を変える、関数の動作を変えるなど)は、先に Issue で相談してください。

## 守ってほしいこと

- **Poke-Controller Modified との互換性を保つ**: Modified 版のスクリプトが、そのまま動くことを必須としています。スクリプトから使う関数の名前・引数・戻り値・動作は変えないでください(引数を足す場合は、省略できる形にします)。
- **層の決まりを守る**: 画面に依存しない処理(`services/` など)から、tkinter や画面のファイルを読み込まないでください。詳しくは [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) を参照してください。
- **秘密の値をコミットしない**: Webhook の URL、トークン、個人の設定(`profiles/` の中)は、コミットに含めないでください。

## 検査とテスト

準備(1回だけ)。[uv](https://docs.astral.sh/uv/) を使う場合:

```
uv sync
```

以下のコマンドは、`.venv` の Python(`.venv\Scripts\python.exe`)で実行するか、先頭に `uv run` を付けます(検査は、`uvx ruff check` でも実行できます)。

pip を使う場合(ver.0.2.x まで):

```
pip install -r requirements.txt
pip install -r requirements-web.txt
pip install ruff
```

検査(設定は `ruff.toml`)。リポジトリのフォルダで実行します。

```
python -m ruff check
```

テスト。SerialController フォルダで実行します(カメラ・シリアル・コントローラーをつながずに実行できます)。

```
python -m unittest discover -s tests
```

push と Pull Request のたびに、GitHub 上でも同じものが自動で実行されます。

## コードの書き方

- Python 3.12 以上で動くように書きます(uv の環境は Python 3.13 ですが、ver.0.2.x の間は、以前からの環境(Python 3.12)でも起動できるようにしています)。
- 1行は 120 文字までを目安にします。
- コメントと説明文(docstring)は、日本語で、何をしているか・なぜそうしているかを書きます。
- 新しいファイルを整形する場合は `python -m ruff format ファイル名` を使えます(既存のファイル全体を整形し直すことは、差分が大きくなるので避けてください)。
- 処理を足したときは、`SerialController/tests` にテストを足してください(実機がないと確認できない部分は除きます)。
- スクリプトから使う関数・クラス(`Commands/CommandBase.py`、`PythonCommandBase.py`、`McuCommandBase.py`、`Keys.py`)の名前と引数は、記録(`tests/data/public_api.json`)と比べて、変わっていないことをテストで確かめています。関数や、省略できる引数を足したときは、SerialController フォルダで `python tests/public_api.py --write` を実行して、記録を作り直してください(名前をなくす、引数を変えるなど、これまでのスクリプトが動かなくなる変更では、作り直されません)。

## ライブラリを足す・版を上げるとき

- 必要なライブラリは `pyproject.toml` に書き、`uv lock` で `uv.lock` を作り直します(両方をコミットします)。ver.0.2.x の間は、`requirements.txt`(Web ブラウザ版の分は `requirements-web.txt`)にも同じものを書きます(食い違うと、テストが失敗します)。
- ライブラリの版を新しくするときは、`uv lock --upgrade` を実行し、テストを通してからコミットします。
- Python の版を上げるときは、`.python-version` を書き換えて、`uv lock` を実行します。
- `bootstrap` フォルダー(環境の用意と起動)は、本体のコードを読み込まず、Python の標準の機能だけで書きます。

## 版を公開するとき(メンテナー向け)

利用者の更新の確認は、GitHub の最新の Release と、手元のバージョンを比べます。`git clone` で取得した利用者は、master の先頭に更新されます。

1. `SerialController/Constant.py` の `VERSION` と、`pyproject.toml` の `version` を上げます(機能紹介の見出しも、合わせて書き換えます)。
2. `changelog.txt` を書き、テストと検査を通します。
3. master に入れます。**master は、版を公開するときだけ進めます**(開発の途中のコミットは、別のブランチに積みます)。
4. タグを付けます。名前は `v` + バージョン(例: `v0.2.1`)にします。
5. GitHub で、そのタグの Release を作ります。`PokeConExtension_Install.bat` を、添付ファイルとして付けます。
   - 試作版は「Pre-release」にすると、利用者の更新の確認の対象になりません。
   - タグのない版からは、ZIP での更新ができません。版ごとに、必ずタグと Release を作ります。

## 文書を直すとき

- 画面の使い方: `SerialController/assets/manual/manual.md`(ウィンドウの画面)/ `manual_web.md`(Web ブラウザ版)
- スクリプトの書き方: `SerialController/assets/manual/scripting.md`
- コマンドを作る人向けの補足: `docs/command-guide.md`

`assets/manual` の文章は、アプリケーションの Instruction Manual にそのまま表示されます。「# 見出し」が1項目、「## 見出し」が小見出し、「- 」が箇条書きになります(表や太字などは使えません)。
