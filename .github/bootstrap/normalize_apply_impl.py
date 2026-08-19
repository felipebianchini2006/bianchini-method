#!/usr/bin/env python3
from pathlib import Path

path = Path('.github/bootstrap/apply_impl.py')
content = path.read_text(encoding='utf-8')
normalized = content.replace('\\\\n', '\\n')
normalized = normalized.replace(
    'updated, count = re.subn(pattern, replacement, text, count=1, flags=flags)',
    'updated, count = re.subn(pattern, lambda _match: replacement, text, count=1, flags=flags)',
)
if normalized == content:
    raise SystemExit('Nenhum ajuste de bootstrap foi aplicado.')
path.write_text(normalized, encoding='utf-8')
