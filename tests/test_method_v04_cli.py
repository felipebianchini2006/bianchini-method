"""Cenários integrados do contrato Bianchini Method 0.4."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "bm.py"


def cli(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(CLI), *args],
        cwd=cwd or ROOT,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        text=True,
        capture_output=True,
        check=False,
    )


def cli_json(*args: str, cwd: Path | None = None) -> dict[str, object]:
    completed = cli(*args, cwd=cwd)
    if completed.returncode != 0:
        raise AssertionError(
            f"CLI falhou ({completed.returncode}): {completed.stderr}\n{completed.stdout}"
        )
    return json.loads(completed.stdout)


def git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=root, text=True, capture_output=True, check=False
    )
    if completed.returncode != 0:
        raise AssertionError(completed.stderr)
    return completed.stdout.strip()


def init_git(root: Path) -> None:
    root.mkdir(parents=True)
    git(root, "init", "-b", "main")
    git(root, "config", "user.name", "BM Test")
    git(root, "config", "user.email", "test@example.invalid")
    (root / ".gitignore").write_text("/.bianchini/.runtime/\n", encoding="utf-8")


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    if not root.exists():
        return digest.hexdigest()
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode())
        if path.is_file() and not path.is_symlink():
            digest.update(path.read_bytes())
    return digest.hexdigest()


def markdown_document(frontmatter: dict[str, object], title: str) -> str:
    return (
        "---\n"
        + json.dumps(frontmatter, ensure_ascii=False, sort_keys=True, indent=2)
        + f"\n---\n\n# {title}\n"
    )


def empty_model(**sections: object) -> dict[str, object]:
    model: dict[str, object] = {
        "schema_version": 1,
        "modules": [],
        "interfaces": [],
        "capabilities": [],
        "contracts": [],
        "ownership": [],
        "data": [],
        "integrations": [],
        "journeys": [],
        "invariants": [],
        "effects": [],
    }
    model.update(sections)
    return model


def write_text_pdf(path: Path, pages: list[str]) -> None:
    """Gera um PDF textual pequeno sem depender de biblioteca externa."""

    objects: list[bytes] = []
    page_ids = [3 + index * 2 for index in range(len(pages))]
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects.append(
        f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode()
    )
    for index, content in enumerate(pages):
        page_id = page_ids[index]
        stream_id = page_id + 1
        objects.append(
            (
                "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Resources << /Font << /F1 {2 + len(pages) * 2 + 1} 0 R >> >> "
                f"/Contents {stream_id} 0 R >>"
            ).encode()
        )
        escaped = content.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream = f"BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET".encode()
        objects.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    data = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for identifier, value in enumerate(objects, start=1):
        offsets.append(len(data))
        data.extend(f"{identifier} 0 obj\n".encode())
        data.extend(value)
        data.extend(b"\nendobj\n")
    xref = len(data)
    data.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    data.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        data.extend(f"{offset:010d} 00000 n \n".encode())
    data.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref}\n%%EOF\n"
        ).encode()
    )
    path.write_bytes(data)


def detailed_scope_body(*, unsourced: bool = False, blocked: bool = False) -> str:
    source = "" if unsourced else "- Fonte: PDF p. 1\n"
    blockers = "- Definir quem pode cancelar uma solicitação.\n" if blocked else "Nenhuma.\n"
    return f"""# Escopo — Portal de solicitações

## Objetivo

Permitir que clientes registrem e acompanhem solicitações de suporte.

## Resultados esperados

- Solicitação registrada com identificador público.
- Histórico de estados consultável pelo cliente responsável.

## Atores e perfis

### ACT-001 — Cliente
- Responsabilidade: registrar e consultar as próprias solicitações.
{source}
## Fluxos

### FLW-001 — Registrar solicitação
- Ator: Cliente autenticado.
- Gatilho: envio do formulário de suporte.
- Pré-condições: cliente possui sessão válida.
- Caminho principal: informar assunto e descrição; confirmar envio.
- Resultado: solicitação criada no estado recebida e identificador exibido.
- Falhas: assunto vazio é recusado sem criar registro.
{source}
## Requisitos funcionais

### REQ-001 — Registrar solicitação
- Origem: explícito.
{source}- Aceite:
  - GIVEN cliente autenticado e assunto preenchido.
  - WHEN confirmar o envio.
  - THEN criar uma solicitação no estado recebida e exibir seu identificador.

## Requisitos não funcionais

Não especificado no PDF.

## Regras de negócio

### BR-001 — Isolamento por cliente
- Regra: cliente consulta somente solicitações criadas por sua conta.
{source}
## Dados e estados

### DAT-001 — Solicitação
- Campos: identificador, cliente, assunto, descrição, estado e datas.
- Estados: recebida, em atendimento e concluída.
{source}
## Integrações e efeitos externos

Não aplicável: o PDF não exige integração externa.

## Critérios gerais de aceite

- O cliente conclui o FLW-001 sem acessar dados de outra conta.
- Entrada inválida não cria uma solicitação parcial.

## Comportamentos de erro

### ERR-001 — Assunto ausente
- Condição: assunto vazio no envio.
- Resposta: recusar a entrada e preservar o formulário.
{source}
## Riscos e casos para o planejamento

### RSK-001 — Concorrência de atualização
- Avaliar: impedir perda de estado quando dois operadores atualizarem a mesma solicitação.
- Efeito no escopo: risco para análise; não adiciona requisito funcional.
{source}
## Dentro do escopo

- Cadastro de solicitação.
- Consulta das próprias solicitações.
- Transição entre os três estados declarados.

## Fora do escopo

- Chat em tempo real.
- Integração com mensageria externa.

## Decisões consolidadas

Nenhuma.

## Questões abertas

Nenhuma.

## Decisões bloqueantes

{blockers}
## Contradições

Nenhuma.

## Proveniência e cobertura

