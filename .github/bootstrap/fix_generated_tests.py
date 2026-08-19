#!/usr/bin/env python3
from pathlib import Path

path = Path('tests/test_method_package.py')
content = path.read_text(encoding='utf-8')
old = '''    def make_mutation_project(self, root: Path, report: dict[str, object]) -> tuple[Path, str]:
        state_path = self.make_v2_project(root, initialize_git=True)
'''
new = '''    def make_mutation_project(self, root: Path, report: dict[str, object]) -> tuple[Path, str]:
        root.rmdir()
        state_path = self.make_v2_project(root, initialize_git=True)
'''
if content.count(old) != 1:
    raise SystemExit(f'Fixture de mutação esperado uma vez, encontrado {content.count(old)}.')
updated = content.replace(old, new, 1).rstrip() + '\n'
path.write_text(updated, encoding='utf-8')
