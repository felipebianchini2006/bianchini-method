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


updater = ROOT / "skills/_shared/scripts/bm_update.py"
replace_once(
    updater,
    "def _base_result(\n",
    "def _normalized_github_repository(remote_url: str) -> str | None:\n"
    "    value = remote_url.strip()\n"
    "    patterns = (\n"
    "        r\"https://github\\.com/([^/]+/[^/]+?)(?:\\.git)?/?$\",\n"
    "        r\"git@github\\.com:([^/]+/[^/]+?)(?:\\.git)?$\",\n"
    "        r\"ssh://git@github\\.com/([^/]+/[^/]+?)(?:\\.git)?/?$\",\n"
    "    )\n"
    "    for pattern in patterns:\n"
    "        match = re.fullmatch(pattern, value, flags=re.IGNORECASE)\n"
    "        if match:\n"
    "            return match.group(1).removesuffix(\".git\").lower()\n"
    "    return None\n\n\n"
    "def _verify_official_origin(repo: Path, repository: str) -> None:\n"
    "    remote = _run_git(repo, \"config\", \"--get\", \"remote.origin.url\").stdout.strip()\n"
    "    normalized = _normalized_github_repository(remote)\n"
    "    if normalized != repository.lower():\n"
    "        raise UpdateError(\n"
    "            \"origin não aponta para o repositório oficial \"\n"
    "            f\"{repository}: {remote or '<ausente>'}\",\n"
    "            3,\n"
    "        )\n\n\n"
    "def _base_result(\n",
    "validação da origem oficial",
)
replace_once(
    updater,
    "    _run_git(repo, \"fetch\", \"origin\", branch)\n",
    "    _verify_official_origin(repo, repository)\n"
    "    _run_git(repo, \"fetch\", \"origin\", branch)\n",
    "verificação da origem antes do fetch",
)
replace_once(
    updater,
    "        for member in members:\n            relative = _safe_member_path(member.name)\n",
    "        seen: set[PurePosixPath] = set()\n"
    "        for member in members:\n"
    "            relative = _safe_member_path(member.name)\n"
    "            if relative in seen:\n"
    "                raise UpdateError(f\"arquivo duplicado no pacote: {member.name}\")\n"
    "            seen.add(relative)\n",
    "bloqueio de entradas duplicadas no archive",
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
    '                if name == "executar-direto":\n'
    '                    self.assertEqual(metadata.get("disable-model-invocation"), "true")\n',
    '                if name in {"executar-direto", "update-bm"}:\n'
    '                    self.assertEqual(metadata.get("disable-model-invocation"), "true")\n',
    "frontmatter das skills manuais",
)
replace_once(
    tests,
    '            "ContextEfficiencyScenarios",\n            "AdaptivePolicyScenarios",\n',
    '            "ContextEfficiencyScenarios",\n'
    '            "SelfUpdateScenarios",\n'
    '            "AdaptivePolicyScenarios",\n',
    "cobertura do shard de atualização",
)
replace_once(
    tests,
    '''                if name == "executar-direto":
                    self.assertEqual(
                        description,
                        "Use quando o usuário solicitar a implementação estruturada de um projeto pequeno ou de uma entrega coesa sem planejamento SDD completo.",
                    )
                    self.assertEqual(metadata["disable-model-invocation"], "true")
                else:
                    self.assertTrue(
                        f"/{name}" in description or "method_version 2" in description
                    )
''',
    '''                if name == "executar-direto":
                    self.assertEqual(
                        description,
                        "Use quando o usuário solicitar a implementação estruturada de um projeto pequeno ou de uma entrega coesa sem planejamento SDD completo.",
                    )
                    self.assertEqual(metadata["disable-model-invocation"], "true")
                elif name == "update-bm":
                    self.assertIn("somente com invocação explícita", description)
                    self.assertEqual(metadata["disable-model-invocation"], "true")
                else:
                    self.assertTrue(
                        f"/{name}" in description or "method_version 2" in description
                    )
''',
    "ativação explícita da skill update-bm",
)


self_tests = ROOT / "tests/test_self_update.py"
replace_once(
    self_tests,
    '            git(root, "clone", "--branch", "main", str(remote), str(local))\n\n'
    '            write_installation(seed / "skills", "3.2.0", "new")\n',
    '            git(root, "clone", "--branch", "main", str(remote), str(local))\n'
    '            official = "https://github.com/felipebianchini2006/bianchini-method.git"\n'
    '            git(local, "remote", "set-url", "origin", official)\n'
    '            git(\n'
    '                local,\n'
    '                "config",\n'
    '                f"url.file://{remote.resolve()}/.insteadOf",\n'
    '                official,\n'
    '            )\n\n'
    '            write_installation(seed / "skills", "3.2.0", "new")\n',
    "fixture Git com URL oficial",
)
replace_once(
    self_tests,
    '    def test_dirty_git_checkout_blocks_before_fetch_or_merge(self) -> None:\n',
    '''    def test_git_checkout_rejects_non_official_origin(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "repo"
            root.mkdir(parents=True)
            git(root, "init", "-b", "main")
            git(root, "config", "user.name", "BM Test")
            git(root, "config", "user.email", "test@example.invalid")
            write_installation(root / "skills", "3.1.0", "local")
            git(root, "add", "skills")
            git(root, "commit", "-m", "base")
            git(root, "remote", "add", "origin", "https://github.com/example/fake.git")
            fetch, _ = fetcher("3.2.0")

            with self.assertRaisesRegex(UpdateError, "repositório oficial"):
                update_bianchini_method(
                    skills_root=root / "skills",
                    fetch_bytes=fetch,
                )

            self.assertEqual((root / "skills/_shared/VERSION").read_text().strip(), "3.1.0")

    def test_dirty_git_checkout_blocks_before_fetch_or_merge(self) -> None:
''',
    "teste de origem Git não oficial",
)


