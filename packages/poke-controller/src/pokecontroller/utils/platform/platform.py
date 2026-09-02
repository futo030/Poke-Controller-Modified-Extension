import platform


def is_windows() -> bool:
    """現在のOSがWindowsかどうかを判定します.

    Returns:
        WindowsであればTrue、それ以外はFalse.
    """
    return platform.system() == "Windows"


def is_macos() -> bool:
    """現在のOSがmacOSかどうかを判定します.

    Returns:
        macOSであればTrue、それ以外はFalse.
    """
    return platform.system() == "Darwin"


def is_linux() -> bool:
    """現在のOSがLinuxかどうかを判定します.

    Returns:
        LinuxであればTrue、それ以外はFalse.
    """
    return platform.system() == "Linux"


def get_name() -> str:
    """現在のOSの名前を取得します.

    Returns:
        OS名の文字列 ("windows", "macos", "linux").

    Raises:
        RuntimeError: サポートされていないOSの場合.
    """
    if is_windows():
        return "windows"
    if is_macos():
        return "macos"
    if is_linux():
        return "linux"
    raise RuntimeError("Unsupported OS")


def get_names() -> tuple[str, ...]:
    """サポートされている全てのOS名のタプルを取得します.

    Returns:
        ("windows", "macos", "linux")のタプル.
    """
    return "windows", "macos", "linux"
