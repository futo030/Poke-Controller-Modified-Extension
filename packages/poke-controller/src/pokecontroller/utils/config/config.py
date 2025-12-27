import configparser
import os
from pathlib import Path

from pokecontroller.core.exception import PokeControllerException


class Config:
    """INI形式の設定ファイルを管理するクラス.

    ConfigParserをラップし、設定ファイルの読み書きと値の取得・設定を提供します。
    """

    def __init__(self, path: Path) -> None:
        """Configインスタンスを初期化します.

        Args:
            path: 設定ファイルのパス.
        """
        self._path = path
        self._config: configparser.ConfigParser = configparser.ConfigParser(
            allow_no_value=True,
            comment_prefixes=("#", ";"),
        )
        self._config.optionxform = str  # type: ignore[assignment]

    def __getitem__(self, section: str) -> configparser.SectionProxy:
        """指定されたセクションのプロキシを取得します.

        Args:
            section: セクション名.

        Returns:
            セクションのプロキシオブジェクト.
        """
        return self._config[section]

    def __setitem__(self, section: str, value: dict[str, str]) -> None:
        """指定されたセクションに値を設定します.

        Args:
            section: セクション名.
            value: 設定する値の辞書.
        """
        self._config[section] = value

    def load(self, encoding: str | None = "utf-8-sig") -> None:
        """設定ファイルを読み込みます.

        Args:
            encoding: ファイルのエンコーディング. デフォルトは "utf-8-sig".

        Raises:
            FileNotFoundError: ファイルが存在しない場合.
        """
        if not self._path.exists():
            raise FileNotFoundError(str(self._path))
        self._config.read(str(self._path), encoding=encoding)

    def save(
        self,
        *,
        encoding: str | None = "utf-8",
        chmod: int | None = None,
        create_directory: bool = True,
    ) -> None:
        """設定ファイルを保存します.

        Args:
            encoding: ファイルのエンコーディング. デフォルトは "utf-8".
            chmod: 保存後に設定するパーミッション. Noneの場合は変更しません.
            create_directory: ディレクトリが存在しない場合に作成するかどうか.
                デフォルトはTrue.
        """
        if not self._exists_directory() and create_directory:
            self._create_directories()

        with open(str(self._path), mode="w", encoding=encoding) as file:
            self._config.write(file)

        if chmod is not None:
            os.chmod(path=self._path, mode=chmod)

    def get(self, section: str, option: str, default: str | None = None) -> str | None:
        """指定されたセクションとオプションの値を取得します.

        Args:
            section: セクション名.
            option: オプション名.
            default: 値がNoneの場合に返すデフォルト値.

        Returns:
            取得した値、またはデフォルト値.
        """
        value = self._config[section][option]
        return value if value is not None else default

    def has_option(self, section: str, option: str) -> bool:
        """指定されたセクションにオプションが存在するかどうかを確認します.

        Args:
            section: セクション名.
            option: オプション名.

        Returns:
            オプションが存在する場合はTrue、それ以外はFalse.
        """
        return self._config.has_option(section, option)

    def get_boolean(
        self,
        section: str,
        option: str,
        default: bool | None = None,
    ) -> bool | None:
        """指定されたセクションとオプションの真偽値を取得します.

        Args:
            section: セクション名.
            option: オプション名.
            default: 値がNoneの場合に返すデフォルト値.

        Returns:
            取得した真偽値、またはデフォルト値.
        """
        value = self._config.getboolean(section, option)
        return value if value is not None else default

    def get_int(
        self,
        section: str,
        option: str,
        default: int | None = None,
    ) -> int | None:
        """指定されたセクションとオプションの整数値を取得します.

        Args:
            section: セクション名.
            option: オプション名.
            default: 値がNoneの場合に返すデフォルト値.

        Returns:
            取得した整数値、またはデフォルト値.
        """
        value = self._config.getint(section, option)
        return value if value is not None else default

    def get_float(
        self,
        section: str,
        option: str,
        default: float | None = None,
    ) -> float | None:
        """指定されたセクションとオプションの浮動小数点数値を取得します.

        Args:
            section: セクション名.
            option: オプション名.
            default: 値がNoneの場合に返すデフォルト値.

        Returns:
            取得した浮動小数点数値、またはデフォルト値.
        """
        value = self._config.getfloat(section, option)
        return value if value is not None else default

    def set(self, section: str, option: str, value: str) -> None:
        """指定されたセクションとオプションに値を設定します.

        セクションが存在しない場合は自動的に作成されます。

        Args:
            section: セクション名.
            option: オプション名.
            value: 設定する値.
        """
        if not self._config.has_section(section):
            self._config.add_section(section)
        self._config[section][option] = value

    def sections(self) -> list[str]:
        """全てのセクション名のリストを取得します.

        Returns:
            セクション名のリスト.
        """
        return self._config.sections()

    def add_section(self, section: str) -> None:
        """新しいセクションを追加します.

        Args:
            section: 追加するセクション名.
        """
        self._config.add_section(section)

    def options(self, section: str) -> dict[str, str]:
        """指定されたセクションの全てのオプションを辞書として取得します.

        Args:
            section: セクション名.

        Returns:
            オプション名と値の辞書.
        """
        return dict(self._config[section])

    def keys(self, section: str) -> list[str]:
        """指定されたセクションの全てのオプション名を取得します.

        Args:
            section: セクション名.

        Returns:
            オプション名のリスト.
        """
        return list(self._config[section].keys())

    def _check_exists_directory(self, should_create: bool) -> None:
        directory = self._path.parent
        exists_dir = self._exists_directory()
        if not exists_dir and not should_create:
            raise PokeControllerException(directory)
        self._create_directories()

    def _exists_directory(self) -> bool:
        directory = self._path.parent
        return directory.exists() and directory.is_dir()

    def _create_directories(self) -> None:
        directory = self._path.parent
        directory.mkdir(parents=True, exist_ok=True)
