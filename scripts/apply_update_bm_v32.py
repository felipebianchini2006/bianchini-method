#!/usr/bin/env python3
"""Integra o atualizador no CLI, contratos, testes e documentação."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    content = path.read_text(encoding="utf-8")
    count = content.count(old)
    if count != 1:
        raise SystemExit(f"{label}: esperado 1 trecho, encontrado {count}")
    path.write_text(content.replace(old, new, 1), encoding="utf-8")


bm = ROOT / "skills/_shared/scripts/bm.py"
replace_once(
    bm,
    "from bm_spec_diff import spec_diff\n",
    "from bm_spec_diff import spec_diff\n"
    "from bm_update import (\n"
    "    UpdateError as BMUpdateError,\n"
    "    render_update_result,\n"
    "    update_bianchini_method,\n"
    ")\n",
    "import do atualizador",
)
replace_once(
    bm,
    "    summary = commands.add_parser(\"status\")\n",
    "    updater = commands.add_parser(\"update-bm\")\n"
    "    updater.add_argument(\"--check\", action=\"store_true\")\n"
    "    updater.add_argument(\n"
    "        \"--skills-root\",\n"
    "        type=Path,\n"
    "        default=_SCRIPT_DIR.parents[1],\n"
    "    )\n"
    "    updater.add_argument(\"--timeout\", type=float, default=15.0)\n"
    "    updater.add_argument(\n"
    "        \"--format\", choices=[\"text\", \"json\"], default=\"text\"\n"
    "    )\n\n"
    "    summary = commands.add_parser(\"status\")\n",
    "parser update-bm",
)
replace_once(
    bm,
    "        elif args.command == \"status\":\n",
    "        elif args.command == \"update-bm\":\n"
    "            try:\n"
    "                update_result = update_bianchini_method(\n"
    "                    skills_root=args.skills_root,\n"
    "                    check_only=args.check,\n"
    "                    timeout=args.timeout,\n"
    "                )\n"
    "            except BMUpdateError as error:\n"
    "                raise BMError(str(error), error.exit_code) from error\n"
    "            if args.format == \"json\":\n"
    "                emit(update_result)\n"
    "            else:\n"
    "                print(render_update_result(update_result), end=\"\")\n"
    "        elif args.command == \"status\":\n",
    "handler update-bm",
)


tests = ROOT / "tests/test_method_package.py"
replace_once(
    tests,
    '    "homologar-sistema",\n)\n',
    '    "homologar-sistema",\n    "update-bm",\n)\n',
    "registro da skill pública",
)
replace_once(
    tests,
    '                if name == "executar-direto":\n',
    '                if name in {"executar-direto", "update-bm"}:\n',
    "invocação explícita das skills manuais",
)
replace_once(
    tests,
    '            "ContextEfficiencyScenarios",\n            "AdaptivePolicyScenarios",\n',
    '            "ContextEfficiencyScenarios",\n'
    '            "SelfUpdateScenarios",\n'
    '            "AdaptivePolicyScenarios",\n',
    "cobertura do shard de atualização",
)


readme = ROOT / "README.md"
replace_once(
    readme,
    "# Bianchini Method v3.1 — Context Efficiency\n",
    "# Bianchini Method v3.2 — Self Update\n",
    "título da versão",
)
replace_once(
    readme,
    "`v3.1` é a versão do pacote.",
    "`v3.2` é a versão do pacote.",
    "versão do pacote",
)
replace_once(
    readme,
    "Sistema de oito skills",
    "Sistema de nove skills",
    "contagem de skills",
)
replace_once(
    readme,
    "- `homologar-sistema`: confirma unitários/integração/regressão/E2E/mutação do release, executa o RC real por perfil/plataforma, faz varredura visual e decide o aceite.\n",
    "- `homologar-sistema`: confirma unitários/integração/regressão/E2E/mutação do release, executa o RC real por perfil/plataforma, faz varredura visual e decide o aceite.\n"
    "- `update-bm`: verifica a versão oficial e atualiza a instalação local com backup e rollback; invocação exclusivamente manual.\n",
    "lista de skills",
)
replace_once(
    readme,
    "checkpoint  proof-map  spec-diff  mutation-evidence  telemetry  status\n",
    "checkpoint  proof-map  spec-diff  mutation-evidence  update-bm  telemetry  status\n",
    "lista de comandos",
)
replace_once(
    readme,
    "Nenhuma instalação ou sincronização é executada automaticamente.\n",
    "Após esta instalação, verifique ou atualize explicitamente com:\n\n"
    "```bash\n"
    "python3 ~/.codex/skills/_shared/scripts/bm.py update-bm --check\n"
    "python3 ~/.codex/skills/_shared/scripts/bm.py update-bm\n"
    "```\n\n"
    "Também é possível usar `/update-bm`. Nenhuma sincronização ocorre sem invocação explícita.\n",
    "instruções de atualização",
)
replace_once(
    readme,
    "/homologar-sistema\n```\n",
    "/homologar-sistema\n/update-bm\n```\n",
    "uso da skill update-bm",
)


changelog = ROOT / "CHANGELOG.md"
replace_once(
    changelog,
    "# Changelog\n\n",
    "# Changelog\n\n"
    "## 3.2.0 - Self Update seguro\n\n"
    "- adiciona `/update-bm` e `bm.py update-bm` com consulta explícita da versão oficial;\n"
    "- atualiza instalações copiadas substituindo somente diretórios gerenciados e preservando skills alheias;\n"
    "- cria backup persistente e executa rollback quando uma substituição falha;\n"
    "- bloqueia archive com path traversal, symlink, arquivo especial ou versão divergente;\n"
    "- em checkout Git, exige `main` limpa e fast-forward de `origin/main`;\n"
    "- nunca faz downgrade e oferece `--check` sem alteração de arquivos.\n\n",
    "entrada do changelog",
)


contract = ROOT / "skills/_shared/METHOD_CONTRACT.md"
replace_once(
    contract,
    "## Fontes de verdade e segurança\n",
    "## Atualização do método\n\n"
    "`/update-bm` é exclusivamente manual e executa `bm.py update-bm`. A versão local vive em `_shared/VERSION`; a fonte remota é a `main` oficial. Instalação copiada preserva diretórios alheios, cria backup e substitui somente as skills gerenciadas. Checkout Git exige `main`, árvore limpa e fast-forward. Versão local igual ou superior nunca é substituída. Falha de rede, archive inseguro, divergência de versão ou erro de escrita bloqueia sem declarar atualização.\n\n"
    "## Fontes de verdade e segurança\n",
    "contrato de atualização",
)


ci = ROOT / ".github/workflows/ci.yml"
replace_once(
    ci,
    "            skills/_shared/scripts/bm_mutation.py \\\n            tests/test_method_package.py \\\n",
    "            skills/_shared/scripts/bm_mutation.py \\\n"
    "            skills/_shared/scripts/bm_update.py \\\n"
    "            tests/test_method_package.py \\\n",
    "py_compile do atualizador",
)
replace_once(
    ci,
    "            tests/test_context_efficiency_review.py\n",
    "            tests/test_context_efficiency_review.py \\\n"
    "            tests/test_self_update.py\n",
    "py_compile dos testes de atualização",
)
replace_once(
    ci,
    '          grep -q "mutation-evidence" /tmp/bm-help.txt\n',
    '          grep -q "mutation-evidence" /tmp/bm-help.txt\n'
    '          grep -q "update-bm" /tmp/bm-help.txt\n',
    "validação do entrypoint update-bm",
)
