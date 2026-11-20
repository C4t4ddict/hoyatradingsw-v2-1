"""Run tests affected by changed Python modules via their transitive imports."""
import argparse
import ast
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True, encoding='utf-8').splitlines()


def affected(files, changed):
    modules = {str(Path(p).with_suffix('')).replace('\\', '.').replace('/', '.'): p for p in files if p.endswith('.py')}
    edges = {}
    for module, path in modules.items():
        imports = set()
        tree = ast.parse((ROOT/path).read_text(encoding='utf-8-sig'))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                prefix = node.module or ''
                if node.level:
                    parent = module.split('.')[:-node.level]
                    prefix = '.'.join(parent + ([prefix] if prefix else []))
                imports.add(prefix)
                imports.update(f'{prefix}.{alias.name}' for alias in node.names)
        edges[module] = {dep for dep in imports if dep in modules}
    dirty = {m for m,p in modules.items() if p in changed}
    while True:
        updated = dirty | {m for m,deps in edges.items() if deps & dirty}
        if updated == dirty:
            break
        dirty = updated
    return sorted(p for m,p in modules.items() if m in dirty and p.startswith('tests/test_'))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', default='origin/develop')
    args = parser.parse_args()
    files = sorted(set(git('ls-files', '--cached', '--others', '--exclude-standard')))
    changed = set(git('diff', '--name-only', args.base, '--')) | set(git('ls-files', '--others', '--exclude-standard'))
    all_tests = any(p.endswith('requirements.txt') for p in changed)
    selected = sorted(p for p in files if p.startswith('tests/test_') and p.endswith('.py')) if all_tests else affected(files, changed)
    print('Selected tests:', ', '.join(selected) or '(no Python impact)', flush=True)
    suite = unittest.TestSuite()
    sys.path.insert(0, str(ROOT))
    for path in selected:
        suite.addTests(unittest.defaultTestLoader.discover(str(ROOT/'tests'), pattern=Path(path).name))
    return 0 if unittest.TextTestRunner(verbosity=1).run(suite).wasSuccessful() else 1


if __name__ == '__main__':
    sys.exit(main())
