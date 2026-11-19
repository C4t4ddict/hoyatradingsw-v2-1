"""Read-only environment diagnosis. Never prints secret values."""
import importlib.util
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    problems = []
    print(f'Python {sys.version.split()[0]} | venv={sys.prefix != sys.base_prefix}')
    if sys.prefix == sys.base_prefix:
        problems.append('프로젝트 .venv Python으로 실행하세요.')
    if sys.version_info[:2] != (3, 12):
        print('권장/CI Python: 3.12')
    for module in ('fastapi', 'pandas', 'ccxt', 'cryptography', 'sklearn', 'dotenv'):
        if importlib.util.find_spec(module) is None:
            problems.append(f'누락 의존성: {module}')
    node = shutil.which('node')
    if node:
        version = subprocess.check_output([node, '--version'], text=True).strip()
        print(f'Node {version} | CI Node: 22')
        if int(version.lstrip('v').split('.')[0]) < 22:
            problems.append('Node 22 이상을 사용하세요.')
    else:
        problems.append('Node가 없습니다.')
    print(f'.env 존재: {(root / ".env").exists()}')
    for name in ('runtime.sqlite3', 'trading_ledger.sqlite3'):
        path = root / 'data' / name
        if path.exists():
            with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as db:
                status = db.execute('PRAGMA quick_check').fetchone()[0]
                print(f'{name}: {status}')
                if status != 'ok':
                    problems.append(f'{name}: 무결성 검사 실패')
    for problem in problems:
        print(problem)
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
