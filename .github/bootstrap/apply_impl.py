#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path.cwd()

MODULES = {'skills/_shared/scripts/bm_feature_support.py': '.github/bootstrap/modules/bm_feature_support.py', 'skills/_shared/scripts/bm_context.py': '.github/bootstrap/modules/bm_context.py', 'skills/_shared/scripts/bm_spec_diff.py': '.github/bootstrap/modules/bm_spec_diff.py', 'skills/_shared/scripts/bm_mutation.py': '.github/bootstrap/modules/bm_mutation.py'}
CONTEXT_DOC = '# Context Efficiency v3.1\n\nEsta referência descreve as projeções derivadas adicionadas ao Bianchini Method. Nenhuma delas substitui o `PROJECT_STATE.md`, a spec completa, o plano aprovado, o ledger ou as evidências do release.\n\n## Enforcement das unidades quality v2\n\nCada unidade de um plano `planning.quality_version: 2` deve declarar:\n\n```markdown\n**Change:** state-machine\n**Readiness refs:** D-001, A-001, P-001, U-001, SD-001\n```\n\n`planning-audit` valida de forma determinística:\n\n- categoria `Change` suportada pela política;\n- formato e existência de cada referência;\n- presença do plano em `destinations` do item de readiness;\n- cobertura de todos os itens de readiness destinados ao plano.\n\nPacotes `quality_version: 1` permanecem compatíveis.\n\n## Brief hidratado\n\n`task-brief` pode produzir uma projeção compacta do contexto da unidade:\n\n```bash\npython3 <bm.py> task-brief \\\n  --plan docs/bianchini/changes/v3/plans/P02-auth.md \\\n  --task 3 \\\n  --state docs/living/PROJECT_STATE.md \\\n  --root . \\\n  --hydrate-context \\\n  --ledger-tail-lines 40 \\\n  --output .superpowers/bianchini/context/P02-T03.md\n```\n\nA projeção contém somente o digest aprovado, metadados do plano, itens de readiness citados, seções exatas de spec, `verification.fast`, execução ativa e final do ledger. O arquivo deve permanecer em scratch ignorado e pode ser regenerado a qualquer momento.\n\n## Diff de specs\n\nA spec futura completa continua sendo a fonte de verdade. `spec-diff` cria apenas uma visualização ADDED, MODIFIED e REMOVED:\n\n```bash\npython3 <bm.py> spec-diff \\\n  --root . \\\n  --base docs/bianchini/current/specs/auth.md \\\n  --target docs/bianchini/changes/v3/spec-deltas/auth.md \\\n  --output artifacts/bianchini/v3/deltas/auth.md\n```\n\nAs duas specs devem usar IDs estáveis em headings:\n\n```markdown\n## AUTH-001: Renovação de sessão\n```\n\nO resultado carrega os SHA-256 da base e do target. Alterar qualquer fonte torna a projeção anterior obsoleta.\n\n## Evidência de mutation testing\n\n`mutation-evidence verify` normaliza e valida o relatório no estado final do código:\n\n```bash\npython3 <bm.py> mutation-evidence verify \\\n  --state docs/living/PROJECT_STATE.md \\\n  --root . \\\n  --plan P03 \\\n  --risk-seam pricing-calculation \\\n  --tool normalized \\\n  --command "python3 mutation_runner.py" \\\n  --report artifacts/mutation/report.json \\\n  --revision "$(git rev-parse HEAD)" \\\n  --output artifacts/bianchini/v3/mutation/P03-pricing.json\n```\n\nFormato normalizado mínimo:\n\n```json\n{\n  "schema_version": 1,\n  "mutants": [\n    {"id": "M1", "status": "killed"},\n    {\n      "id": "M2",\n      "status": "survived",\n      "classification": "equivalent",\n      "justification": "O operador produz o mesmo resultado no domínio aprovado."\n    }\n  ]\n}\n```\n\nTambém é aceito o relatório JSON do Stryker. Survivors usam `equivalent`, `unreachable`, `non_material` ou `blocking`. Classificação não bloqueante exige justificativa. Revisão divergente do HEAD ou do RC, survivor sem classificação, mutante ignorado ou erro de execução bloqueiam quando a política for `selective` ou `required_selective`. Percentual global nunca decide o gate.\n'
README_INSERT = '\n## Eficiência de contexto\n\nA v3.1 mantém as fontes completas e adiciona projeções determinísticas para reduzir leitura ativa:\n\n- `planning-audit` exige `Change` e `Readiness refs` nas unidades quality v2;\n- `task-brief --hydrate-context` reúne somente readiness, specs, gates e ledger aplicáveis;\n- `spec-diff` deriva ADDED, MODIFIED e REMOVED entre specs completas;\n- `mutation-evidence verify` vincula relatório, seam, plano e revisão do código sem usar score global.\n\nDetalhes: [`skills/_shared/CONTEXT_EFFICIENCY.md`](skills/_shared/CONTEXT_EFFICIENCY.md).\n'
CHANGELOG_SECTION = '## 3.1.0 - Context Efficiency determinística\n\n- exige `Change` e `Readiness refs` em cada unidade de novos planejamentos quality v2, validando existência, destino e cobertura no readiness;\n- adiciona contexto hidratado opcional ao `task-brief`, limitado à unidade, specs referenciadas, readiness aplicável, gates rápidos e final do ledger;\n- adiciona `spec-diff` como projeção ADDED/MODIFIED/REMOVED vinculada aos digests das specs completas;\n- adiciona `mutation-evidence verify` para normalizar relatórios, classificar survivors e vincular a prova ao HEAD ou fingerprint do RC;\n- preserva `quality_version: 1`, specs completas, aprovação única e ausência de score global de mutação;\n- adiciona CI versionada para executar todos os shards e validar o CLI.\n\n'
CONTRACT_INSERT = '\n## Eficiência de contexto derivada\n\nUnidades de novos planos `quality_version: 2` declaram `Change` e `Readiness refs`; o audit valida categoria, existência, destino e cobertura. `task-brief --hydrate-context`, `spec-diff` e `mutation-evidence verify` geram projeções reproduzíveis sem criar nova fonte de verdade. Contratos, comandos e formatos estão em [`CONTEXT_EFFICIENCY.md`](CONTEXT_EFFICIENCY.md).\n'
SDD_INSERT = '\nPara `planning.quality_version: 2`, `planning-audit` também exige `Change` e `Readiness refs` em cada unidade e valida as referências contra `READINESS.md` e seus `destinations`. A validação é executável; não basta mencionar os campos apenas na instrução da skill.\n'
EXECUTE_INSERT = '\nQuando o plano usar `quality_version: 2`, preferir `task-brief --hydrate-context --state <PROJECT_STATE.md> --root <repo>` para carregar somente readiness, seções de spec, gates rápidos e final do ledger da unidade. A projeção permanece em `.superpowers/` e nunca substitui os artefatos aprovados.\n'
MUTATION_EXECUTE_INSERT = '\nQuando `bm.py policy` retornar `selective` ou `required_selective`, validar o relatório final com `mutation-evidence verify`. A evidência deve apontar o mesmo HEAD ou fingerprint do RC, classificar todos os survivors e permanecer vigente após a última alteração no seam.\n'

