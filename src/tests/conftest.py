"""Фикстуры и конфиг Pytest."""
import sys
from pathlib import Path

# добавить src в path при запуске тестов из корня репозитория (src/tests/conftest.py -> root = репо, src = root/src)
root = Path(__file__).resolve().parent.parent.parent
src = root / "src"
if str(src) not in sys.path:
    sys.path.insert(0, str(src))
