#!/usr/bin/env python3
from pathlib import Path

path = Path('.github/bootstrap/apply_impl.py')
content = path.read_text(encoding='utf-8')
normalized = content.replace('\\\\n', '\\n')
if normalized == content:
    raise SystemExit('Nenhum escape duplo de newline foi encontrado no bootstrap.')
path.write_text(normalized, encoding='utf-8')