def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: esperado 1 ocorrência, encontrado {count}")
    return text.replace(old, new, 1)


def regex_once(text: str, pattern: str, replacement: str, label: str, flags: int = 0) -> str:
    updated, count = re.subn(pattern, replacement, text, count=1, flags=flags)
    if count != 1:
        raise RuntimeError(f"{label}: esperado 1 match, encontrado {count}")
    return updated


def write(path: str, content: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


for path, source in MODULES.items():
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes((ROOT / source).read_bytes())

bm_path = ROOT / "skills/_shared/scripts/bm.py"
bm = bm_path.read_text(encoding="utf-8")

import_anchor = "from pathlib import Path\\nfrom typing import Any\\n"
import_block = """from pathlib import Path
from typing import Any


_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from bm_context import (
    QUALITY_V2_UNIT_FIELDS,
    hydrate_task_context,
    mutation_mode_for_change,
    validate_quality_v2_plan,
)
from bm_mutation import mutation_evidence_verify
from bm_spec_diff import spec_diff
"""
bm = replace_once(bm, import_anchor, import_block, "imports")

bm = replace_once(
    bm,
    "    execution_unit_words: list[int] = []\\n    for plan in state[\"plans\"]:\\n",
    "    execution_unit_words: list[int] = []\\n    plan_contents: dict[str, str] = {}\\n    for plan in state[\"plans\"]:\\n",
    "cache de planos",
)
bm = replace_once(
    bm,
    "        if not content:\\n            continue\\n        plan_words.append(word_count(content))\\n",
    "        if not content:\\n            continue\\n        plan_contents[plan[\"path\"]] = content\\n        plan_words.append(word_count(content))\\n",
    "armazenamento de conteúdo do plano",
)
bm = replace_once(
    bm,
    "            for field in UNIT_FIELDS:\\n",
    "            required_fields = (\\n                (*UNIT_FIELDS, *QUALITY_V2_UNIT_FIELDS) if quality_v2 else UNIT_FIELDS\\n            )\\n            for field in required_fields:\\n",
    "campos obrigatórios da unidade",
)
readiness_anchor = """        errors.extend(readiness_errors)
        warnings.extend(readiness_warnings)
        checker = state[\"planning\"].get(\"checker\")
"""
readiness_patch = """        errors.extend(readiness_errors)
        warnings.extend(readiness_warnings)
        readiness_value = state[\"planning\"].get(\"readiness\")
        readiness_path, _ = planning_file(root, readiness_value, \"planning.readiness\")
        if readiness_path is not None and readiness_path.is_file():
            readiness_value_document = readiness_document(readiness_path)
            for plan_path_value, plan_content in plan_contents.items():
                errors.extend(
                    validate_quality_v2_plan(
                        plan_path_value,
                        plan_content,
                        readiness_value_document,
                    )
                )
        checker = state[\"planning\"].get(\"checker\")
"""
bm = replace_once(bm, readiness_anchor, readiness_patch, "validação de readiness por unidade")

mutation_policy_pattern = r'''    if risk == "low" or change_kind in PURE_NON_LOGIC_CHANGES:\n        mutation_mode = "not_required"\n    elif risk in \{"high", "critical"\}:\n        mutation_mode = "required_selective"\n    elif change_kind in MUTATION_RELEVANT_CHANGES:\n        mutation_mode = "selective"\n    else:\n        mutation_mode = "not_required"'''
bm = regex_once(
    bm,
    mutation_policy_pattern,
    '    mutation_mode = mutation_mode_for_change(risk, change_kind)',
    "política compartilhada de mutação",
)

bm = bm.replace(
    'rf"(?ms)^###\\s+(?:Tarefa|Task)\\s+{re.escape(task)}\\b.*?(?=^###\\s+(?:Tarefa|Task)\\s+\\S+|\\Z)"',
    'rf"(?ms)^###\\s+(?:Tarefa|Task|Slice)\\s+{re.escape(task)}\\b.*?(?=^###\\s+(?:Tarefa|Task|Slice)\\s+\\S+|\\Z)"',
)
if "(?:Tarefa|Task|Slice)" not in bm:
    raise RuntimeError("extract_task não foi ampliado para Slice")

new_write_task_brief = '''def write_task_brief(
    plan: Path,
    task: str | None,
    tasks: str | None,
    group: str | None,
    output: Path,
    state_path: Path | None = None,
    root: Path | None = None,
    hydrate_context: bool = False,
    ledger_tail_lines: int = 40,
) -> dict[str, Any]:
    if ledger_tail_lines < 0:
        raise BMError("--ledger-tail-lines não pode ser negativo")
    if group:
        labels = [group]
        sections = [extract_group(plan, group)]
        title = group
    else:
        labels = parse_task_selector(tasks or task or "")
        sections = [extract_task(plan, label) for label in labels]
        title = ", ".join(labels)
        if len(labels) > 1:
            executions = []
            for label, section in zip(labels, sections):
                match = re.search(r"(?mi)^\\*\\*Execution:\\*\\*\\s*([a-z_]+)\\s*$", section)
                if not match:
                    raise BMError(f"tarefa {label} não declara Execution")
                executions.append(match.group(1))
            if any(mode != "grouped" for mode in executions):
                raise BMError(
                    "brief com várias tarefas exige Execution: grouped em todas as unidades"
                )
    source_hash = file_digest(plan)
    unit_hashes = [content_digest(section) for section in sections]
    group_digest = content_digest("\\n--- bm-unit ---\\n".join(sections))
    kind = "heading" if group else "group" if len(labels) > 1 else "task"
    group_id = f"group-{group_digest[:12]}" if kind in {"group", "heading"} else None
    metadata = "\\n".join(
        f"- Unit `{label}` SHA-256: `{digest}`"
        for label, digest in zip(labels, unit_hashes)
    )
    content = (
        f"# Task Brief {title}\\n\\n- Plan: `{plan}`\\n"
        f"- Plan SHA-256: `{source_hash}`\\n"
        f"- Kind: `{kind}`\\n"
        f"- Group ID: `{group_id or 'n/a'}`\\n"
        f"- Group SHA-256: `{group_digest}`\\n{metadata}\\n\\n"
        + "\\n".join(sections)
    )
    context_metadata: dict[str, Any] | None = None
    if hydrate_context:
        if state_path is None or root is None:
            raise BMError("--hydrate-context exige --state e --root")
        state = validate_state(state_path)
        try:
            context, context_metadata = hydrate_task_context(
                root=root,
                state=state,
                plan_path=plan,
                labels=labels,
                sections=sections,
                ledger_tail_lines=ledger_tail_lines,
            )
        except ValueError as error:
            raise BMError(str(error)) from error
        content = content.rstrip() + "\\n\\n" + context
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content.rstrip() + "\\n", encoding="utf-8")
    return {
        "brief": str(output),
        "plan_digest": source_hash,
        "kind": kind,
        "group_id": group_id,
        "group_digest": group_digest,
        "tasks": labels,
        "unit_digests": unit_hashes,
        "hydrated": hydrate_context,
        "context_digest": context_metadata.get("context_digest") if context_metadata else None,
    }
'''
bm = regex_once(
    bm,
    r"def write_task_brief\(.*?\n\ndef write_report\(",
    new_write_task_brief + "\\n\\ndef write_report(",
    "write_task_brief",
    flags=re.DOTALL,
)

brief_parser_anchor = '''    brief.add_argument("--output", type=Path, required=True)

    report = commands.add_parser("report")
'''
brief_parser_patch = '''    brief.add_argument("--state", type=Path)
    brief.add_argument("--root", type=Path)
    brief.add_argument("--hydrate-context", action="store_true")
    brief.add_argument("--ledger-tail-lines", type=int, default=40)
    brief.add_argument("--output", type=Path, required=True)

    spec_delta = commands.add_parser("spec-diff")
    spec_delta.add_argument("--root", type=Path, required=True)
    spec_delta.add_argument("--base", type=Path, required=True)
    spec_delta.add_argument("--target", type=Path, required=True)
    spec_delta.add_argument("--output", type=Path, required=True)

    mutation_evidence = commands.add_parser("mutation-evidence")
    mutation_evidence.add_argument("action", choices=["verify"])
    mutation_evidence.add_argument("--state", type=Path, required=True)
    mutation_evidence.add_argument("--root", type=Path, required=True)
    mutation_evidence.add_argument("--plan", required=True)
    mutation_evidence.add_argument("--risk-seam", required=True)
    mutation_evidence.add_argument(
        "--tool", choices=["normalized", "stryker"], required=True
    )
    mutation_evidence.add_argument("--command", required=True)
    mutation_evidence.add_argument("--report", type=Path, required=True)
    mutation_evidence.add_argument("--revision", required=True)
    mutation_evidence.add_argument("--classifications", type=Path)
    mutation_evidence.add_argument("--output", type=Path, required=True)

    report = commands.add_parser("report")
'''
bm = replace_once(bm, brief_parser_anchor, brief_parser_patch, "parsers de contexto")

main_anchor = '''        elif args.command == "task-brief":
            emit(write_task_brief(args.plan, args.task, args.tasks, args.group, args.output))
        elif args.command == "report":
'''
main_patch = '''        elif args.command == "task-brief":
            emit(
                write_task_brief(
                    args.plan,
                    args.task,
                    args.tasks,
                    args.group,
                    args.output,
                    args.state,
                    args.root,
                    args.hydrate_context,
                    args.ledger_tail_lines,
                )
            )
        elif args.command == "spec-diff":
            try:
                emit(
                    spec_diff(
                        root=args.root,
                        base=args.base,
                        target=args.target,
                        output=args.output,
                    )
                )
            except ValueError as error:
                raise BMError(str(error)) from error
        elif args.command == "mutation-evidence":
            try:
                mutation_result = mutation_evidence_verify(
                    root=args.root,
                    state=validate_state(args.state),
                    plan_id=args.plan,
                    risk_seam=args.risk_seam,
                    tool=args.tool,
                    command=args.command,
                    report=args.report,
                    output=args.output,
                    revision=args.revision,
                    classifications=args.classifications,
                )
            except ValueError as error:
                raise BMError(str(error)) from error
            if mutation_result["status"] != "passed":
                raise BMError(
                    "BLOQUEADO: mutation evidence bloqueada; consulte "
                    + mutation_result["output"],
                    EXIT_BLOCKED,
                )
            emit(mutation_result)
        elif args.command == "report":
'''
bm = replace_once(bm, main_anchor, main_patch, "handlers de contexto")

bm_path.write_text(bm, encoding="utf-8")

# Amplia o teste de dependências para todos os módulos do CLI.
test_path = ROOT / "tests/test_method_package.py"
tests = test_path.read_text(encoding="utf-8")
old_test = '''    def test_cli_has_no_third_party_imports(self) -> None:
        content = read(ROOT / "skills" / "_shared" / "scripts" / "bm.py")
        for dependency in ("yaml", "jsonschema", "click", "pydantic"):
            self.assertNotRegex(content, rf"(?m)^(?:from|import)\\s+{dependency}\\b")
'''
new_test = '''    def test_cli_has_no_third_party_imports(self) -> None:
        scripts = ROOT / "skills" / "_shared" / "scripts"
        content = "\\n".join(read(path) for path in sorted(scripts.glob("bm*.py")))
        for dependency in ("yaml", "jsonschema", "click", "pydantic"):
            self.assertNotRegex(content, rf"(?m)^(?:from|import)\\s+{dependency}\\b")
'''
tests = replace_once(tests, old_test, new_test, "teste de dependências")
test_path.write_text(tests, encoding="utf-8")

write("skills/_shared/CONTEXT_EFFICIENCY.md", CONTEXT_DOC)

readme_path = ROOT / "README.md"
readme = readme_path.read_text(encoding="utf-8")
readme = replace_once(
    readme,
    "# Bianchini Method v3.0 — Planning Stability",
    "# Bianchini Method v3.1 — Context Efficiency",
    "versão README",
)
readme = replace_once(
    readme,
    "`v3.0` é a versão do pacote.",
    "`v3.1` é a versão do pacote.",
    "versão do pacote",
)
readme = replace_once(
    readme,
    "checkpoint  proof-map  telemetry  status",
    "checkpoint  proof-map  spec-diff  mutation-evidence  telemetry  status",
    "lista de comandos",
)
readme = replace_once(readme, "\n## Homologação e manual\n", README_INSERT + "\n## Homologação e manual\n", "seção README")
readme_path.write_text(readme, encoding="utf-8")

changelog_path = ROOT / "CHANGELOG.md"
changelog = changelog_path.read_text(encoding="utf-8")
changelog = replace_once(changelog, "# Changelog\n\n", "# Changelog\n\n" + CHANGELOG_SECTION, "changelog")
changelog_path.write_text(changelog, encoding="utf-8")

contract_path = ROOT / "skills/_shared/METHOD_CONTRACT.md"
contract = contract_path.read_text(encoding="utf-8")
contract = replace_once(contract, "\n## Fontes de verdade e segurança\n", CONTRACT_INSERT + "\n## Fontes de verdade e segurança\n", "contrato")
contract_path.write_text(contract, encoding="utf-8")

sdd_path = ROOT / "skills/sdd-planning/SKILL.md"
sdd = sdd_path.read_text(encoding="utf-8")
sdd = replace_once(sdd, "\n## 8. Definir garantia e verificação\n", SDD_INSERT + "\n## 8. Definir garantia e verificação\n", "sdd planning")
sdd_path.write_text(sdd, encoding="utf-8")

execute_path = ROOT / "skills/executar-plano/SKILL.md"
execute = execute_path.read_text(encoding="utf-8")
execute = replace_once(execute, "\n## 4. Autonomia e plano congelado\n", EXECUTE_INSERT + "\n## 4. Autonomia e plano congelado\n", "executor contexto")
execute = replace_once(execute, "\n## 7. Revisão e convergência\n", MUTATION_EXECUTE_INSERT + "\n## 7. Revisão e convergência\n", "executor mutação")
execute_path.write_text(execute, encoding="utf-8")
