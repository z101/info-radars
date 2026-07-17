import sys
import subprocess
import os
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SKILL_DIR.parents[3]
VENV_DIR = PROJECT_DIR / '.venv'


def get_python_exe():
    if sys.platform == 'win32':
        return VENV_DIR / 'Scripts' / 'python.exe'
    return VENV_DIR / 'bin' / 'python'


def check_venv():
    if not VENV_DIR.exists():
        return False
    return get_python_exe().exists()


def create_venv():
    try:
        subprocess.run(
            [sys.executable, '-m', 'venv', str(VENV_DIR)],
            check=True, capture_output=True, text=True
        )
        return True, None
    except subprocess.CalledProcessError as e:
        return False, e.stderr


if __name__ == '__main__':
    check_only = '--check' in sys.argv

    if check_venv():
        print(f'OK: Virtual environment exists at {VENV_DIR}')
        sys.exit(0)

    if check_only:
        print(f'MISSING: Virtual environment not found at {VENV_DIR}')
        sys.exit(1)

    print(f'Creating virtual environment at {VENV_DIR}...')
    success, error = create_venv()
    if success:
        print('OK: Virtual environment created.')
        sys.exit(0)
    else:
        print(f'ERROR: Failed to create virtual environment:\n{error}')
        sys.exit(1)
