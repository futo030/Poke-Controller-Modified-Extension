python -m pip install --upgrade pip

python -c "import subprocess, sys; subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-r', 'requirements.txt'])"

python SerialController/PokeConUpdateChecker.py
cd SerialController
rem python Window.py --profile dragonite
python Window.py
pause