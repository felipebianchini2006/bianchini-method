#!/usr/bin/env python3
from pathlib import Path

path = Path('.github/bootstrap/apply_impl.py')
content = path.read_text(encoding='utf-8')

old_replace_once = '''def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: esperado 1 ocorrência, encontrado {count}")
    return text.replace(old, new, 1)
'''
new_replace_once = r'''def replace_once(text: str, old: str, new: str, label: str) -> str:
    decode_newlines = "\\n" in old
    old = old.replace("\\n", "\n")
    if decode_newlines:
        new = new.replace("\\n", "\n")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: esperado 1 ocorrência, encontrado {count}")
    return text.replace(old, new, 1)
'''

old_regex_once = '''def regex_once(text: str, pattern: str, replacement: str, label: str, flags: int = 0) -> str:
    updated, count = re.subn(pattern, replacement, text, count=1, flags=flags)
    if count != 1:
        raise RuntimeError(f"{label}: esperado 1 match, encontrado {count}")
    return updated
'''
new_regex_once = '''def regex_once(text: str, pattern: str, replacement: str, label: str, flags: int = 0) -> str:
    match = re.search(pattern, text, flags)
    if match is None:
        raise RuntimeError(f"{label}: esperado 1 match, encontrado 0")
    if re.search(pattern, text[match.end():], flags):
        raise RuntimeError(f"{label}: encontrado mais de 1 match")
    return text[:match.start()] + replacement + text[match.end():]
'''

if old_replace_once not in content:
    raise SystemExit('Função replace_once esperada não foi encontrada.')
if old_regex_once not in content:
    raise SystemExit('Função regex_once esperada não foi encontrada.')

normalized = content.replace(old_replace_once, new_replace_once, 1)
normalized = normalized.replace(old_regex_once, new_regex_once, 1)
normalized = normalized.replace(
    r'new_write_task_brief + "\\n\\ndef write_report("',
    r'new_write_task_brief + "\n\ndef write_report("',
    1,
)
normalized = normalized.replace(
    'mutation_evidence.add_argument("--command", required=True)',
    'mutation_evidence.add_argument("--command", dest="mutation_command", required=True)',
    1,
)
normalized = normalized.replace(
    '                    command=args.command,\n                    report=args.report,',
    '                    command=args.mutation_command,\n                    report=args.report,',
    1,
)
if normalized == content:
    raise SystemExit('Nenhum ajuste de bootstrap foi aplicado.')
path.write_text(normalized, encoding='utf-8')
