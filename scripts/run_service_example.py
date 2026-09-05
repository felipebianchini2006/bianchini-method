#!/usr/bin/env python3
"""Jornada pública reproduzível. --protocol-test usa revisões de fixture declaradas.

Uma execução de aceite usa --review-report com parecer real e hashes das fontes.
Nenhuma transição de estado é forjada. Documentos de produto são autorados;
estado, proofs, reviews, resultados e arquivamento pertencem exclusivamente ao CLI.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/service_requests"
sys.path.insert(0, str(ROOT / "tests"))
from test_method_v04_cli import empty_model, git, init_git, markdown_document, typed_plan, typed_task

IDS = ["FLW-001", "REQ-001", "REQ-002", "REQ-003", "NFR-001", "BR-001", "DAT-001", "ERR-001", "RSK-001"]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def create_scope_pdf(path):
    """PDF de entrada legível em uma página, criado só com a stdlib."""
    lines = (FIXTURE / "scope_input.txt").read_text().splitlines()
    operations = ["BT /F1 11 Tf 15 TL 48 744 Td"]
    for line in lines:
        escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        operations.append(f"({escaped}) Tj T*")
    stream = ("\n".join(operations) + "\nET").encode("ascii")
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>",
               b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
               b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    data, offsets = bytearray(b"%PDF-1.4\n"), [0]
    for identifier, value in enumerate(objects, 1):
        offsets.append(len(data))
        data.extend(f"{identifier} 0 obj\n".encode() + value + b"\nendobj\n")
    xref = len(data)
    data.extend(b"xref\n0 6\n0000000000 65535 f \n")
    for offset in offsets[1:]:
        data.extend(f"{offset:010d} 00000 n \n".encode())
    data.extend(f"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    path.write_bytes(data)


def frontmatter(path):
    return json.loads(path.read_text().split("---", 2)[1])


def run_example(binary, base, review, scope_pdf=None):
    repo = base / "service-requests"
    init_git(repo)
    (repo / ".gitignore").write_text("/.bianchini/.runtime/\n__pycache__/\n")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "initialize service example")
    calls, negatives = [], []

    def cli(*args, reject=None):
        result = subprocess.run([str(binary), *map(str, args)], cwd=repo, capture_output=True, text=True,
                                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        calls.append({"argv": list(map(str, args)), "exit_code": result.returncode, "stderr": result.stderr.strip()})
        if reject:
            assert result.returncode != 0 and reject in result.stderr, (args, result.stdout, result.stderr)
            negatives.append(reject)
            return None
        assert result.returncode == 0, (args, result.stdout, result.stderr)
        return json.loads(result.stdout)

    cli("model", "init", "--repo", repo)
    change = cli("model", "init", "--repo", repo, "--change", "Solicitações de serviço")["change"]
    directory = repo / ".bianchini/changes" / change
    draft = FIXTURE / "scope.md"
    if scope_pdf is None:
        # A textual fixture PDF, no optional packages or external services.
        scope_pdf = base / "scope.pdf"
        create_scope_pdf(scope_pdf)
    cli("scope", "seal", "--repo", repo, "--change", change, "--source", scope_pdf,
        "--draft", draft, "--pages", "1", "--extraction", "native")
    sealed = cli("scope", "verify", "--repo", repo, "--change", change, "--source", scope_pdf)
    assert sealed["verified"] is True
    (directory / "RESEARCH.md").write_text("# Pesquisa\n\nPython e SQLite fornecem CLI e transações locais sem serviço. "
        "Fontes: https://docs.python.org/3/library/sqlite3.html e https://docs.python.org/3/library/argparse.html. "
        "Acessadas em 2026-09-05. Inferência: suficientes para a demonstração sem rede pública.\n")
    (directory / "ARCHITECTURE.md").write_text("# Arquitetura\n\nPython, argparse e SQLite. Uma CLI e um banco local. "
        "Transação por comando e consulta condicionada ao dono ou papel operador. "
        "Identidades sintéticas públicas são apenas fixtures. Sem autenticação de produção. "
        "Escolha: stdlib suficiente, testes por processo e zero serviço operacional. "
        "Go exigiria driver SQLite; servidor web não é requisito. "
        "Premissa: poucos operadores locais. Evolução: autenticação real e servidor quando contratados. "
        "Falha de gravação usa rollback da transação.\n")
    delta = {"contracts": {"add": [{"id": "service_requests"}]}}
    (directory / "SYSTEM_MODEL.md").write_text(markdown_document(empty_model(contracts=[{"id": "service_requests"}]), "Sistema final"))
    task = typed_task("T01", covers=IDS)
    task.update(name="Entregar solicitação persistente e isolada", result="Usuário cria e acompanha; operador atualiza",
                files=["app.py", "test_service.py", "external_gate.py"], risk_seam="service-access")
    task["verify"] = {"kind": "command", "argv": ["python3", "-B", "test_service.py", "ServiceTests.test_owner_isolation"],
                      "cwd": ".", "timeout_seconds": 60, "proves": "isolamento e permissão pela CLI", "cache": "fresh"}
    plan = typed_plan("P01", requirements=IDS, tasks=[task], provides=["service_requests"], model_delta=delta)
    plan.update(result="Solicitações funcionam após reinício com isolamento", execution="grouped", review="plan_gate",
                acceptance=["criar, operar, acompanhar e rejeitar acesso indevido"],
                verifications=["python3 -B test_service.py", "python3 -B external_gate.py"])
    (directory / "plans/P01-services.md").write_text(markdown_document(plan, "Entrega vertical de solicitações"))
    spec_lines = ["# Comportamento técnico observável"]
    descriptions = ["CLI cria, opera e consulta por identidade.", "create retorna id e open.", "Operador lista e atualiza estado.",
                    "get retorna registro do dono.", "Um novo processo lê os dados confirmados.", "Consulta alheia e escrita por usuário são rejeitadas.",
                    "Registro contém id, owner, description e status.", "Entradas inválidas retornam código não zero e JSON.", "Transação local mantém escrita atômica."]
    for identifier, description in zip(IDS, descriptions):
        spec_lines.extend(["", f"## {identifier}: Contrato", "", description])
    (directory / "specs/expected/system.md").write_text("\n".join(spec_lines) + "\n")
    cli("roadmap", "sync", "--repo", repo, "--change", change)
    cli("model", "validate", "--repo", repo, "--change", change)
    checked = cli("coherence", "check", "--repo", repo, "--change", change, "--structural-only")
    semantic = base / "semantic.json"
    semantic.write_text(json.dumps({"prompt": "service-example-v1", "inputs": checked["review_input_digest"],
                                   "sources": review["sources"], "findings": review["findings"]}))
    checked = cli("coherence", "check", "--repo", repo, "--change", change, "--semantic-report", semantic)
    cli("coherence", "approve", "--repo", repo, "--change", change, "--digest", checked["digest"], "--decided-by", "agent:example")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "plan service delivery")
    # New CLI processes reconstruct the same state; no in-memory session is used.
    cli("model", "validate", "--repo", repo)
    cli("roadmap", "next-wave", "--repo", repo, "--change", change)
    for name in ("app.py", "test_service.py", "external_gate.py"):
        shutil.copyfile(FIXTURE / name, repo / name)
    runtime = repo / ".bianchini/.runtime"
    runtime.mkdir(exist_ok=True)
    external = runtime / "service-state"
    external.write_text("up")
    packed = cli("context", "pack", "--repo", repo, "--unit", "C001/P01/T01")
    common = ["--repo", repo, "--change", change, "--plan", "P01"]
    task_args = [*common, "--task", "T01", "--context-pack", repo / packed["path"]]
    verified = cli("verify", "task", *task_args)
    original = (repo / "app.py").read_text()
    (repo / "app.py").write_text(original.replace('role != "operator" and row["owner"] != user', 'False'))
    cli("plan", "complete", *task_args, "--result", "invalid", "--proof", verified["proof_id"], reject="STALE_EVIDENCE")
    cli("verify", "task", *task_args, reject="VERIFICATION_FAILED")
    (repo / "app.py").write_text(original)
    verified = cli("verify", "task", *task_args, "--retry-reason", "restore isolated permission after negative test")
    cli("plan", "complete", *task_args, "--result", "Solicitações isoladas", "--proof", verified["proof_id"])
    integrated = cli("verify", "plan", *common)
    external.write_text("down")
    cli("verify", "plan", *common, reject="VERIFICATION_FAILED")
    delta_path = runtime / "actual-delta.json"
    delta_path.write_text(json.dumps(delta))
    cli("plan", "complete", *common, "--actual-delta", delta_path, "--result", "invalid",
        "--proof", integrated["proof_ids"][0], reject="GATE_COVERAGE")
    external.write_text("up")
    integrated = cli("verify", "plan", *common, "--retry-reason", "restore controlled external fixture")
    proofs = [arg for proof in integrated["proof_ids"] for arg in ("--proof", proof)]
    cli("plan", "complete", *common, "--actual-delta", delta_path, "--result", "invalid", *proofs, reject="REVIEW_REQUIRED")
    reviewed = cli("verify", "review", *common, "--scope", "plan", "--reviewer", review["reviewer"], "--verdict", "approved", *proofs)
    cli("plan", "complete", *common, "--actual-delta", delta_path, "--result", "Todos os aceites verificados", *proofs, "--review", reviewed["review_id"])
    git(repo, "add", ".")
    git(repo, "commit", "-m", "deliver service requests")
    artifact = runtime / "service.pyz"
    with zipfile.ZipFile(artifact, "w") as archive:
        archive.write(repo / "app.py", "__main__.py")
    release = cli("verify", "release", "--repo", repo, "--change", change, "--build", artifact, "--delivery", "ready")
    proofs = [arg for proof in release["proof_ids"] for arg in ("--proof", proof)]
    cli("verify", "review", "--repo", repo, "--change", change, "--scope", "release", "--reviewer", review["reviewer"], "--verdict", "approved", *proofs)
    homologation = {"schema_version": 1, "change": change, "rc": release["candidate"], "fingerprint": release["fingerprint"],
                    "status": "accepted", "blockers": [], "findings": [], "manual_proofs": [],
                    "gates": [{"proof_id": p, "result": "passed"} for p in release["proof_ids"]]}

    def save_homologation(value):
        (directory / "results/HOMOLOGATION.md").write_text(markdown_document(value, "Homologação da CLI real"))
        git(repo, "add", ".bianchini")
        git(repo, "commit", "-m", "record candidate acceptance", "--allow-empty")

    for mutate in ("not_run", "critical", "high"):
        bad = json.loads(json.dumps(homologation))
        if mutate == "not_run":
            bad["gates"][0]["result"] = mutate
        else:
            bad["findings"] = [{"severity": mutate, "status": "open"}]
        save_homologation(bad)
        cli("cycle-close", "--repo", repo, "--change", change, reject="HOMOLOGATION_")
        assert directory.exists() and frontmatter(repo / ".bianchini/STATE.md")["status"] != "completed"
    save_homologation(homologation)
    original_artifact = artifact.read_bytes()
    artifact.write_bytes(original_artifact + b"modified")
    cli("cycle-close", "--repo", repo, "--change", change, reject="ARTIFACT_MISMATCH")
    artifact.write_bytes(original_artifact)
    closed = cli("cycle-close", "--repo", repo, "--change", change)
    assert closed["status"] == "completed"
    # Small direct change, same public runner and real proof.
    quick = cli("direct", "start", "--repo", repo, "--objective", "Melhorar ajuda", "--scope", "texto de ajuda",
                "--acceptance", "CLI e testes preservados", "--verification", "python3 -B test_service.py")
    (repo / "app.py").write_text(original.replace('description="Solicitações de serviço"', 'description="Criar e acompanhar solicitações de serviço"'))
    cli("direct", "checkpoint", "--repo", repo, "--slug", quick["id"], "--checkpoint", "ajuda ajustada",
        "--command", "python3 -B test_service.py", "--next-action", "concluir")
    cli("direct", "finish", "--repo", repo, "--slug", quick["id"], "--status", "completed", "--verification", "proof no checkpoint",
        "--next-action", "idle", "--docviva-kind", "internal", "--docviva-outcome", "not_applicable", "--docviva-justification", "somente descrição da ajuda")
    # Controlled product defect followed by a true RED/GREEN in the same debug.
    good = (repo / "app.py").read_text()
    (repo / "app.py").write_text(good.replace('description = args.description.strip()', 'description = args.description'))
    debug = cli("debug", "start", "--repo", repo, "--objective", "Rejeitar descrição em branco", "--expected", "entrada vazia rejeitada",
                "--actual", "espaços aceitos", "--environment", "local fixture")
    debug_args = ["--repo", repo, "--id", debug["id"]]
    cli("debug", "checkpoint", *debug_args, "--event", "reproduced", "--evidence", "entrada composta por espaços aceita")
    cli("debug", "checkpoint", *debug_args, "--event", "diagnosed", "--evidence", "validação antes da normalização", "--root-cause", "strip removido")
    (repo / "regression.py").write_text("from test_service import ServiceTests\nimport unittest\nclass Regression(ServiceTests):\n"
        "    def test_blank(self):\n        result = self.call('demo-a', 'create', '--description', '   ', ok=False)\n"
        "        self.assertEqual(result['error'], 'invalid_description')\nif __name__ == '__main__': unittest.main()\n")
    command = "python3 -B regression.py Regression.test_blank"
    cli("debug", "checkpoint", *debug_args, "--event", "red", "--evidence", "regressão real", "--command", command,
        "--test-file", "regression.py", "--failure-pattern", "AssertionError")
    cli("debug", "checkpoint", *debug_args, "--event", "fixing", "--evidence", "restaurar normalização")
    (repo / "app.py").write_text(good)
    cli("debug", "resume", *debug_args)
    cli("debug", "checkpoint", *debug_args, "--event", "green", "--evidence", "mesmo teste passa", "--command", command)
    cli("debug", "checkpoint", *debug_args, "--event", "regression_checked", "--evidence", "suíte pública passa",
        "--command", "python3 -B test_service.py", "--neighbor-regression", "permissão e persistência")
    cli("debug", "checkpoint", *debug_args, "--event", "documented", "--evidence", "contrato restaurado", "--residual-risk", "somente ambiente demonstrado")
    cli("debug", "finish", *debug_args, "--docviva-kind", "internal", "--docviva-outcome", "not_applicable",
        "--docviva-justification", "restaura validação contratada, sem mudar comportamento aceito")
    assert frontmatter(repo / ".bianchini/STATE.md")["status"] == "idle"
    result = {"status": "passed", "repository": str(repo), "change": change, "quick": quick["id"], "debug": debug["id"],
              "reviewer": review["reviewer"], "negative_rejections": negatives, "public_calls": calls,
              "candidate": release["candidate"], "scope_pdf_sha256": digest(scope_pdf)}
    (base / "journey-result.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--directory", type=Path, help="diretório de evidências vazio, criado com mktemp -d")
    parser.add_argument("--scope-pdf", type=Path)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--review-report", type=Path)
    source.add_argument("--protocol-test", action="store_true")
    args = parser.parse_args()
    if args.protocol_test:
        review = {"reviewer": "fixture:protocol-test-not-independent", "sources": ["versioned test fixture"], "findings": []}
    else:
        review = json.loads(args.review_report.read_text())
        assert review["findings"] == [], "resolva findings antes do aceite"
        assert args.scope_pdf and digest(args.scope_pdf) == review["scope_pdf_sha256"], "PDF ausente ou diferente do parecer"
        for name in ("app.py", "test_service.py", "scope.md"):
            assert review["fixture_sha256"][name] == digest(FIXTURE / name), "parecer obsoleto"
    if args.directory:
        result = run_example(args.binary.resolve(), args.directory.resolve(), review, args.scope_pdf)
    else:
        with tempfile.TemporaryDirectory(prefix="bm-service-example-", dir=ROOT.parent) as temp:
            result = run_example(args.binary.resolve(), Path(temp), review, args.scope_pdf)
    print(json.dumps({key: value for key, value in result.items() if key != "public_calls"}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
