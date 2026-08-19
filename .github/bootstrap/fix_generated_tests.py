#!/usr/bin/env python3
from pathlib import Path

path = Path('tests/test_method_package.py')
content = path.read_text(encoding='utf-8')

mutation_old = '''    def make_mutation_project(self, root: Path, report: dict[str, object]) -> tuple[Path, str]:
        state_path = self.make_v2_project(root, initialize_git=True)
'''
mutation_new = '''    def make_mutation_project(self, root: Path, report: dict[str, object]) -> tuple[Path, str]:
        root.rmdir()
        state_path = self.make_v2_project(root, initialize_git=True)
'''
if content.count(mutation_old) != 1:
    raise SystemExit(
        f'Fixture de mutação esperado uma vez, encontrado {content.count(mutation_old)}.'
    )
content = content.replace(mutation_old, mutation_new, 1)

no_delta_old = '''            delta_path = "docs/bianchini/changes/v1/spec-deltas/system.md"
            state["approval"]["package"]["files"].remove(delta_path)
            state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
'''
no_delta_new = '''            delta_path = "docs/bianchini/changes/v1/spec-deltas/system.md"
            state["approval"]["package"]["files"].remove(delta_path)
            plan_path = root / state["plans"][0]["path"]
            plan_path.write_text(
                read(plan_path).replace(", SD-001", ""),
                encoding="utf-8",
            )
            state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
'''
if content.count(no_delta_old) != 1:
    raise SystemExit(
        f'Fixture sem delta esperado uma vez, encontrado {content.count(no_delta_old)}.'
    )
content = content.replace(no_delta_old, no_delta_new, 1)

path.write_text(content.rstrip() + '\n', encoding='utf-8')
