import importlib.util
import os
from pathlib import Path

def import_all_modules_from_directory(directory: str):
    """
    指定したディレクトリ以下にあるすべてのPythonモジュールを動的にインポートします。
    """
    modules = {}
    directory_path = Path(directory)
    
    # ディレクトリ内のすべての.pyファイルを探索
    for root, _, files in os.walk(directory_path):
        for file in files:
            if file.endswith(".py") and not file.startswith("__init__"):  # __init__.pyを無視
                file_path = Path(root) / file
                module_name = file_path.stem  # ファイル名からモジュール名を取得
                
                # モジュールを動的にインポート
                spec = importlib.util.spec_from_file_location(module_name, file_path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                
                # インポートしたモジュールを辞書に格納
                modules[module_name] = module
    
    return modules

def test():
    # 使用例
    serialcontroller_path = "/path/to/serialcontroller"
    imported_modules = import_all_modules_from_directory(serialcontroller_path)

    # インポートされたモジュールを確認
    for module_name, module in imported_modules.items():
        print(f"Imported module: {module_name}")
        # 例: モジュール内の関数を呼び出す
        # module.some_function()