- Páginas processadas: 1-2 de 2.
"""


class MethodV04Scenarios(unittest.TestCase):
    def test_first_quick_initializes_v04_without_legacy_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            init_git(repo)
            planning = repo / ".planning"
            planning.mkdir()
            (planning / "foreign.md").write_text("não tocar\n", encoding="utf-8")
            planning_before = tree_digest(planning)

            started = cli_json(
                "direct",
                "start",
                "--repo",
                str(repo),
                "--objective",
                "Ajustar parser",
                "--scope",
                "uma alteração localizada",
                "--acceptance",
                "parser aceita entrada válida",
                "--verification",
                "test_parser",
                "--scope-score",
                "0",
            )

            self.assertRegex(str(started["id"]), r"^Q001-")
            self.assertTrue((repo / ".bianchini/STATE.md").is_file())
            self.assertTrue((repo / f".bianchini/quick/{started['id']}/BRIEF.md").is_file())
            self.assertFalse((repo / ".superpowers").exists())
            self.assertFalse((repo / "docs/living").exists())
            self.assertEqual(tree_digest(planning), planning_before)

    def test_first_debug_initializes_v04_without_legacy_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            init_git(repo)

            started = cli_json(
                "debug",
                "start",
                "--repo",
                str(repo),
                "--objective",
                "Corrigir cálculo",
                "--expected",
                "total 10",
                "--actual",
                "total 11",
                "--environment",
                "teste local",
            )

            self.assertRegex(str(started["id"]), r"^D001-")
            self.assertTrue((repo / ".bianchini/STATE.md").is_file())
            self.assertTrue(
                (repo / f".bianchini/debug/active/{started['id']}.md").is_file()
            )
            self.assertFalse((repo / ".superpowers").exists())
            self.assertFalse((repo / "docs/living").exists())

    def test_invalid_first_work_does_not_leave_partial_workspace(self) -> None:
        attempts = (
            (
                "direct",
                "start",
                "--objective",
                "Entrada incompleta",
                "--scope",
                "local",
            ),
            (
                "debug",
                "start",
                "--objective",
                "Debug incompleto",
                "--expected",
                "A",
                "--actual",
                "B",
            ),
        )
        for command in attempts:
            with self.subTest(command=command[0]), tempfile.TemporaryDirectory() as temp:
                repo = Path(temp) / "repo"
                init_git(repo)
                result = cli(*command, "--repo", str(repo))
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse((repo / ".bianchini").exists())
                self.assertFalse((repo / ".superpowers").exists())

    def test_first_execution_requires_explicit_migration_for_old_bianchini_docs(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            init_git(repo)
            legacy = repo / "docs/living"
            legacy.mkdir(parents=True)
            (legacy / "PROJECT_STATE.md").write_text(
                "# Bianchini Method\nstatus: idle\n", encoding="utf-8"
            )
            before = tree_digest(repo / "docs")

            quick = cli(
                "direct",
                "start",
                "--repo",
                str(repo),
                "--objective",
                "Ajustar parser",
                "--scope",
                "local",
                "--acceptance",
                "funciona",
                "--verification",
                "test_parser",
            )
            debug = cli(
                "debug",
                "start",
                "--repo",
                str(repo),
                "--objective",
                "Corrigir parser",
                "--expected",
                "válido",
                "--actual",
                "inválido",
                "--environment",
                "teste",
            )
            workspace = cli(
                "workspace",
                "create",
                "--repo",
                str(repo),
                "--change",
                "C001",
                "--plan",
                "P01",
            )
            close = cli(
                "cycle-close",
                "--repo",
                str(repo),
                "--change",
                "C001",
            )

            self.assertNotEqual(quick.returncode, 0)
            self.assertNotEqual(debug.returncode, 0)
            self.assertNotEqual(workspace.returncode, 0)
            self.assertNotEqual(close.returncode, 0)
            for result in (quick, debug, workspace, close):
                self.assertIn("MIGRATION_REQUIRED", result.stderr)
            self.assertFalse((repo / ".bianchini").exists())
            self.assertFalse((repo / ".superpowers").exists())
            self.assertEqual(tree_digest(repo / "docs"), before)

    def test_every_recognized_legacy_source_blocks_first_work(self) -> None:
        cases = (
            ("docs-bianchini", "docs/bianchini/old.md", "old\n"),
            ("artifacts", "artifacts/bianchini/result.json", "{}\n"),
            ("direct", ".superpowers/bianchini/direct/Q001/BRIEF.md", "old\n"),
            (
                "design",
                "docs/design/C001/DESIGN_MANIFEST.json",
                json.dumps({"schema_version": 1, "status": "approved"}),
            ),
        )
        for name, relative, content in cases:
            with self.subTest(source=name), tempfile.TemporaryDirectory() as temp:
                repo = Path(temp) / "repo"
                init_git(repo)
                source = repo / relative
                source.parent.mkdir(parents=True)
                source.write_text(content, encoding="utf-8")
                result = cli(
                    "direct",
                    "start",
                    "--repo",
                    str(repo),
                    "--objective",
                    "Teste de migração",
                    "--scope",
                    "local",
                    "--acceptance",
                    "funciona",
                    "--verification",
                    "test",
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("MIGRATION_REQUIRED", result.stderr)
                self.assertFalse((repo / ".bianchini").exists())

        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            init_git(repo)
            foreign = repo / "docs/design/foreign/notes.md"
            foreign.parent.mkdir(parents=True)
            foreign.write_text("não é Bianchini\n", encoding="utf-8")
            started = cli_json(
                "direct",
                "start",
                "--repo",
                str(repo),
                "--objective",
                "Design estrangeiro",
                "--scope",
                "local",
                "--acceptance",
                "funciona",
                "--verification",
                "test",
            )
            self.assertRegex(str(started["id"]), r"^Q001-")
            self.assertEqual(foreign.read_text(encoding="utf-8"), "não é Bianchini\n")

    def test_legacy_fallback_arguments_are_not_public_in_v04(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            init_git(repo)
            state = repo / "legacy-state.json"
            state.write_text('{"method_version":2}', encoding="utf-8")

            commands = (
                (
                    "direct",
                    "start",
                    "--repo",
                    str(repo),
                    "--objective",
                    "teste",
                    "--scope",
                    "local",
                    "--acceptance",
                    "ok",
                    "--verification",
                    "test",
                    "--current-state",
                    "legado",
                ),
                (
                    "workspace",
                    "create",
                    "--repo",
                    str(repo),
                    "--plan",
                    "P01",
                    "--planning-version",
                    "v2",
                    "--state",
                    str(state),
                ),
                (
                    "cycle-close",
                    "--repo",
                    str(repo),
                    "--state",
                    str(state),
                    "--root",
                    str(repo),
                ),
            )
            for command in commands:
                with self.subTest(command=command[0]):
                    result = cli(*command)
                    self.assertEqual(result.returncode, 2)
                    self.assertIn("usage: bm", result.stderr)

            self.assertFalse((repo / ".bianchini").exists())
            self.assertFalse((repo / ".superpowers").exists())
            self.assertFalse((repo / "docs/living").exists())

    def test_legacy_adapter_commands_are_not_public(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            init_git(repo)
            commands = (
                ("route", "--repo", str(repo), "--new-project"),
                ("legacy-transition", "--repo", str(repo)),
                ("repo-hygiene", "check", "--repo", str(repo)),
            )
            for command in commands:
                with self.subTest(command=command[0]):
                    result = cli(*command)
                    self.assertEqual(result.returncode, 2)
                    self.assertIn("invalid choice", result.stderr)
            self.assertFalse((repo / ".bianchini").exists())
            self.assertFalse((repo / ".superpowers").exists())
            self.assertFalse((repo / "docs/living").exists())

    def test_clean_installed_package_starts_only_v04_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            installed = base / "installed"
            shutil.copytree(ROOT / "skills", installed / "skills")
            installed_cli = installed / "skills/_shared/scripts/bm.py"
            repo = base / "repo"
            init_git(repo)

            completed = subprocess.run(
                [
                    "python3",
                    str(installed_cli),
                    "direct",
                    "start",
                    "--repo",
                    str(repo),
                    "--objective",
                    "Smoke instalado",
                    "--scope",
                    "local",
                    "--acceptance",
                    "workspace criado",
                    "--verification",
                    "smoke",
                ],
                cwd=repo,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            result = json.loads(completed.stdout)
            self.assertRegex(result["id"], r"^Q001-")
            self.assertEqual(
                (installed / "skills/_shared/VERSION").read_text(encoding="utf-8").strip(),
                "0.4.5",
            )
            self.assertTrue((repo / ".bianchini/STATE.md").is_file())
            self.assertFalse((repo / ".superpowers").exists())
            self.assertFalse((repo / "docs/living").exists())

    def test_model_init_creates_only_bianchini_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            init_git(repo)
            planning = repo / ".planning"
            planning.mkdir()
            (planning / "keep.md").write_text("foreign\n", encoding="utf-8")
            before = tree_digest(planning)

            result = cli_json("model", "init", "--repo", str(repo))

            self.assertEqual(result["method"], "0.4")
            self.assertEqual(result["status"], "idle")
            self.assertTrue((repo / ".bianchini/STATE.md").is_file())
            self.assertTrue((repo / ".bianchini/current/SYSTEM_MODEL.md").is_file())
            self.assertTrue((repo / ".bianchini/current/ARCHITECTURE.md").is_file())
            self.assertLess((repo / ".bianchini/STATE.md").stat().st_size, 65536)
            self.assertEqual(tree_digest(planning), before)
            self.assertFalse((repo / "docs/living/PROJECT_STATE.md").exists())

            valid = cli_json("model", "validate", "--repo", str(repo))
            self.assertTrue(valid["valid"])
            self.assertEqual(valid["method"], "0.4")

    def test_change_model_coherence_and_impact_are_integrated(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            init_git(repo)
            cli_json("model", "init", "--repo", str(repo))
            change = cli_json(
                "model", "init", "--repo", str(repo), "--change", "checkout"
            )
            change_id = str(change["change"])
            self.assertRegex(change_id, r"^C001-checkout$")
            change_root = repo / ".bianchini/changes" / change_id
            self.assertTrue((change_root / "SYSTEM_MODEL.md").is_file())

            target = empty_model(
                contracts=[{"id": "payment_created"}, {"id": "order_paid"}]
            )
            (change_root / "SYSTEM_MODEL.md").write_text(
                markdown_document(target, "Sistema final"), encoding="utf-8"
            )
            plans = [
                {
                    "id": "P01",
                    "provides": ["payment_created"],
                    "acceptance": ["pagamento persistido"],
                    "verifications": ["test_payment"],
                    "model_delta": {
                        "contracts": {"add": [{"id": "payment_created"}]}
                    },
                },
                {
                    "id": "P02",
                    "depends_on": ["P01"],
                    "consumes": ["payment_created"],
                    "provides": ["order_paid"],
                    "acceptance": ["pedido atualizado"],
                    "verifications": ["test_order"],
                    "model_delta": {
                        "contracts": {"add": [{"id": "order_paid"}]}
                    },
                },
            ]
            for plan in plans:
                (change_root / "plans" / f"{plan['id']}.md").write_text(
                    markdown_document(plan, str(plan["id"])), encoding="utf-8"
                )

            coherent = cli_json(
                "coherence",
                "check",
                "--repo",
                str(repo),
                "--change",
                change_id,
                "--structural-only",
            )
            self.assertEqual(coherent["status"], "structurally_valid")
            self.assertEqual(coherent["findings"], [])
            self.assertTrue((change_root / "COHERENCE.md").is_file())

            impact = cli_json(
                "impact",
                "analyze",
                "--repo",
                str(repo),
                "--change",
                change_id,
                "--plan",
                "P01",
                "--changed-contract",
                "payment_created",
            )
            self.assertEqual(impact["radius"], "direct")
            self.assertEqual(impact["direct_plans"], ["P02"])
            self.assertEqual(impact["stale_plans"], ["P02"])
            self.assertTrue(impact["preview"])
            coherence_text = (change_root / "COHERENCE.md").read_text(encoding="utf-8")
            self.assertIn("Impact Radius", coherence_text)
            coherence_header = json.loads(coherence_text.split("---", 2)[1])
            self.assertEqual(coherence_header["stale_plans"], [])

    def test_semantic_error_is_normalized_to_warning_and_needs_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            init_git(repo)
            cli_json("model", "init", "--repo", str(repo))
            change_id = str(
                cli_json("model", "init", "--repo", str(repo), "--change", "simple")[
                    "change"
                ]
            )
            change_root = repo / ".bianchini/changes" / change_id
            plan = {
                "id": "P01",
                "acceptance": ["entrega"],
                "verifications": ["test"],
            }
            (change_root / "plans/P01.md").write_text(
                markdown_document(plan, "P01"), encoding="utf-8"
            )
            report = repo / "semantic.json"
            report.write_text(
                json.dumps(
                    {
                        "prompt": "revise",
                        "inputs": "digest-bound",
                        "sources": ["official"],
                        "findings": [
                            {
                                "code": "SPECULATIVE_ABSTRACTION",
                                "severity": "ERROR",
                                "evidence": "módulo sem consumidor",
                                "expected_fix": "remover ou justificar",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            checked = cli_json(
                "coherence",
                "check",
                "--repo",
                str(repo),
                "--change",
                change_id,
                "--semantic-report",
                str(report),
            )
            self.assertEqual(checked["status"], "changes_required")
            semantic = [
                item for item in checked["findings"] if item["origin"] == "semantic"
            ]
            self.assertEqual(semantic[0]["severity"], "WARNING")
            self.assertEqual(semantic[0]["status"], "open")

    def test_post_approval_impact_preserves_digest_and_only_blocks_stale_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            repo = base / "repo"
            init_git(repo)
            cli_json("model", "init", "--repo", str(repo))
            change_id = str(
                cli_json("model", "init", "--repo", str(repo), "--change", "impact")[
                    "change"
                ]
            )
            change_root = repo / ".bianchini/changes" / change_id
            target_model = empty_model(
                contracts=[{"id": "shared_contract"}, {"id": "independent_contract"}]
            )
            (change_root / "SYSTEM_MODEL.md").write_text(
                markdown_document(target_model, "Sistema final"), encoding="utf-8"
            )
            plans = [
                {
                    "id": "P01",
                    "provides": ["shared_contract"],
                    "acceptance": ["provider pronto"],
                    "verifications": ["test_provider"],
                    "model_delta": {
                        "contracts": {"add": [{"id": "shared_contract"}]}
                    },
                },
                {
                    "id": "P02",
                    "depends_on": ["P01"],
                    "consumes": ["shared_contract"],
                    "acceptance": ["consumer pronto"],
                    "verifications": ["test_consumer"],
                },
                {
                    "id": "P03",
                    "provides": ["independent_contract"],
                    "acceptance": ["fluxo independente pronto"],
                    "verifications": ["test_independent"],
                    "model_delta": {
                        "contracts": {"add": [{"id": "independent_contract"}]}
                    },
                },
            ]
            for plan in plans:
                (change_root / "plans" / f"{plan['id']}.md").write_text(
                    markdown_document(plan, str(plan["id"])), encoding="utf-8"
                )
            report = base / "semantic.json"
            report.write_text(
                json.dumps(
                    {
                        "prompt": "revisar impacto",
                        "inputs": "pacote global",
                        "sources": ["official"],
                        "findings": [],
                    }
                ),
                encoding="utf-8",
            )
            checked = cli_json(
                "coherence",
                "check",
                "--repo",
                str(repo),
                "--change",
                change_id,
                "--semantic-report",
                str(report),
            )
            approved_digest = str(checked["digest"])
            cli_json(
                "coherence",
                "approve",
                "--repo",
                str(repo),
                "--change",
                change_id,
                "--digest",
                approved_digest,
                "--approved-by",
                "human:test",
            )

            impact = cli_json(
                "impact",
                "analyze",
                "--repo",
                str(repo),
                "--change",
                change_id,
                "--plan",
                "P01",
                "--changed-contract",
                "shared_contract",
            )
            self.assertFalse(impact["preview"])
            self.assertEqual(impact["stale_plans"], ["P02"])
            coherence_header = json.loads(
                (change_root / "COHERENCE.md").read_text(encoding="utf-8").split("---", 2)[1]
            )
            self.assertEqual(coherence_header["status"], "approved_with_stale")
            self.assertEqual(coherence_header["digest"], approved_digest)
            self.assertEqual(coherence_header["approval"]["digest"], approved_digest)

            git(repo, "add", ".")
            git(repo, "commit", "-m", "approve selective impact")
            unaffected = cli_json(
                "workspace",
                "create",
                "--repo",
                str(repo),
                "--change",
                change_id,
                "--plan",
                "P03",
                "--target",
                str(base / "worktree-p03"),
            )
            self.assertEqual(unaffected["plan"], "P03")
            blocked = cli(
                "workspace",
                "create",
                "--repo",
                str(repo),
                "--change",
                change_id,
                "--plan",
                "P02",
                "--target",
                str(base / "worktree-p02"),
            )
            self.assertNotEqual(blocked.returncode, 0)
            self.assertIn("IMPACT_STALE", blocked.stderr)

    def test_execution_workspace_uses_change_and_plan_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            repo = base / "repo"
            target = base / "worktree"
            init_git(repo)
            cli_json("model", "init", "--repo", str(repo))
            change_id = str(
                cli_json("model", "init", "--repo", str(repo), "--change", "checkout")[
                    "change"
                ]
            )
            change_root = repo / ".bianchini/changes" / change_id
            plan = {
                "id": "P01",
                "acceptance": ["entrega"],
                "verifications": ["test"],
            }
            (change_root / "plans/P01.md").write_text(
                markdown_document(plan, "P01"), encoding="utf-8"
            )
            structural = cli_json(
                "coherence",
                "check",
                "--repo",
                str(repo),
                "--change",
                change_id,
                "--structural-only",
            )
            self.assertEqual(structural["status"], "structurally_valid")
            premature = cli(
                "coherence",
                "approve",
                "--repo",
                str(repo),
                "--change",
                change_id,
                "--digest",
                str(structural["digest"]),
                "--approved-by",
                "human:test",
            )
            self.assertNotEqual(premature.returncode, 0)
            self.assertIn("WARNING_UNRESOLVED", premature.stderr)

            report = repo / "semantic.json"
            report.write_text(
                json.dumps(
                    {
                        "prompt": "revisão arquitetural",
                        "inputs": "pacote global",
                        "sources": ["official"],
                        "findings": [],
                    }
                ),
                encoding="utf-8",
            )
            coherent = cli_json(
                "coherence",
                "check",
                "--repo",
                str(repo),
                "--change",
                change_id,
                "--semantic-report",
                str(report),
            )
            self.assertEqual(coherent["status"], "ready_for_approval")
            approved = cli_json(
                "coherence",
                "approve",
                "--repo",
                str(repo),
                "--change",
                change_id,
                "--digest",
                str(coherent["digest"]),
                "--approved-by",
                "human:test",
            )
            self.assertEqual(approved["status"], "approved")
            git(repo, "add", ".")
            git(repo, "commit", "-m", "approve change")

            nested = cli(
                "workspace",
                "create",
                "--repo",
                str(repo),
                "--change",
                "C001",
                "--plan",
                "P01",
                "--target",
                str(repo / "nested-worktree"),
            )
            self.assertNotEqual(nested.returncode, 0)
            self.assertIn("fora do repo", nested.stderr)

            created = cli_json(
                "workspace",
                "create",
                "--repo",
                str(repo),
                "--change",
                "C001",
                "--plan",
                "P01",
                "--target",
                str(target),
            )
            self.assertEqual(created["branch"], "bm/c001-p01")
            self.assertEqual(Path(str(created["workspace"])), target.resolve())
            self.assertTrue(target.is_dir())

            located = cli_json(
                "workspace",
                "resume",
                "--repo",
                str(repo),
                "--change",
                "C001",
                "--plan",
                "P01",
            )
            self.assertEqual(Path(str(located["workspace"])), target.resolve())
            checked = cli_json("workspace", "check", "--repo", str(target))
            self.assertTrue(checked["valid"])

    def test_plan_result_promotes_final_model_and_archives_cycle(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            repo = base / "repo"
            init_git(repo)
            cli_json("model", "init", "--repo", str(repo))
            change_id = str(
                cli_json("model", "init", "--repo", str(repo), "--change", "billing")[
                    "change"
                ]
            )
            change_root = repo / ".bianchini/changes" / change_id
            delta = {"contracts": {"add": [{"id": "invoice_created"}]}}
            (change_root / "SYSTEM_MODEL.md").write_text(
                markdown_document(
                    empty_model(contracts=[{"id": "invoice_created"}]),
                    "Sistema final",
                ),
                encoding="utf-8",
            )
            (change_root / "plans/P01.md").write_text(
                markdown_document(
                    {
                        "id": "P01",
                        "provides": ["invoice_created"],
                        "acceptance": ["fatura persistida"],
                        "verifications": ["test_invoice"],
                        "model_delta": delta,
                    },
                    "P01",
                ),
                encoding="utf-8",
            )
            report = base / "semantic.json"
            report.write_text(
                json.dumps(
                    {
                        "prompt": "revisar",
                        "inputs": "pacote",
                        "sources": ["official"],
                        "findings": [],
                    }
                ),
                encoding="utf-8",
            )
            checked = cli_json(
                "coherence",
                "check",
                "--repo",
                str(repo),
                "--change",
                change_id,
                "--semantic-report",
                str(report),
            )
            cli_json(
                "coherence",
                "approve",
                "--repo",
                str(repo),
                "--change",
                change_id,
                "--digest",
                str(checked["digest"]),
                "--approved-by",
                "human:test",
            )
            actual_delta = base / "actual-delta.json"
            actual_delta.write_text(json.dumps(delta), encoding="utf-8")
            completed = cli_json(
                "plan",
                "complete",
                "--repo",
                str(repo),
                "--change",
                change_id,
                "--plan",
                "P01",
                "--actual-delta",
                str(actual_delta),
                "--result",
                "Fatura entregue conforme contrato",
                "--verification",
                "test_invoice passou",
            )
            self.assertEqual(completed["status"], "completed")
            self.assertTrue((change_root / "results/P01.md").is_file())
            git(repo, "add", ".")
            git(repo, "commit", "-m", "complete billing plan")

            closed = cli_json(
                "cycle-close", "--repo", str(repo), "--change", change_id
            )

            self.assertEqual(closed["status"], "completed")
            self.assertFalse(change_root.exists())
            self.assertTrue((repo / ".bianchini/archive" / change_id / "SUMMARY.md").is_file())
            current = json.loads(
                (repo / ".bianchini/current/SYSTEM_MODEL.md")
                .read_text(encoding="utf-8")
                .split("---", 2)[1]
            )
            self.assertEqual(current["contracts"], [{"id": "invoice_created"}])
            state_text = (repo / ".bianchini/STATE.md").read_text(encoding="utf-8")
            self.assertIn('"status":"idle"', state_text)

    def test_direct_risk_classification_is_deterministic(self) -> None:
        normal = cli_json(
            "direct",
            "classify",
            "--scope-score",
            "1",
            "--external-effect-score",
            "0",
            "--migration-score",
            "0",
            "--concurrency-score",
            "0",
            "--money-score",
            "0",
        )
        protected = cli_json(
            "direct",
            "classify",
            "--scope-score",
            "1",
            "--external-effect-score",
            "2",
            "--migration-score",
            "0",
            "--concurrency-score",
            "1",
            "--money-score",
            "2",
        )
        critical = cli_json(
            "direct",
            "classify",
            "--scope-score",
            "1",
            "--external-effect-score",
            "2",
            "--migration-score",
            "2",
            "--concurrency-score",
            "1",
            "--money-score",
            "2",
            "--destructive-migration",
        )

        self.assertEqual((normal["score"], normal["route"]), (1, "normal"))
        self.assertEqual((protected["score"], protected["route"]), (6, "protected"))
        self.assertEqual(critical["route"], "protected")
        self.assertIn("destructive_migration", critical["overrides"])

        boundaries = (
            ((0, 1, 0, 0, 1), (2, "normal")),
            ((0, 1, 1, 0, 1), (3, "protected")),
            ((0, 2, 1, 1, 2), (6, "protected")),
            ((1, 2, 1, 1, 2), (7, "protected")),
        )
        for scores, expected in boundaries:
            arguments = ["direct", "classify"]
            for name, value in zip(
                ("scope", "external-effect", "migration", "concurrency", "money"),
                scores,
            ):
                arguments.extend([f"--{name}-score", str(value)])
            with self.subTest(boundary=expected[0]):
                result = cli_json(*arguments)
                self.assertEqual((result["score"], result["route"]), expected)

        for dimension in ("scope", "migration", "concurrency"):
            scores = {
                "scope": "0",
                "external-effect": "0",
                "migration": "0",
                "concurrency": "0",
                "money": "0",
            }
            scores[dimension] = "2"
            arguments = ["direct", "classify"]
            for name, value in scores.items():
                arguments.extend([f"--{name}-score", value])
            with self.subTest(automatic_override=dimension):
                classified = cli_json(*arguments)
                self.assertEqual(classified["route"], "protected")
                self.assertTrue(classified["overrides"])

    def test_critical_direct_work_stays_active_without_planning_redirect(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            init_git(repo)

            started = cli_json(
                "direct",
                "start",
                "--repo",
                str(repo),
                "--objective",
                "Executar migração concorrente com webhook",
                "--scope",
                "Entrega crítica já decidida e rastreada",
                "--acceptance",
                "Migração e webhook funcionam com segurança",
                "--verification",
                "pytest tests/integration.py",
                "--scope-score",
                "2",
                "--external-effect-score",
                "2",
                "--migration-score",
                "2",
                "--concurrency-score",
                "2",
                "--money-score",
                "2",
                "--destructive-migration",
                "--uncontrolled-concurrency",
                "--webhook-flow",
            )

            quick_id = str(started["id"])
            self.assertEqual(started["status"], "active")
            self.assertEqual(started["risk"]["route"], "protected")
            self.assertFalse((repo / f".bianchini/quick/{quick_id}/RESULT.md").exists())
            state = (repo / ".bianchini/STATE.md").read_text(encoding="utf-8")
            self.assertIn(quick_id, state)
            self.assertNotIn("sdd-planning", state)

    def test_direct_finish_rejects_escalated_status(self) -> None:
        result = cli("direct", "finish", "--status", "escalated")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("invalid choice", result.stderr)

    def test_protected_quick_persists_and_requires_production_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            init_git(repo)
            cli_json("model", "init", "--repo", str(repo))
            git(repo, "add", ".bianchini", ".gitignore")
            git(repo, "commit", "-m", "init method")
            started = cli_json(
                "direct",
                "start",
                "--repo",
                str(repo),
                "--objective",
                "Integrar pagamento e confirmação externa",
                "--scope",
                "Uma entrega vertical de checkout",
                "--acceptance",
                "Pagamento confirmado uma única vez",
                "--verification",
                "pytest tests/payment_contract.py",
                "--scope-score",
                "1",
                "--external-effect-score",
                "2",
                "--concurrency-score",
                "1",
                "--money-score",
                "2",
                "--payment-flow",
                "--webhook-flow",
                "--guard",
                "official_docs",
                "--guard",
                "timeout_recovery",
                "--guard",
                "source_of_truth",
                "--guard",
                "idempotency",
                "--guard",
                "reconciliation",
                "--guard",
                "rollback",
                "--guard",
                "sandbox",
                "--guard",
                "deduplication",
                "--guard",
                "replay_order",
                "--guard",
                "persistence",
                "--guard",
                "local_contract",
                "--guard",
                "authenticity",
            )
            quick_id = str(started["id"])
            self.assertEqual(started["risk"]["route"], "protected")
            self.assertTrue((repo / f".bianchini/quick/{quick_id}/BRIEF.md").is_file())

            checkpoint = cli_json(
                "direct",
                "checkpoint",
                "--repo",
                str(repo),
                "--slug",
                quick_id,
                "--checkpoint",
                "Contrato implementado em sandbox",
                "--next-action",
                "Validar efeito real",
                "--changed-file",
                "src/payment.py",
                "--command",
                "pytest tests/payment_contract.py",
                "--evidence",
                "sandbox passou",
            )
            self.assertEqual(checkpoint["status"], "active")

            changed_after_checkpoint = repo / "changed-after-checkpoint.py"
            changed_after_checkpoint.write_text("changed = True\n", encoding="utf-8")
            stale = cli(
                "direct",
                "finish",
                "--repo",
                str(repo),
                "--slug",
                quick_id,
                "--status",
                "completed",
                "--next-action",
                "Concluído",
                "--behavior",
                "Pagamento idempotente",
                "--verification",
                "sandbox passou",
                "--production-authorized",
            )
            self.assertNotEqual(stale.returncode, 0)
            self.assertIn("STALE_EVIDENCE", stale.stderr)
            changed_after_checkpoint.unlink()

            blocked = cli(
                "direct",
                "finish",
                "--repo",
                str(repo),
                "--slug",
                quick_id,
                "--status",
                "completed",
                "--next-action",
                "Concluído",
                "--behavior",
                "Pagamento idempotente",
                "--verification",
                "sandbox passou",
            )
            self.assertNotEqual(blocked.returncode, 0)
            self.assertIn("EXTERNAL_AUTHORITY_REQUIRED", blocked.stderr)

            finished = cli_json(
                "direct",
                "finish",
                "--repo",
                str(repo),
                "--slug",
                quick_id,
                "--status",
                "completed",
                "--next-action",
                "Concluído",
                "--behavior",
                "Pagamento idempotente",
                "--verification",
                "sandbox passou",
                "--production-authorized",
            )
            self.assertEqual(finished["status"], "completed")
            self.assertTrue((repo / f".bianchini/quick/{quick_id}/RESULT.md").is_file())

    def test_webhook_quick_cannot_finish_without_authenticity_guard(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            init_git(repo)
            cli_json("model", "init", "--repo", str(repo))
            started = cli_json(
                "direct",
                "start",
                "--repo",
                str(repo),
                "--objective",
                "Receber confirmação de webhook em sandbox",
                "--scope",
                "Uma entrega vertical",
                "--acceptance",
                "Evento autêntico processado uma vez",
                "--verification",
                "teste de contrato",
                "--scope-score",
                "1",
                "--external-effect-score",
                "1",
                "--concurrency-score",
                "1",
                "--webhook-flow",
                *[
                    value
                    for guard in (
                        "official_docs",
                        "timeout_recovery",
                        "rollback",
                        "sandbox",
                        "idempotency",
                        "deduplication",
                        "replay_order",
                        "persistence",
                        "local_contract",
                    )
                    for value in ("--guard", guard)
                ],
            )
            quick_id = str(started["id"])
            self.assertEqual(started["missing_guards"], ["authenticity"])
            cli_json(
                "direct",
                "checkpoint",
                "--repo",
                str(repo),
                "--slug",
                quick_id,
                "--checkpoint",
                "Sandbox executado",
                "--next-action",
                "Completar guard",
                "--evidence",
                "contrato passou",
            )
            blocked = cli(
                "direct",
                "finish",
                "--repo",
                str(repo),
                "--slug",
                quick_id,
                "--status",
                "completed",
                "--next-action",
                "Concluído",
                "--behavior",
                "Webhook processado",
                "--verification",
                "sandbox passou",
            )
            self.assertNotEqual(blocked.returncode, 0)
            self.assertIn("MISSING_GUARD", blocked.stderr)

    def test_debug_persists_red_green_and_rejects_wrong_order(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            init_git(repo)
            cli_json("model", "init", "--repo", str(repo))
            started = cli_json(
                "debug",
                "start",
                "--repo",
                str(repo),
                "--objective",
                "Eliminar processamento duplicado do webhook",
                "--expected",
                "Evento duplicado não altera o estado novamente",
                "--actual",
                "Evento duplicado cria uma segunda transição",
                "--environment",
                "pytest local",
            )
            debug_id = str(started["id"])
            self.assertRegex(debug_id, r"^D001-")

            premature = cli(
                "debug",
                "checkpoint",
                "--repo",
                str(repo),
                "--id",
                debug_id,
                "--event",
                "green",
                "--evidence",
                "teste passou",
            )
            self.assertNotEqual(premature.returncode, 0)
            self.assertIn("ORDER_VIOLATION", premature.stderr)

            for event in ("reproduced", "diagnosed", "red", "fixing"):
                extra: list[str] = []
                if event == "diagnosed":
                    extra = [
                        "--hypothesis",
                        "deduplicação ausente",
                        "--experiment",
                        "repetir provider_event_id",
                        "--eliminated-hypothesis",
                        "retry de rede isolado",
                        "--root-cause",
                        "provider_event_id não era persistido como chave única",
                    ]
                checkpoint = cli_json(
                    "debug",
                    "checkpoint",
                    "--repo",
                    str(repo),
                    "--id",
                    debug_id,
                    "--event",
                    event,
                    "--evidence",
                    f"evidência {event}",
                    *extra,
                )
                self.assertEqual(checkpoint["stage"], event)

            stale_green = cli(
                "debug",
                "checkpoint",
                "--repo",
                str(repo),
                "--id",
                debug_id,
                "--event",
                "green",
                "--evidence",
                "teste sem patch",
            )
            self.assertNotEqual(stale_green.returncode, 0)
            self.assertIn("STALE_EVIDENCE", stale_green.stderr)
            (repo / "fix.py").write_text("DEDUPLICATION = True\n", encoding="utf-8")
            green = cli_json(
                "debug",
                "checkpoint",
                "--repo",
                str(repo),
                "--id",
                debug_id,
                "--event",
                "green",
                "--evidence",
                "regressão focal passou no patch",
            )
            self.assertEqual(green["stage"], "green")
            regression = cli_json(
                "debug",
                "checkpoint",
                "--repo",
                str(repo),
                "--id",
                debug_id,
                "--event",
                "regression_checked",
                "--evidence",
                "fluxos vizinhos passaram",
                "--neighbor-regression",
                "webhook válido continua atualizando o pedido",
            )
            self.assertEqual(regression["stage"], "regression_checked")
            documented = cli_json(
                "debug",
                "checkpoint",
                "--repo",
                str(repo),
                "--id",
                debug_id,
                "--event",
                "documented",
                "--evidence",
                "causa e contrato registrados",
                "--residual-risk",
                "nenhum risco conhecido no escopo testado",
            )
            self.assertEqual(documented["stage"], "documented")

            finished = cli_json(
                "debug", "finish", "--repo", str(repo), "--id", debug_id
            )
            self.assertEqual(finished["status"], "resolved")
            self.assertFalse((repo / f".bianchini/debug/active/{debug_id}.md").exists())
            self.assertTrue((repo / f".bianchini/debug/resolved/{debug_id}.md").is_file())

    def test_migration_is_explicit_and_never_touches_planning(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            init_git(repo)
            (repo / "docs/living").mkdir(parents=True)
            (repo / "docs/bianchini/current/specs").mkdir(parents=True)
            (repo / "artifacts/bianchini/C001").mkdir(parents=True)
            (repo / "docs/design/foreign").mkdir(parents=True)
            (repo / "docs/design/C001").mkdir(parents=True)
            (repo / ".planning").mkdir()
            (repo / "docs/living/PROJECT_STATE.md").write_text(
                json.dumps({"planning_status": "idle", "next_action": "aguardar"}),
                encoding="utf-8",
            )
            (repo / "docs/bianchini/current/specs/system.md").write_text(
                "# Sistema\n", encoding="utf-8"
            )
            (repo / "artifacts/bianchini/C001/result.json").write_text(
                "{}\n", encoding="utf-8"
            )
            (repo / "docs/design/foreign/notes.md").write_text(
                "not bianchini\n", encoding="utf-8"
            )
            (repo / "docs/design/C001/DESIGN_MANIFEST.json").write_text(
                json.dumps({"schema_version": 1, "status": "approved"}),
                encoding="utf-8",
            )
            (repo / "docs/design/C001/prototype.html").write_text(
                "<main>approved</main>\n", encoding="utf-8"
            )
            (repo / ".planning/foreign.md").write_text("foreign\n", encoding="utf-8")
            planning_before = tree_digest(repo / ".planning")
            git(repo, "add", ".")
            git(repo, "commit", "-m", "legacy docs")

            checked = cli_json("migrate", "check", "--repo", str(repo))
            self.assertTrue(checked["eligible"])
            self.assertGreater(len(checked["entries"]), 0)
            self.assertFalse(
                any(".planning" in json.dumps(item) for item in checked["entries"])
            )

            applied = cli_json("migrate", "apply", "--repo", str(repo))
            self.assertEqual(applied["status"], "migrated")
            self.assertTrue((repo / ".bianchini/STATE.md").is_file())
            self.assertTrue((repo / ".bianchini/current/specs/system.md").is_file())
            self.assertTrue(list((repo / ".bianchini/archive").glob("import-*/MANIFEST.md")))
            self.assertFalse((repo / "docs/living/PROJECT_STATE.md").exists())
            self.assertTrue((repo / "docs/design/foreign/notes.md").is_file())
            self.assertFalse((repo / "docs/design/C001/prototype.html").exists())
            self.assertEqual(tree_digest(repo / ".planning"), planning_before)

    def test_version_files_use_zero_four_lineage(self) -> None:
        self.assertEqual(
            (ROOT / "skills/_shared/VERSION").read_text(encoding="utf-8").strip(),
            "0.4.5",
        )
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn('test "$(cat skills/_shared/VERSION)" = "0.4.5"', workflow)
        root_schema = (ROOT / "schemas/state-v04.schema.json").read_bytes()
        packaged_schema = (
            ROOT / "skills/_shared/schemas/state-v04.schema.json"
        ).read_bytes()
        self.assertEqual(root_schema, packaged_schema)
        schema = json.loads(root_schema)
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(schema["properties"]["method"]["const"], "0.4")
        for forbidden in ("history", "ledger", "events", "results", "timeline"):
            self.assertNotIn(forbidden, schema["properties"])


class ScopeIntakeScenarios(unittest.TestCase):
    def prepare_change(self, root: Path) -> tuple[Path, str, Path]:
        repo = root / "repo"
        init_git(repo)
        planning = repo / ".planning"
        planning.mkdir()
        (planning / "foreign.md").write_text("não tocar\n", encoding="utf-8")
        cli_json("model", "init", "--repo", str(repo))
        change = cli_json(
            "model", "init", "--repo", str(repo), "--change", "portal suporte"
        )
        source = root / "escopo-cliente.pdf"
        write_text_pdf(source, ["Portal de suporte", "Regras e aceite"])
        return repo, str(change["change"]), source

    def test_scope_seal_creates_verified_scope_and_preserves_foreign_planning(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo, change, source = self.prepare_change(root)
            planning_before = tree_digest(repo / ".planning")
            draft = root / "scope-draft.md"
            draft.write_text(detailed_scope_body(), encoding="utf-8")

            sealed = cli_json(
                "scope",
                "seal",
                "--repo",
                str(repo),
                "--change",
                change,
                "--source",
                str(source),
                "--draft",
                str(draft),
                "--pages",
                "2",
                "--extraction",
                "native",
            )

            self.assertEqual(sealed["status"], "ready_for_sdd")
            self.assertEqual(sealed["change"], change)
            self.assertEqual(sealed["coverage"]["unsourced_items"], 0)
            self.assertEqual(sealed["coverage"]["blocking_decisions"], 0)
            self.assertRegex(str(sealed["scope_digest"]), r"^[0-9a-f]{64}$")
            scope = repo / f".bianchini/changes/{change}/SCOPE.md"
            content = scope.read_text(encoding="utf-8")
            self.assertIn('"document": "bianchini-scope"', content)
            self.assertIn('"status": "ready_for_sdd"', content)
            self.assertIn("### REQ-001", content)
            self.assertIn("- Itens sem fonte: 0", content)
            self.assertNotIn(str(source.parent), content)

            verified = cli_json(
                "scope",
                "verify",
                "--repo",
                str(repo),
                "--change",
                change,
                "--source",
                str(source),
            )
            self.assertEqual(verified["scope_digest"], sealed["scope_digest"])
            state = (repo / ".bianchini/STATE.md").read_text(encoding="utf-8")
            self.assertIn('"status":"scope_ready"', state)
            self.assertIn('"current_unit":"scope"', state)
            self.assertIn(f'"id":"{change}"', state)
            self.assertIn(f".bianchini/changes/{change}/SCOPE.md", state)
            self.assertEqual(tree_digest(repo / ".planning"), planning_before)

    def test_scope_seal_rejects_unsourced_requirement_without_overwriting_scope(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo, change, source = self.prepare_change(root)
            scope = repo / f".bianchini/changes/{change}/SCOPE.md"
            before = scope.read_bytes()
            draft = root / "scope-draft.md"
            draft.write_text(detailed_scope_body(unsourced=True), encoding="utf-8")

            rejected = cli(
                "scope",
                "seal",
                "--repo",
                str(repo),
                "--change",
                change,
                "--source",
                str(source),
                "--draft",
                str(draft),
                "--pages",
                "2",
                "--extraction",
                "native",
            )

            self.assertEqual(rejected.returncode, 3)
            self.assertIn("item sem fonte", rejected.stderr)
            self.assertEqual(scope.read_bytes(), before)
            self.assertNotIn(
                '"status":"scope_ready"',
                (repo / ".bianchini/STATE.md").read_text(encoding="utf-8"),
            )

    def test_scope_seal_rejects_open_decision_and_vague_placeholder(self) -> None:
        cases = (
            (detailed_scope_body(blocked=True), "decisão bloqueante"),
            (detailed_scope_body().replace("Chat em tempo real.", "TBD."), "placeholder"),
            (
                detailed_scope_body().replace("Fonte: PDF p. 1", "Fonte: PDF p. 1 e memória", 1),
                "fonte deve ser",
            ),
            (
                detailed_scope_body().replace("### ACT-001", "### REQ-002", 1),
                "seção incorreta",
            ),
            (
                detailed_scope_body().replace("PDF p. 1", "PDF p. 3", 1),
                "página 3 fora do PDF",
            ),
        )
        for body, expected in cases:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                repo, change, source = self.prepare_change(root)
                draft = root / "scope-draft.md"
                draft.write_text(body, encoding="utf-8")
                rejected = cli(
                    "scope",
                    "seal",
                    "--repo",
                    str(repo),
                    "--change",
                    change,
                    "--source",
                    str(source),
                    "--draft",
                    str(draft),
                    "--pages",
                    "2",
                    "--extraction",
                    "native",
                )
                self.assertEqual(rejected.returncode, 3)
                self.assertIn(expected, rejected.stderr)

    def test_scope_verify_detects_tampering_and_different_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo, change, source = self.prepare_change(root)
            draft = root / "scope-draft.md"
            draft.write_text(detailed_scope_body(), encoding="utf-8")
            sealed = cli_json(
                "scope",
                "seal",
                "--repo",
                str(repo),
                "--change",
                change,
                "--source",
                str(source),
                "--draft",
                str(draft),
                "--pages",
                "2",
                "--extraction",
                "mixed",
            )
            other = root / "outro.pdf"
            write_text_pdf(other, ["Outro documento", "Outro aceite"])
            wrong_source = cli(
                "scope",
                "verify",
                "--repo",
                str(repo),
                "--change",
                change,
                "--source",
                str(other),
            )
            self.assertEqual(wrong_source.returncode, 3)
            self.assertIn("fonte PDF diverge", wrong_source.stderr)

            state_path = repo / ".bianchini/STATE.md"
            original_state = state_path.read_text(encoding="utf-8")
            state_path.write_text(
                original_state.replace(str(sealed["scope_digest"]), "0" * 64),
                encoding="utf-8",
            )
            stale_state = cli(
                "scope", "verify", "--repo", str(repo), "--change", change
            )
            self.assertEqual(stale_state.returncode, 3)
            self.assertIn("STATE.md diverge", stale_state.stderr)
            state_path.write_text(original_state, encoding="utf-8")

            scope = repo / f".bianchini/changes/{change}/SCOPE.md"
            scope.write_text(
                scope.read_text(encoding="utf-8").replace(
                    "Chat em tempo real.", "Chat em tempo real e voz."
                ),
                encoding="utf-8",
            )
            tampered = cli(
                "scope", "verify", "--repo", str(repo), "--change", change
            )
            self.assertEqual(tampered.returncode, 3)
            self.assertIn("digest do SCOPE.md diverge", tampered.stderr)

            planning = cli(
                "model", "validate", "--repo", str(repo), "--change", change
            )
            self.assertEqual(planning.returncode, 3)
            self.assertIn("STALE_EVIDENCE", planning.stderr)
            self.assertIn("SCOPE_STALE", planning.stderr)


if __name__ == "__main__":
    unittest.main()