readme = ROOT / "README.md"
for old, new, label in (
    ("# Bianchini Method v3.1 — Context Efficiency\n", "# Bianchini Method v3.2 — Self Update\n", "título da versão"),
    ("`v3.1` é a versão do pacote.", "`v3.2` é a versão do pacote.", "versão do pacote"),
    ("Sistema de oito skills", "Sistema de nove skills", "contagem de skills"),
    (
        "- `homologar-sistema`: confirma unitários/integração/regressão/E2E/mutação do release, executa o RC real por perfil/plataforma, faz varredura visual e decide o aceite.\n",
        "- `homologar-sistema`: confirma unitários/integração/regressão/E2E/mutação do release, executa o RC real por perfil/plataforma, faz varredura visual e decide o aceite.\n"
        "- `update-bm`: verifica a versão oficial e atualiza a instalação local com backup e rollback; invocação exclusivamente manual.\n",
        "lista de skills",
    ),
    (
        "checkpoint  proof-map  spec-diff  mutation-evidence  telemetry  status\n",
        "checkpoint  proof-map  spec-diff  mutation-evidence  update-bm  telemetry  status\n",
        "lista de comandos",
    ),
    (
        "Nenhuma instalação ou sincronização é executada automaticamente.\n",
        "Após esta instalação, verifique ou atualize explicitamente com:\n\n"
        "```bash\n"
        "python3 ~/.codex/skills/_shared/scripts/bm.py update-bm --check\n"
        "python3 ~/.codex/skills/_shared/scripts/bm.py update-bm\n"
        "```\n\n"
        "No Claude Code, troque `~/.codex` por `~/.claude`. Também é possível usar `/update-bm`. Nenhuma sincronização ocorre sem invocação explícita.\n",
        "instruções de atualização",
    ),
    ("/homologar-sistema\n```\n", "/homologar-sistema\n/update-bm\n```\n", "uso da skill update-bm"),
):
    replace_once(readme, old, new, label)


changelog = ROOT / "CHANGELOG.md"
replace_once(
    changelog,
    "# Changelog\n\n",
    "# Changelog\n\n"
    "## 3.2.0 - Self Update seguro\n\n"
    "- adiciona `/update-bm` e `bm.py update-bm` com consulta explícita da versão oficial;\n"
    "- atualiza instalações copiadas substituindo somente diretórios gerenciados e preservando skills alheias;\n"
    "- cria backup persistente e executa rollback quando uma substituição falha;\n"
    "- bloqueia archive com path traversal, symlink, arquivo especial, entrada duplicada ou versão divergente;\n"
    "- em checkout Git, exige origem oficial, `main` limpa e fast-forward de `origin/main`;\n"
    "- nunca faz downgrade e oferece `--check` sem alteração de arquivos.\n\n",
    "entrada do changelog",
)


contract = ROOT / "skills/_shared/METHOD_CONTRACT.md"
replace_once(
    contract,
    "## Fontes de verdade e segurança\n",
    "## Atualização do método\n\n"
    "`/update-bm` é exclusivamente manual e executa `bm.py update-bm`. A versão local vive em `_shared/VERSION`; a fonte remota é a `main` oficial. Instalação copiada preserva diretórios alheios, cria backup e substitui somente as skills gerenciadas. Checkout Git exige origem oficial, `main`, árvore limpa e fast-forward. Versão local igual ou superior nunca é substituída. Falha de rede, archive inseguro, divergência de versão ou erro de escrita bloqueia sem declarar atualização.\n\n"
    "## Fontes de verdade e segurança\n",
    "contrato de atualização",
)


final_ci = '''name: CI

on:
  push:
    branches:
      - main
  pull_request:
    branches:
      - main

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.13"

      - name: Validate Python syntax
        run: |
          python3 -m py_compile \
            skills/_shared/scripts/bm.py \
            skills/_shared/scripts/bm_feature_support.py \
            skills/_shared/scripts/bm_context.py \
            skills/_shared/scripts/bm_spec_diff.py \
            skills/_shared/scripts/bm_mutation.py \
            skills/_shared/scripts/bm_update.py \
            tests/test_method_package.py \
            tests/test_context_efficiency.py \
            tests/test_context_efficiency_review.py \
            tests/test_self_update.py

      - name: Run complete sharded suite
        run: python3 scripts/run_test_shards.py

      - name: Validate CLI entrypoints
        run: |
          python3 scripts/bm.py --help > /tmp/bm-help.txt
          grep -q "spec-diff" /tmp/bm-help.txt
          grep -q "mutation-evidence" /tmp/bm-help.txt
          grep -q "update-bm" /tmp/bm-help.txt
          python3 scripts/bm.py proof-map --help | grep -q "mutation-evidence"
          python3 scripts/bm.py update-bm --help | grep -q -- "--check"
          test "$(cat skills/_shared/VERSION)" = "3.2.0"
'''
(ROOT / ".github/workflows/ci.yml").write_text(final_ci, encoding="utf-8")
