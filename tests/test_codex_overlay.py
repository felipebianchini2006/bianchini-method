"""Contratos sintéticos exclusivos do overlay Codex."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OVERLAY = ROOT / "codex" / "skills" / "executar-plano-codex"
GUARD = OVERLAY / "scripts" / "review_guard.py"
INSTALLER = ROOT / "codex" / "install.sh"
BASE_POLICY = ROOT / "codex" / "skills" / "executar-plano" / "agents" / "openai.yaml"


def run_guard(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(GUARD), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )


def result_json(result: subprocess.CompletedProcess[str]) -> dict[str, object]:
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    value = json.loads(result.stdout)
    if not isinstance(value, dict):
        raise AssertionError("saída não é objeto")
    return value


def git(repo: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo, text=True, capture_output=True, check=False
    )
    if check and result.returncode != 0:
        raise AssertionError(result.stderr)
    return result.stdout.strip()


def init_repo(root: Path) -> str:
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "-b", "main")
    git(root, "config", "user.name", "Codex Overlay Test")
    git(root, "config", "user.email", "codex@example.invalid")
    (root / "app.txt").write_text("alpha\nstable\nremove-me\n", encoding="utf-8")
    git(root, "add", "app.txt")
    git(root, "commit", "-m", "base")
    return git(root, "rev-parse", "HEAD")


def commit_file(repo: Path, content: str, message: str, path: str = "app.txt") -> str:
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    git(repo, "add", "--", path)
    git(repo, "commit", "-m", message)
    return git(repo, "rev-parse", "HEAD")


def write_json(path: Path, value: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return path


def write_task_brief(repo: Path, unit: str, identity: str) -> Path:
    path = repo / f"synthetic/task-brief-{unit}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"# Task Brief {unit}\n\n- Unit `{unit}` SHA-256: `{identity}`\n\n"
        "REQ-1: comportamento aprovado da unidade sintética.\n",
        encoding="utf-8",
    )
    return path


def run_proof(
    repo: Path,
    unit: str,
    command: list[str],
    *,
    commit: str | None = None,
    cwd: str = ".",
    timeout: float = 5,
) -> dict[str, object]:
    value = result_json(
        run_guard(
            "proof",
            "--root",
            str(repo),
            "--planning-version",
            "v1",
            "--plan",
            "P01",
            "--unit",
            unit,
            "--commit",
            commit or git(repo, "rev-parse", "HEAD"),
            "--cwd",
            cwd,
            "--timeout",
            str(timeout),
            "--",
            *command,
        )
    )
    return value


def default_blocker_command() -> list[str]:
    return [
        "python3",
        "-c",
        "from pathlib import Path; raise SystemExit(0 if 'resolved-marker' in Path('app.txt').read_text() else 1)",
    ]


def initial_blocker(
    finding_id: str = "B1", *, structural: bool = False, seam: str = "api"
) -> dict[str, object]:
    return {
        "id": finding_id,
        "severity": "important",
        "disposition": "blocker",
        "title": f"Blocker {finding_id}",
        "approved_requirement": "REQ-1",
        "root_cause": f"root-{finding_id}",
        "material_impact": "requisito aprovado falha",
        "reachable_scenario": "entrada pública válida",
        "risk_seam": seam,
        "structural": structural,
        "structural_class": "state_machine" if structural else None,
        "structural_evidence": "AUTO" if structural else None,
        "_test_command": default_blocker_command(),
    }


def hardening(finding_id: str = "H1") -> dict[str, object]:
    return {
        "id": finding_id,
        "severity": "minor",
        "disposition": "hardening",
        "title": f"Hardening {finding_id}",
    }


def delta_finding(
    base: str,
    head: str,
    *,
    finding_id: str = "R1",
    file: str = "app.txt",
    line: int = 2,
    change_kind: str = "modified",
    base_exit_code: int = 0,
    head_exit_code: int = 1,
    structural: bool = False,
    seam: str = "api",
    command: list[str] | None = None,
) -> dict[str, object]:
    return {
        "id": finding_id,
        "source": "delta_regression",
        "severity": "important",
        "disposition": "blocker",
        "title": f"Regression {finding_id}",
        "approved_requirement": "REQ-1",
        "material_impact": "regressão material",
        "reachable_scenario": "entrada pública válida",
        "delta_base": base,
        "delta_head": head,
        "file": file,
        "line": line,
        "change_kind": change_kind,
        "_test_command": command
        or (
            ["python3", "-c", "raise SystemExit(1)"]
            if base_exit_code != 0 and head_exit_code != 0
            else ["python3", "-c", "raise SystemExit(0)"]
            if base_exit_code == 0 and head_exit_code == 0
            else ["AUTO_DELTA"]
        ),
        "causal_explanation": "a linha alterada muda diretamente o resultado",
        "risk_seam": seam,
        "structural": structural,
        "structural_class": "state_machine" if structural else None,
        "structural_evidence": "AUTO" if structural else None,
    }


def frozen_open(finding_id: str = "B1") -> dict[str, object]:
    return {"id": finding_id, "source": "frozen", "resolution": "open"}


def frozen_resolved(finding_id: str = "B1") -> dict[str, object]:
    return {
        "id": finding_id,
        "source": "frozen",
        "resolution": "resolved",
        "_auto_resolution_proof": True,
    }


def freeze(
    repo: Path,
    findings: list[dict[str, object]] | None = None,
    *,
    unit: str = "U1",
    seam: str = "api",
    head: str | None = None,
    identity: str | None = None,
) -> tuple[Path, dict[str, object]]:
    review_head = head or git(repo, "rev-parse", "HEAD")
    unit_identity_value = (
        identity or hashlib.sha256(f"unit:{unit}".encode()).hexdigest()
    )
    task_brief = write_task_brief(repo, unit, unit_identity_value)
    prepared = json.loads(
        json.dumps(findings if findings is not None else [initial_blocker(seam=seam)])
    )
    for finding in prepared:
        if finding.get("disposition") != "blocker" or finding.get("proof_id"):
            continue
        command = finding.pop("_test_command", default_blocker_command())
        if "reproduction" in finding:
            continue
        proof = run_proof(repo, unit, command, commit=review_head)
        finding["proof_id"] = proof["proof_id"]
        if finding.get("structural_evidence") == "AUTO":
            finding["structural_evidence"] = proof["proof_id"]
    findings_path = write_json(
        repo / "synthetic/findings.json",
        {"findings": prepared},
    )
    result = run_guard(
        "freeze",
        "--root",
        str(repo),
        "--planning-version",
        "v1",
        "--plan",
        "P01",
        "--unit",
        unit,
        "--unit-identity",
        unit_identity_value,
        "--task-brief",
        str(task_brief),
        "--seam",
        seam,
        "--review-head",
        review_head,
        "--findings",
        str(findings_path),
        "--required-gate",
        "unit-tests",
    )
    value = result_json(result)
    sidecar = repo / f"artifacts/bianchini/v1/codex/convergence/P01/{unit}.json"
    return sidecar, value


def start_fix(sidecar: Path, blocker: str = "B1") -> dict[str, object]:
    return result_json(
        run_guard(
            "fix",
            "--sidecar",
            str(sidecar),
            "--blocker",
            blocker,
            "--summary",
            "correção sintética",
        )
    )


def submit_delta(sidecar: Path, kind: str, base: str, head: str) -> dict[str, object]:
    return result_json(
        run_guard(
            "submit-delta",
            "--sidecar",
            str(sidecar),
            "--kind",
            kind,
            "--base",
            base,
            "--head",
            head,
        )
    )


def review(
    sidecar: Path, repo: Path, findings: list[dict[str, object]]
) -> dict[str, object]:
    prepared = json.loads(json.dumps(findings))
    state = json.loads(sidecar.read_text(encoding="utf-8"))
    unit = state["unit_id"]
    store = repo / f"artifacts/bianchini/v1/codex/convergence/P01/.proofs/{unit}.json"
    store_value = (
        json.loads(store.read_text(encoding="utf-8"))
        if store.exists()
        else {"proofs": {}}
    )
    for finding in prepared:
        if finding.get("source") == "delta_regression" and not finding.get(
            "base_proof_id"
        ):
            command = finding.pop("_test_command")
            if command == ["AUTO_DELTA"]:
                base_content = (
                    git(repo, "show", f"{finding['delta_base']}:app.txt") + "\n"
                )
                command = [
                    "python3",
                    "-c",
                    "from pathlib import Path; "
                    f"expected={base_content!r}; path=Path('app.txt'); "
                    "raise SystemExit(0 if path.exists() and path.read_text() == expected else 1)",
                ]
            base_proof = run_proof(repo, unit, command, commit=finding["delta_base"])
            head_proof = run_proof(repo, unit, command, commit=finding["delta_head"])
            finding["base_proof_id"] = base_proof["proof_id"]
            finding["head_proof_id"] = head_proof["proof_id"]
            if finding.get("structural_evidence") == "AUTO":
                finding["structural_evidence"] = head_proof["proof_id"]
        if finding.pop("_auto_resolution_proof", False):
            blocker = state["blockers"][finding["id"]]
            origin_id = blocker.get("head_proof_id") or blocker.get("proof_id")
            origin = store_value["proofs"][origin_id]
            proof = run_proof(repo, unit, origin["command"], cwd=origin["cwd"])
            finding["proof_id"] = proof["proof_id"]
    path = write_json(repo / "synthetic/review.json", {"findings": prepared})
    return result_json(
        run_guard("review", "--sidecar", str(sidecar), "--findings", str(path))
    )


def fix_review_cycle(
    repo: Path, sidecar: Path, index: int, *, resolve: bool = False
) -> dict[str, object]:
    start_fix(sidecar)
    base = git(repo, "rev-parse", "HEAD")
    current = (repo / "app.txt").read_text(encoding="utf-8")
    suffix = "resolved-marker\n" if resolve else f"fix-{index}\n"
    head = commit_file(repo, current + suffix, f"fix {index}")
    submit_delta(sidecar, "fix", base, head)
    return review(sidecar, repo, [frozen_resolved() if resolve else frozen_open()])


def record_gate(repo: Path, sidecar: Path) -> dict[str, object]:
    unit = json.loads(sidecar.read_text(encoding="utf-8"))["unit_id"]
    proof = run_proof(repo, unit, ["python3", "-c", "raise SystemExit(0)"])
    return result_json(
        run_guard(
            "gate",
            "--sidecar",
            str(sidecar),
            "--gate",
            "unit-tests",
            "--proof-id",
            str(proof["proof_id"]),
        )
    )


def stop_evidence(kind: str, proof_id: str) -> dict[str, object]:
    if kind == "essential_external_credential":
        return {
            "service": "synthetic-service",
            "missing_credential": "SYNTHETIC_TOKEN",
            "blocked_operation": "contract test",
            "local_alternative_proof": proof_id,
        }
    if kind == "destructive_action":
        return {
            "action": "drop synthetic dataset",
            "target": "temporary fixture",
            "irreversible_effect": "fixture seria perdida",
            "safe_alternative_proof": proof_id,
        }
    if kind == "new_cost":
        return {
            "provider": "Synthetic Cloud",
            "operation": "isolated test run",
            "estimate": 1.5,
            "currency": "BRL",
            "indispensability_proof": proof_id,
        }
    if kind == "material_change":
        return {
            "approved_requirement": "REQ-1",
            "change_kind": "public_contract",
            "current_contract": "entrada aceita conforme brief congelado",
            "required_change": "alterar a entrada pública aprovada",
            "execution_blocker": "a unidade não pode cumprir ambos os contratos",
            "evidence_proof_id": proof_id,
        }
    return {
        "invariant": "gate exige plataforma ausente",
        "attempts": [{"proof_id": proof_id}],
        "safe_workaround_absence_proof": proof_id,
    }


class CodexOverlayPackageTests(unittest.TestCase):
    def test_overlay_loads_only_three_allowed_references(self) -> None:
        skill = (OVERLAY / "SKILL.md").read_text(encoding="utf-8")
        for name in (
            "EXECUTION_CORE_CODEX.md",
            "CODEX_CONVERGENCE.md",
            "plan-reviewer-codex.md",
        ):
            self.assertIn(name, skill)
            self.assertTrue((OVERLAY / "references" / name).is_file())
        self.assertNotIn("skills/executar-plano/SKILL.md", skill)
        self.assertNotIn("Leia integralmente o executor base", skill)

    def test_core_excludes_convergence_and_stop_rules(self) -> None:
        core = (OVERLAY / "references/EXECUTION_CORE_CODEX.md").read_text(
            encoding="utf-8"
        )
        folded = core.casefold()
        for included in (
            "Preflight",
            "Rota",
            "Aprovação",
            "Worktree",
            "Implementação",
            "Commits",
            "Checkpoints",
            "Gates",
            "Release",
            "Homologação",
            "Entrega",
        ):
            self.assertIn(included.casefold(), folded)
        for excluded in ("Fix loop", "Breaker", "Redesign", "Paradas"):
            self.assertNotIn(excluded.casefold(), folded)

    def test_core_does_not_pin_subagent_models_or_hierarchy(self) -> None:
        core = (OVERLAY / "references/EXECUTION_CORE_CODEX.md").read_text(
            encoding="utf-8"
        )
        skill = (OVERLAY / "SKILL.md").read_text(encoding="utf-8")
        convergence = (OVERLAY / "references/CODEX_CONVERGENCE.md").read_text(
            encoding="utf-8"
        )
        combined = "\n".join((core, skill, convergence))
        for pinned in (
            "/root/luna_max",
            "/root/sol_medium",
            "gpt-5.6-luna",
            "gpt-5.6-sol",
            "reasoning effort `max`",
            "reasoning effort `medium`",
            "Orquestração obrigatória de subagentes",
        ):
            self.assertNotIn(pinned, combined)
        self.assertIn("Quando o host suportar subagentes", core)
        self.assertIn("Não fixar nome, modelo, reasoning effort", core)
        self.assertIn("Sem subagentes, cumprir a mesma responsabilidade inline", core)
        self.assertIn(
            "todo trabalho restante estiver terminal ou estacionado", convergence
        )
        policy = (OVERLAY / "agents/openai.yaml").read_text(encoding="utf-8")
        for unsupported in ("model:", "reasoning_effort:", "subagents:", "agents:"):
            self.assertNotIn(unsupported, policy)

    def test_codex_core_bounds_test_depth_without_reintroducing_overengineering(
        self,
    ) -> None:
        core = (OVERLAY / "references/EXECUTION_CORE_CODEX.md").read_text(
            encoding="utf-8"
        )
        for expected in (
            "não executar E2E completo, regressão completa ou mutação por unidade",
            "não cria unidade, dispatch, revisor ou subagente",
            "uma execução seletiva por seam de risco",
            "score global",
            "hardening adiado",
        ):
            self.assertIn(expected, core)
        self.assertIn("verification.fast", core)
        self.assertIn("verification.plan", core)
        self.assertIn("verification.release", core)

    def test_codex_preserves_frozen_plan_and_autonomy_envelope(self) -> None:
        core = (OVERLAY / "references/EXECUTION_CORE_CODEX.md").read_text(
            encoding="utf-8"
        )
        convergence = (OVERLAY / "references/CODEX_CONVERGENCE.md").read_text(
            encoding="utf-8"
        )
        reviewer = (OVERLAY / "references/plan-reviewer-codex.md").read_text(
            encoding="utf-8"
        )
        skill = (OVERLAY / "SKILL.md").read_text(encoding="utf-8")
        for expected in (
            "implementation_detail",
            "bounded_amendment",
            "material_change",
            "bm change-policy",
            "plano aprovado permanece congelado",
            "opção reversível de menor risco",
            "USER_ACTIONS.md",
            "cycle-close",
        ):
            self.assertIn(expected, core)
        self.assertIn("material_change", convergence)
        self.assertIn("não autoriza nova decomposição", convergence)
        self.assertIn("mudança material comprovada", reviewer)
        self.assertIn("cinco categorias de parada", skill)

    def test_overlay_uses_current_native_cli_surfaces(self) -> None:
        skill = (OVERLAY / "SKILL.md").read_text(encoding="utf-8")
        core = (OVERLAY / "references/EXECUTION_CORE_CODEX.md").read_text(
            encoding="utf-8"
        )
        convergence = (OVERLAY / "references/CODEX_CONVERGENCE.md").read_text(
            encoding="utf-8"
        )
        reviewer = (OVERLAY / "references/plan-reviewer-codex.md").read_text(
            encoding="utf-8"
        )
        combined = "\n".join((skill, core, convergence, reviewer))
        self.assertIn("../_shared/bin/bm", skill)
        self.assertNotIn("bm.py", combined)
        for retired in ("bm route", "bm repo-hygiene", "bm legacy-transition"):
            self.assertNotIn(retired, combined)
        for retired_flag in ("--planning-version", "--state"):
            self.assertNotIn(retired_flag, core)
        self.assertIn("bm workspace create --repo <repo> --change <change_id>", core)
        self.assertIn("bm review-package --cwd <workspace>", convergence)
        for required in ("--brief <task-brief.md>", "--report <report.md>", "--output <review-package.md>"):
            self.assertIn(required, convergence)

    def test_codex_activation_policy_is_explicit_and_base_implicit_is_disabled(
        self,
    ) -> None:
        overlay_policy = (OVERLAY / "agents/openai.yaml").read_text(encoding="utf-8")
        base_policy = BASE_POLICY.read_text(encoding="utf-8")
        skill = (OVERLAY / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("allow_implicit_invocation: false", overlay_policy)
        self.assertIn("allow_implicit_invocation: false", base_policy)
        self.assertIn("$executar-plano-codex all", skill)
        self.assertIn("name: executar-plano-codex", skill)

    def test_base_cli_and_schemas_remain_unmodified_by_overlay(self) -> None:
        wrapper = (ROOT / "scripts/bm.py").read_text(encoding="utf-8")
        oracle = (ROOT / "scripts/bm_python_oracle.py").read_text(encoding="utf-8")
        packaged = (ROOT / "skills/_shared/scripts/bm.py").read_text(encoding="utf-8")
        self.assertIn("os.execv", wrapper)
        self.assertNotIn("runpy.run_path", wrapper)
        self.assertIn("runpy.run_path", oracle)
        self.assertNotIn("review_guard", wrapper)
        self.assertNotIn("review_guard", oracle)
        self.assertNotIn("review_guard", packaged)
        self.assertEqual(
            (ROOT / "schemas/project-state.schema.json").read_bytes(),
            (ROOT / "skills/_shared/schemas/project-state.schema.json").read_bytes(),
        )


class ReviewGuardScenarios(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        spec = importlib.util.spec_from_file_location("review_guard_tested", GUARD)
        if spec is None or spec.loader is None:
            raise AssertionError("review_guard não carregável")
        cls.guard = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.guard)

    def test_transition_table_accepts_every_valid_and_rejects_every_invalid_edge(
        self,
    ) -> None:
        actions = {
            "submit_delta",
            "fix",
            "redesign",
            "park",
            "complete",
            "stop",
            "review",
        }
        for source, mapping in self.guard.TRANSITIONS.items():
            for action, targets in mapping.items():
                for target in targets:
                    state = {"phase": source, "events": [], "updated_at": ""}
                    self.guard.transition(state, action, target)
                    self.assertEqual(state["phase"], target)
            for action in actions:
                for target in self.guard.PHASES:
                    if target in mapping.get(action, set()):
                        continue
                    state = {"phase": source, "events": [], "updated_at": ""}
                    with self.assertRaises(self.guard.GuardError):
                        self.guard.transition(state, action, target)

    def test_proof_executes_real_argv_and_green_result_cannot_be_spoofed_red(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            init_repo(repo)
            proof = run_proof(
                repo,
                "U1",
                [
                    "python3",
                    "-c",
                    "import sys; print('out'); print('err', file=sys.stderr); raise SystemExit(0)",
                ],
            )
            record = proof["proof"]
            self.assertEqual(record["exit_code"], 0)
            self.assertEqual(record["commit"], git(repo, "rev-parse", "HEAD"))
            self.assertRegex(record["stdout_sha256"], r"^[0-9a-f]{64}$")
            self.assertRegex(record["stderr_sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(
                record["stdout_sha256"], hashlib.sha256(b"out\n").hexdigest()
            )
            self.assertEqual(
                record["stderr_sha256"], hashlib.sha256(b"err\n").hexdigest()
            )
            self.assertRegex(record["signature"], r"^[0-9a-f]{64}$")
            self.assertNotIn("stdout", record)
            self.assertNotIn("stderr", record)

            candidate = initial_blocker()
            candidate.pop("_test_command")
            candidate["proof_id"] = proof["proof_id"]
            sidecar, frozen = freeze(repo, [candidate])
            self.assertEqual(frozen["next_action"], "approve")
            self.assertEqual(frozen["state"]["blockers"], {})
            self.assertIn(
                "proof real está verde",
                frozen["state"]["deferred_hardening"][0]["deferred_reason"],
            )

            gate = result_json(
                run_guard(
                    "gate",
                    "--sidecar",
                    str(sidecar),
                    "--gate",
                    "unit-tests",
                    "--proof-id",
                    str(proof["proof_id"]),
                )
            )
            self.assertEqual(gate["state"]["gates"]["unit-tests"]["status"], "passed")
            green_u2 = run_proof(repo, "U2", ["python3", "-c", "raise SystemExit(0)"])
            forged = initial_blocker()
            forged.pop("_test_command")
            forged["proof_id"] = green_u2["proof_id"]
            forged["exit_code"] = 1
            with self.assertRaises(AssertionError) as forged_error:
                freeze(repo, [forged], unit="U2")
            self.assertIn("evidência manual proibida", str(forged_error.exception))
            spoof = run_guard(
                "gate",
                "--sidecar",
                str(sidecar),
                "--gate",
                "unit-tests",
                "--status",
                "failed",
                "--proof-id",
                str(proof["proof_id"]),
            )
            self.assertEqual(spoof.returncode, 2)

            sentinel = repo / "SHELL_INJECTION_EXECUTED"
            literal = run_proof(
                repo,
                "U1",
                [
                    "python3",
                    "-c",
                    "import sys; print(sys.argv[1])",
                    f"; touch {sentinel}",
                ],
            )
            self.assertEqual(literal["proof"]["exit_code"], 0)
            self.assertFalse(sentinel.exists())
            timed = run_proof(
                repo,
                "U1",
                ["python3", "-c", "import time; time.sleep(2)"],
                timeout=0.01,
            )
            self.assertTrue(timed["proof"]["timed_out"])
            self.assertNotEqual(timed["proof"]["exit_code"], 0)
            missing_timeout = run_guard(
                "proof",
                "--root",
                str(repo),
                "--planning-version",
                "v1",
                "--plan",
                "P01",
                "--unit",
                "U1",
                "--commit",
                git(repo, "rev-parse", "HEAD"),
                "--cwd",
                ".",
                "--",
                "python3",
                "-c",
                "raise SystemExit(0)",
            )
            self.assertEqual(missing_timeout.returncode, 2)

    def test_proof_store_detects_tampering_and_parallel_writes_do_not_lose_records(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            init_repo(repo)
            command = [
                "python3",
                str(GUARD),
                "proof",
                "--root",
                str(repo),
                "--planning-version",
                "v1",
                "--plan",
                "P01",
                "--unit",
                "U1",
                "--commit",
                git(repo, "rev-parse", "HEAD"),
                "--cwd",
                ".",
                "--timeout",
                "5",
                "--",
                "python3",
                "-c",
                "import time; time.sleep(0.1); raise SystemExit(0)",
            ]
            first = subprocess.Popen(
                command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            second = subprocess.Popen(
                command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            first_stdout, first_stderr = first.communicate(timeout=10)
            second_stdout, second_stderr = second.communicate(timeout=10)
            self.assertEqual(first.returncode, 0, first_stderr)
            self.assertEqual(second.returncode, 0, second_stderr)
            proof_ids = {
                json.loads(first_stdout)["proof_id"],
                json.loads(second_stdout)["proof_id"],
            }
            store_path = (
                repo / "artifacts/bianchini/v1/codex/convergence/P01/.proofs/U1.json"
            )
            store = json.loads(store_path.read_text(encoding="utf-8"))
            self.assertTrue(proof_ids.issubset(store["proofs"]))

            proof_id = next(iter(proof_ids))
            store_path.with_suffix(".json.bak").unlink(missing_ok=True)
            store["proofs"][proof_id]["exit_code"] = 17
            store_path.write_text(json.dumps(store), encoding="utf-8")
            candidate = initial_blocker()
            candidate.pop("_test_command")
            candidate["proof_id"] = proof_id
            with self.assertRaises(AssertionError) as raised:
                freeze(repo, [candidate])
            self.assertIn("assinatura guard-owned inválida", str(raised.exception))

    def test_requirement_binding_and_three_root_cause_limit(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            init_repo(repo)
            proof = run_proof(repo, "U1", ["python3", "-c", "raise SystemExit(9)"])
            findings: list[dict[str, object]] = []
            for index in range(1, 6):
                item = initial_blocker(f"B{index}")
                item.pop("_test_command")
                item["proof_id"] = proof["proof_id"]
                item["root_cause"] = "same-root" if index in {1, 2} else f"root-{index}"
                if index == 3:
                    item["approved_requirement"] = (
                        "comportamento aprovado da unidade sintética"
                    )
                findings.append(item)
            missing = initial_blocker("B6")
            missing.pop("_test_command")
            missing["proof_id"] = proof["proof_id"]
            missing["approved_requirement"] = "REQ-DOES-NOT-EXIST"
            findings.append(missing)
            _, frozen = freeze(repo, findings)
            self.assertEqual(len(frozen["state"]["blockers"]), 3)
            reasons = [
                item["deferred_reason"]
                for item in frozen["state"]["deferred_hardening"]
            ]
            self.assertTrue(
                any("causa raiz consolidada" in reason for reason in reasons)
            )
            self.assertTrue(any("limite de três" in reason for reason in reasons))
            self.assertTrue(any("task-brief congelado" in reason for reason in reasons))

    def test_delta_uses_real_proofs_and_ignores_no_declared_exit_codes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            base = init_repo(repo)
            sidecar, _ = freeze(repo, [])
            head = commit_file(repo, "alpha\nchanged\nremove-me\n", "change")
            green_command = ["python3", "-c", "raise SystemExit(0)"]
            base_proof = run_proof(repo, "U1", green_command, commit=base)
            head_proof = run_proof(repo, "U1", green_command, commit=head)
            submit_delta(sidecar, "implementation", base, head)
            finding = delta_finding(base, head)
            finding.pop("_test_command")
            finding["base_proof_id"] = base_proof["proof_id"]
            finding["head_proof_id"] = head_proof["proof_id"]
            finding["head_exit_code"] = 1
            reviewed = review(sidecar, repo, [finding])
            self.assertNotIn("R1", reviewed["state"]["blockers"])
            self.assertIn(
                "somente base_proof_id/head_proof_id",
                reviewed["state"]["deferred_hardening"][-1]["deferred_reason"],
            )
            self.assertNotIn(
                "head_exit_code", reviewed["state"]["deferred_hardening"][-1]
            )

    def test_valid_fix_submit_review_sequence_and_no_consecutive_fix(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            init_repo(repo)
            sidecar, frozen = freeze(repo)
            self.assertEqual(frozen["phase"], "review_frozen")
            self.assertEqual(frozen["next_action"], "fix_required")
            fixing = start_fix(sidecar)
            self.assertEqual(fixing["phase"], "fixing")
            second = run_guard(
                "fix",
                "--sidecar",
                str(sidecar),
                "--blocker",
                "B1",
                "--summary",
                "fix consecutivo",
            )
            self.assertEqual(second.returncode, 2)
            base = git(repo, "rev-parse", "HEAD")
            head = commit_file(
                repo,
                "alpha\nchanged\nremove-me\nresolved-marker\n",
                "fix",
            )
            awaiting = submit_delta(sidecar, "fix", base, head)
            self.assertEqual(awaiting["phase"], "awaiting_review")
            wrong = run_proof(
                repo, "U1", ["python3", "-c", "raise SystemExit(0)"], commit=head
            )
            wrong_path = write_json(
                repo / "synthetic/wrong-resolution.json",
                {
                    "findings": [
                        {
                            "id": "B1",
                            "source": "frozen",
                            "resolution": "resolved",
                            "proof_id": wrong["proof_id"],
                        }
                    ]
                },
            )
            wrong_result = run_guard(
                "review", "--sidecar", str(sidecar), "--findings", str(wrong_path)
            )
            self.assertEqual(wrong_result.returncode, 2)
            self.assertIn("mesmo comando", wrong_result.stderr)
            reviewed = review(sidecar, repo, [frozen_resolved()])
            self.assertEqual(reviewed["phase"], "review_frozen")
            self.assertEqual(reviewed["next_action"], "approve")

    def test_verification_delta_is_allowed_once_after_clean_implementation_review(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            base = init_repo(repo)
            sidecar, _ = freeze(repo, [])
            implementation = commit_file(
                repo, "alpha\nimplemented\nremove-me\n", "implementation"
            )
            submit_delta(sidecar, "implementation", base, implementation)
            first_review = review(sidecar, repo, [])
            self.assertEqual(first_review["phase"], "review_frozen")
            self.assertEqual(first_review["state"]["delta_submissions"], 1)

            verification = commit_file(
                repo,
                "def test_implemented():\n    assert True\n",
                "verification",
                "tests/test_app.py",
            )
            awaiting = submit_delta(
                sidecar, "verification", implementation, verification
            )
            self.assertEqual(awaiting["phase"], "awaiting_review")
            self.assertEqual(
                awaiting["state"]["pending_delta"]["kind"], "verification"
            )
            verified = review(sidecar, repo, [])
            self.assertEqual(verified["phase"], "review_frozen")
            self.assertEqual(verified["next_action"], "approve")
            self.assertEqual(verified["state"]["delta_submissions"], 2)

            second_verification = commit_file(
                repo, "# segunda verificação\n", "second verification", "docs/check.md"
            )
            rejected = run_guard(
                "submit-delta",
                "--sidecar",
                str(sidecar),
                "--kind",
                "verification",
                "--base",
                verification,
                "--head",
                second_verification,
            )
            self.assertEqual(rejected.returncode, 2)
            self.assertIn("único delta implementation", rejected.stderr)

    def test_verification_delta_rejects_production_changes_and_hidden_renames(
        self,
    ) -> None:
        for scenario in ("production", "rename"):
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as temp:
                repo = Path(temp) / "repo"
                base = init_repo(repo)
                sidecar, _ = freeze(repo, [])
                implementation = commit_file(
                    repo, "alpha\nimplemented\nremove-me\n", "implementation"
                )
                submit_delta(sidecar, "implementation", base, implementation)
                review(sidecar, repo, [])

                if scenario == "production":
                    head = commit_file(
                        repo,
                        "alpha\nproduction-change\nremove-me\n",
                        "production change",
                    )
                else:
                    (repo / "tests").mkdir()
                    git(repo, "mv", "app.txt", "tests/app.txt")
                    git(repo, "commit", "-m", "hide production as test")
                    head = git(repo, "rev-parse", "HEAD")
                rejected = run_guard(
                    "submit-delta",
                    "--sidecar",
                    str(sidecar),
                    "--kind",
                    "verification",
                    "--base",
                    implementation,
                    "--head",
                    head,
                )
                self.assertEqual(rejected.returncode, 2)
                self.assertIn("altera código de produção", rejected.stderr)

    def test_review_outside_awaiting_review_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            init_repo(repo)
            sidecar, _ = freeze(repo)
            findings = write_json(repo / "synthetic/review.json", {"findings": []})
            result = run_guard(
                "review", "--sidecar", str(sidecar), "--findings", str(findings)
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("awaiting_review", result.stderr)

    def test_third_fix_is_rejected_and_nonstructural_blocker_is_parked(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            init_repo(repo)
            sidecar, _ = freeze(repo, [initial_blocker(structural=False)])
            fix_review_cycle(repo, sidecar, 1)
            second = fix_review_cycle(repo, sidecar, 2)
            self.assertEqual(second["phase"], "parked")
            self.assertEqual(second["next_action"], "park_unit")
            third = run_guard(
                "fix",
                "--sidecar",
                str(sidecar),
                "--blocker",
                "B1",
                "--summary",
                "terceiro",
            )
            self.assertEqual(third.returncode, 2)
            state = json.loads(sidecar.read_text(encoding="utf-8"))
            self.assertEqual(state["fix_rounds"], 2)
            self.assertEqual(state["blockers"]["B1"]["status"], "open")

    def test_structural_blocker_allows_one_redesign_with_frozen_seam(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            init_repo(repo)
            sidecar, _ = freeze(repo, [initial_blocker(structural=True)])
            fix_review_cycle(repo, sidecar, 1)
            second = fix_review_cycle(repo, sidecar, 2)
            self.assertEqual(second["next_action"], "redesign_allowed")
            renamed = run_guard(
                "redesign",
                "--sidecar",
                str(sidecar),
                "--blocker",
                "B1",
                "--seam",
                "renamed",
                "--summary",
                "tentativa",
            )
            self.assertEqual(renamed.returncode, 2)
            redesigning = result_json(
                run_guard(
                    "redesign",
                    "--sidecar",
                    str(sidecar),
                    "--blocker",
                    "B1",
                    "--seam",
                    "api",
                    "--summary",
                    "redesign estrutural",
                )
            )
            self.assertEqual(redesigning["phase"], "redesigning")
            base = git(repo, "rev-parse", "HEAD")
            head = commit_file(
                repo,
                (repo / "app.txt").read_text(encoding="utf-8") + "redesign\n",
                "redesign",
            )
            submit_delta(sidecar, "redesign", base, head)
            parked = review(sidecar, repo, [frozen_open()])
            self.assertEqual(parked["phase"], "parked")
            second_redesign = run_guard(
                "redesign",
                "--sidecar",
                str(sidecar),
                "--blocker",
                "B1",
                "--seam",
                "api",
                "--summary",
                "segundo",
            )
            self.assertEqual(second_redesign.returncode, 2)
            self.assertEqual(
                json.loads(sidecar.read_text(encoding="utf-8"))["redesign_count"], 1
            )
            renamed_findings = write_json(
                repo / "synthetic/renamed-unit.json", {"findings": []}
            )
            renamed_identity = hashlib.sha256(b"unit:U1").hexdigest()
            renamed_brief = write_task_brief(repo, "U-renamed", renamed_identity)
            renamed_unit = run_guard(
                "freeze",
                "--root",
                str(repo),
                "--planning-version",
                "v1",
                "--plan",
                "P01",
                "--unit",
                "U-renamed",
                "--unit-identity",
                renamed_identity,
                "--task-brief",
                str(renamed_brief),
                "--seam",
                "api",
                "--review-head",
                git(repo, "rev-parse", "HEAD"),
                "--findings",
                str(renamed_findings),
                "--required-gate",
                "unit-tests",
            )
            self.assertEqual(renamed_unit.returncode, 2)
            self.assertIn("identidade da unidade", renamed_unit.stderr)

    def test_redesign_nonstructural_and_structural_without_evidence_are_rejected(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            init_repo(repo)
            invalid = initial_blocker(structural=True)
            invalid["structural_evidence"] = None
            findings = write_json(
                repo / "synthetic/findings.json", {"findings": [invalid]}
            )
            invalid_identity = hashlib.sha256(b"unit:U1").hexdigest()
            invalid_brief = write_task_brief(repo, "U1", invalid_identity)
            freeze_result = run_guard(
                "freeze",
                "--root",
                str(repo),
                "--planning-version",
                "v1",
                "--plan",
                "P01",
                "--unit",
                "U1",
                "--unit-identity",
                invalid_identity,
                "--task-brief",
                str(invalid_brief),
                "--seam",
                "api",
                "--review-head",
                git(repo, "rev-parse", "HEAD"),
                "--findings",
                str(findings),
                "--required-gate",
                "unit-tests",
            )
            self.assertEqual(freeze_result.returncode, 2)

            invalid_reproduction = initial_blocker()
            invalid_reproduction["reproduction"] = "texto livre"
            invalid_findings = write_json(
                repo / "synthetic/invalid-reproduction.json",
                {"findings": [invalid_reproduction]},
            )
            invalid_reproduction_identity = hashlib.sha256(b"unit:U3").hexdigest()
            invalid_reproduction_brief = write_task_brief(
                repo, "U3", invalid_reproduction_identity
            )
            invalid_result = run_guard(
                "freeze",
                "--root",
                str(repo),
                "--planning-version",
                "v1",
                "--plan",
                "P01",
                "--unit",
                "U3",
                "--unit-identity",
                invalid_reproduction_identity,
                "--task-brief",
                str(invalid_reproduction_brief),
                "--seam",
                "api",
                "--review-head",
                git(repo, "rev-parse", "HEAD"),
                "--findings",
                str(invalid_findings),
                "--required-gate",
                "unit-tests",
            )
            self.assertEqual(invalid_result.returncode, 2)

            sidecar, _ = freeze(repo, [initial_blocker(structural=False)], unit="U2")
            fix_review_cycle(repo, sidecar, 1)
            fix_review_cycle(repo, sidecar, 2)
            redesign = run_guard(
                "redesign",
                "--sidecar",
                str(sidecar),
                "--blocker",
                "B1",
                "--seam",
                "api",
                "--summary",
                "não estrutural",
            )
            self.assertEqual(redesign.returncode, 2)

    def test_submit_rejects_nonexistent_commit_wrong_base_wrong_head_and_nonancestor(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            base = init_repo(repo)
            sidecar, _ = freeze(repo, [])
            missing = run_guard(
                "submit-delta",
                "--sidecar",
                str(sidecar),
                "--kind",
                "implementation",
                "--base",
                base,
                "--head",
                "0" * 40,
            )
            self.assertEqual(missing.returncode, 2)
            head1 = commit_file(repo, "alpha\nchanged\nremove-me\n", "head1")
            wrong_base = run_guard(
                "submit-delta",
                "--sidecar",
                str(sidecar),
                "--kind",
                "implementation",
                "--base",
                head1,
                "--head",
                head1,
            )
            self.assertEqual(wrong_base.returncode, 2)
            head2 = commit_file(repo, "alpha\nchanged-again\nremove-me\n", "head2")
            wrong_head = run_guard(
                "submit-delta",
                "--sidecar",
                str(sidecar),
                "--kind",
                "implementation",
                "--base",
                base,
                "--head",
                head1,
            )
            self.assertEqual(wrong_head.returncode, 2)
            self.assertNotEqual(head1, head2)

        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            base = init_repo(repo)
            sidecar, _ = freeze(repo, [])
            git(repo, "checkout", "--orphan", "unrelated")
            unrelated = commit_file(repo, "orphan\n", "unrelated")
            rejected = run_guard(
                "submit-delta",
                "--sidecar",
                str(sidecar),
                "--kind",
                "implementation",
                "--base",
                base,
                "--head",
                unrelated,
            )
            self.assertEqual(rejected.returncode, 2)
            self.assertIn("não descende", rejected.stderr)

    def test_delta_line_must_be_changed_not_context_or_other_file(self) -> None:
        for file, line, expected_reason in (
            ("other.txt", 1, "fora do delta"),
            ("app.txt", 1, "contexto"),
        ):
            with (
                self.subTest(file=file, line=line),
                tempfile.TemporaryDirectory() as temp,
            ):
                repo = Path(temp) / "repo"
                base = init_repo(repo)
                commit_file(repo, "unchanged\n", "other", "other.txt")
                base = git(repo, "rev-parse", "HEAD")
                sidecar, _ = freeze(repo, [])
                head = commit_file(repo, "alpha\nchanged\nremove-me\n", "change")
                submit_delta(sidecar, "implementation", base, head)
                reviewed = review(
                    sidecar,
                    repo,
                    [delta_finding(base, head, file=file, line=line)],
                )
                self.assertEqual(reviewed["next_action"], "approve")
                deferred = reviewed["state"]["deferred_hardening"][-1]
                self.assertIn(expected_reason, deferred["deferred_reason"])

    def test_modified_added_removed_and_rename_lines_are_verified_by_real_git_diff(
        self,
    ) -> None:
        cases = (
            ("alpha\nchanged\nremove-me\n", "app.txt", 2, "modified"),
            ("alpha\nstable\nremove-me\nadded\n", "app.txt", 4, "added"),
            ("alpha\nstable\n", "app.txt", 3, "removed"),
        )
        for content, file, line, kind in cases:
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temp:
                repo = Path(temp) / "repo"
                base = init_repo(repo)
                sidecar, _ = freeze(repo, [])
                head = commit_file(repo, content, kind)
                submit_delta(sidecar, "implementation", base, head)
                reviewed = review(
                    sidecar,
                    repo,
                    [delta_finding(base, head, file=file, line=line, change_kind=kind)],
                )
                self.assertIn("R1", reviewed["state"]["blockers"])

        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            base = init_repo(repo)
            sidecar, _ = freeze(repo, [])
            git(repo, "mv", "app.txt", "renamed.txt")
            (repo / "renamed.txt").write_text(
                "alpha\nchanged\nremove-me\n", encoding="utf-8"
            )
            git(repo, "add", "renamed.txt")
            git(repo, "commit", "-m", "rename and edit")
            head = git(repo, "rev-parse", "HEAD")
            submit_delta(sidecar, "implementation", base, head)
            reviewed = review(
                sidecar,
                repo,
                [delta_finding(base, head, file="renamed.txt", line=2)],
            )
            self.assertIn("R1", reviewed["state"]["blockers"])

        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            base = init_repo(repo)
            sidecar, _ = freeze(repo, [])
            git(repo, "mv", "app.txt", "renamed.txt")
            git(repo, "commit", "-m", "rename only")
            head = git(repo, "rev-parse", "HEAD")
            submit_delta(sidecar, "implementation", base, head)
            reviewed = review(
                sidecar,
                repo,
                [delta_finding(base, head, file="renamed.txt", line=1)],
            )
            self.assertEqual(reviewed["next_action"], "approve")
            self.assertEqual(reviewed["state"]["deferred_hardening"][-1]["id"], "R1")

    def test_reproduction_requires_base_green_head_red_and_does_not_execute_shell_text(
        self,
    ) -> None:
        for base_exit, head_exit in ((1, 1), (0, 0)):
            with (
                self.subTest(base=base_exit, head=head_exit),
                tempfile.TemporaryDirectory() as temp,
            ):
                repo = Path(temp) / "repo"
                base = init_repo(repo)
                sidecar, _ = freeze(repo, [])
                head = commit_file(repo, "alpha\nchanged\nremove-me\n", "change")
                submit_delta(sidecar, "implementation", base, head)
                reviewed = review(
                    sidecar,
                    repo,
                    [
                        delta_finding(
                            base,
                            head,
                            base_exit_code=base_exit,
                            head_exit_code=head_exit,
                        )
                    ],
                )
                self.assertEqual(reviewed["next_action"], "approve")
                self.assertEqual(
                    reviewed["state"]["deferred_hardening"][-1]["id"], "R1"
                )

        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            base = init_repo(repo)
            sidecar, _ = freeze(repo, [])
            head = commit_file(repo, "alpha\nchanged\nremove-me\n", "change")
            sentinel = repo / "SHELL_INJECTION_EXECUTED"
            submit_delta(sidecar, "implementation", base, head)
            reviewed = review(
                sidecar,
                repo,
                [
                    delta_finding(
                        base,
                        head,
                        command=[
                            "python3",
                            "-c",
                            "from pathlib import Path; raise SystemExit(1 if 'changed' in Path('app.txt').read_text() else 0)",
                            f"; touch {sentinel}",
                        ],
                    )
                ],
            )
            self.assertIn("R1", reviewed["state"]["blockers"])
            self.assertFalse(sentinel.exists())

    def test_complete_requires_no_blockers_and_all_required_gates(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            init_repo(repo)
            blocked, _ = freeze(repo, [initial_blocker()], unit="blocked")
            result = run_guard("complete", "--sidecar", str(blocked))
            self.assertEqual(result.returncode, 2)
            clean, frozen = freeze(repo, [], unit="clean")
            self.assertEqual(frozen["next_action"], "approve")
            without_gate = run_guard("complete", "--sidecar", str(clean))
            self.assertEqual(without_gate.returncode, 2)
            record_gate(repo, clean)
            completed = result_json(run_guard("complete", "--sidecar", str(clean)))
            self.assertEqual(completed["phase"], "completed")
            self.assertEqual(completed["next_action"], "completed")
            terminal = run_guard(
                "decision",
                "--sidecar",
                str(clean),
                "--kind",
                "internal",
                "--summary",
                "reabrir",
            )
            self.assertEqual(terminal.returncode, 2)

        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            base = init_repo(repo)
            sidecar, _ = freeze(repo, [])
            record_gate(repo, sidecar)
            head = commit_file(repo, "alpha\nnew\nremove-me\n", "new delta")
            self.assertEqual(
                run_guard("complete", "--sidecar", str(sidecar)).returncode, 2
            )
            submit_delta(sidecar, "implementation", base, head)
            review(sidecar, repo, [])
            stale = run_guard("complete", "--sidecar", str(sidecar))
            self.assertEqual(stale.returncode, 2)
            self.assertIn("revision antiga", stale.stderr)
            record_gate(repo, sidecar)
            self.assertEqual(
                result_json(run_guard("complete", "--sidecar", str(sidecar)))["phase"],
                "completed",
            )

    def test_stop_requires_complete_structured_evidence_for_every_category(
        self,
    ) -> None:
        for index, kind in enumerate(
            sorted(
                {
                    "essential_external_credential",
                    "destructive_action",
                    "new_cost",
                    "material_change",
                    "real_impossibility",
                }
            )
        ):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temp:
                repo = Path(temp) / "repo"
                init_repo(repo)
                sidecar, _ = freeze(repo, [], unit=f"U{index}")
                failed = run_proof(
                    repo,
                    f"U{index}",
                    ["python3", "-c", "raise SystemExit(7)"],
                )
                proof_id = str(failed["proof_id"])
                missing = run_guard(
                    "stop",
                    "--sidecar",
                    str(sidecar),
                    "--kind",
                    kind,
                    "--evidence",
                    str(repo / "synthetic/missing.json"),
                )
                self.assertEqual(missing.returncode, 2)
                incomplete_value = stop_evidence(kind, proof_id)
                incomplete_value.pop(next(iter(incomplete_value)))
                incomplete = write_json(
                    repo / "synthetic/incomplete.json", incomplete_value
                )
                rejected = run_guard(
                    "stop",
                    "--sidecar",
                    str(sidecar),
                    "--kind",
                    kind,
                    "--evidence",
                    str(incomplete),
                )
                self.assertEqual(rejected.returncode, 2)
                if kind == "real_impossibility":
                    forged_attempt = stop_evidence(kind, proof_id)
                    forged_attempt["attempts"] = [
                        {"proof_id": proof_id, "exit_code": 0}
                    ]
                    forged_path = write_json(
                        repo / "synthetic/forged-attempt.json", forged_attempt
                    )
                    rejected_forged = run_guard(
                        "stop",
                        "--sidecar",
                        str(sidecar),
                        "--kind",
                        kind,
                        "--evidence",
                        str(forged_path),
                    )
                    self.assertEqual(rejected_forged.returncode, 2)
                    self.assertIn("somente proof_id", rejected_forged.stderr)
                    successful_attempt = stop_evidence(kind, proof_id)
                    green = run_proof(
                        repo,
                        f"U{index}",
                        ["python3", "-c", "raise SystemExit(0)"],
                    )
                    successful_attempt["attempts"] = [{"proof_id": green["proof_id"]}]
                    successful_path = write_json(
                        repo / "synthetic/successful-attempt.json",
                        successful_attempt,
                    )
                    rejected_success = run_guard(
                        "stop",
                        "--sidecar",
                        str(sidecar),
                        "--kind",
                        kind,
                        "--evidence",
                        str(successful_path),
                    )
                    self.assertEqual(rejected_success.returncode, 2)
                valid = write_json(
                    repo / "synthetic/valid.json", stop_evidence(kind, proof_id)
                )
                stopped = result_json(
                    run_guard(
                        "stop",
                        "--sidecar",
                        str(sidecar),
                        "--kind",
                        kind,
                        "--evidence",
                        str(valid),
                    )
                )
                self.assertEqual(stopped["phase"], "stopped")
                self.assertEqual(stopped["next_action"], "stopped")
                terminal = run_guard(
                    "decision",
                    "--sidecar",
                    str(sidecar),
                    "--kind",
                    "internal",
                    "--summary",
                    "não reabrir",
                )
                self.assertEqual(terminal.returncode, 2)

    def test_internal_decision_never_stops_or_asks_user(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            init_repo(repo)
            sidecar, _ = freeze(repo, [])
            decision = result_json(
                run_guard(
                    "decision",
                    "--sidecar",
                    str(sidecar),
                    "--kind",
                    "internal",
                    "--summary",
                    "usar parser existente",
                )
            )
            rendered = json.dumps(decision)
            self.assertEqual(decision["phase"], "review_frozen")
            self.assertNotIn("stopped", rendered)
            self.assertNotIn("ask_user", rendered)

    def test_path_traversal_and_symlinks_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base_dir = Path(temp)
            repo = base_dir / "repo"
            base = init_repo(repo)
            sidecar, _ = freeze(repo, [])
            head = commit_file(repo, "alpha\nchanged\nremove-me\n", "change")
            submit_delta(sidecar, "implementation", base, head)
            traversal = write_json(
                repo / "synthetic/traversal.json",
                {"findings": [delta_finding(base, head, file="../outside.txt")]},
            )
            rejected = run_guard(
                "review", "--sidecar", str(sidecar), "--findings", str(traversal)
            )
            self.assertEqual(rejected.returncode, 2)
            outside = base_dir / "outside"
            outside.mkdir()
            (repo / "link").symlink_to(outside, target_is_directory=True)
            symlink = write_json(
                repo / "synthetic/symlink.json",
                {"findings": [delta_finding(base, head, file="link/file.txt")]},
            )
            rejected_link = run_guard(
                "review", "--sidecar", str(sidecar), "--findings", str(symlink)
            )
            self.assertEqual(rejected_link.returncode, 2)

            internal = repo / "internal"
            internal.mkdir()
            (repo / "internal-link").symlink_to(internal, target_is_directory=True)
            internal_symlink = write_json(
                repo / "synthetic/internal-symlink.json",
                {
                    "findings": [
                        delta_finding(base, head, file="internal-link/file.txt")
                    ]
                },
            )
            rejected_internal_link = run_guard(
                "review",
                "--sidecar",
                str(sidecar),
                "--findings",
                str(internal_symlink),
            )
            self.assertEqual(rejected_internal_link.returncode, 2)

            backup = sidecar.with_suffix(".json.bak")
            if backup.exists():
                backup.unlink()
            external_backup_target = base_dir / "external-backup.json"
            external_backup_target.write_text("preserve", encoding="utf-8")
            backup.symlink_to(external_backup_target)
            rejected_backup = run_guard(
                "decision",
                "--sidecar",
                str(sidecar),
                "--kind",
                "internal",
                "--summary",
                "não escrever no backup externo",
            )
            self.assertEqual(rejected_backup.returncode, 2)
            self.assertEqual(
                external_backup_target.read_text(encoding="utf-8"), "preserve"
            )
            backup.unlink()

            real_sidecar = sidecar.with_name("real-sidecar.json")
            sidecar.rename(real_sidecar)
            sidecar.symlink_to(real_sidecar)
            rejected_sidecar = run_guard("status", "--sidecar", str(sidecar))
            self.assertEqual(rejected_sidecar.returncode, 2)

    def test_truncated_json_recovers_from_bak(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            init_repo(repo)
            sidecar, _ = freeze(repo, [])
            run_guard(
                "decision",
                "--sidecar",
                str(sidecar),
                "--kind",
                "internal",
                "--summary",
                "gera backup",
            )
            backup = sidecar.with_suffix(".json.bak")
            self.assertTrue(backup.is_file())
            sidecar.write_text("{truncated", encoding="utf-8")
            recovered = result_json(run_guard("status", "--sidecar", str(sidecar)))
            self.assertTrue(recovered["recovered"])
            self.assertEqual(recovered["phase"], "review_frozen")

    def test_v1_sidecar_migration_is_generic_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            init_repo(repo)
            sidecar, _ = freeze(repo, [initial_blocker()])
            state = json.loads(sidecar.read_text(encoding="utf-8"))
            state["schema_version"] = 1
            state["status"] = "active"
            state["review_frozen"] = True
            state["redesigns_by_seam"] = {}
            for field in (
                "phase",
                "unit_identity",
                "unit_digest",
                "unit_identity_source",
                "task_brief",
                "task_brief_digest",
                "pending_delta",
                "delta_submissions",
                "redesign_count",
                "required_gates",
                "gates",
            ):
                state.pop(field, None)
            for blocker in state["blockers"].values():
                for field in (
                    "risk_seam",
                    "structural",
                    "structural_class",
                    "structural_evidence",
                ):
                    blocker.pop(field, None)
                blocker["reproduction"] = "reprodução legado falhou"
                blocker["status"] = "resolved"
                blocker["resolution_evidence"] = "reprodução legado passou"
            sidecar.write_text(json.dumps(state), encoding="utf-8")
            first = result_json(run_guard("migrate", "--sidecar", str(sidecar)))
            second = result_json(run_guard("migrate", "--sidecar", str(sidecar)))
            self.assertTrue(first["migrated"])
            self.assertFalse(second["migrated"])
            self.assertEqual(first["state"]["schema_version"], 2)
            self.assertIsInstance(
                first["state"]["blockers"]["B1"]["resolution_evidence"], dict
            )
            self.assertEqual(first["state"], second["state"])


class CodexInstallerScenarios(unittest.TestCase):
    def installer_env(self, home: Path, override: Path | None = None) -> dict[str, str]:
        environment = {**os.environ, "HOME": str(home), "PYTHONDONTWRITEBYTECODE": "1"}
        environment.pop("CODEX_HOME", None)
        environment.pop("CODEX_SKILLS_DIR", None)
        if override is not None:
            environment["CODEX_SKILLS_DIR"] = str(override)
        return environment

    def install(
        self, home: Path, override: Path | None = None
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(INSTALLER)],
            cwd=ROOT,
            env=self.installer_env(home, override),
            text=True,
            capture_output=True,
            check=False,
        )

    def copy_legacy(self, skills_dir: Path) -> Path:
        target = skills_dir / "executar-plano-codex"
        for relative, content in {
            "SKILL.md": "---\nname: executar-plano-codex\n---\n",
            "agents/openai.yaml": "policy:\n  allow_implicit_invocation: false\n",
            "references/CODEX_CONVERGENCE.md": "# convergência legado\n",
            "references/plan-reviewer-codex.md": "# reviewer legado\n",
            "scripts/review_guard.py": "# guard legado\n",
        }.items():
            path = target / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        return target

    def test_default_is_agents_and_override_has_highest_precedence(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / "home"
            home.mkdir()
            installed = self.install(home)
            self.assertEqual(installed.returncode, 0, installed.stderr)
            default_target = home / ".agents/skills/executar-plano-codex"
            self.assertTrue((default_target / "SKILL.md").is_file())
            self.assertFalse((home / ".codex/skills/executar-plano-codex").exists())
            self.assertEqual(list((home / ".agents/skills").glob("*.stage.*")), [])
            installed_again = self.install(home)
            self.assertEqual(installed_again.returncode, 0, installed_again.stderr)
            self.assertEqual(list((home / ".agents/skills").glob("*.backup.*")), [])

        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / "home"
            home.mkdir()
            override = Path(temp) / "custom-skills"
            installed = self.install(home, override)
            self.assertEqual(installed.returncode, 0, installed.stderr)
            self.assertTrue((override / "executar-plano-codex/SKILL.md").is_file())
            self.assertFalse((home / ".agents/skills").exists())

    def test_existing_legacy_installation_is_detected_without_duplicate(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / "home"
            home.mkdir()
            legacy_skills = home / ".codex/skills"
            self.copy_legacy(legacy_skills)
            installed = self.install(home)
            self.assertEqual(installed.returncode, 0, installed.stderr)
            target = legacy_skills / "executar-plano-codex"
            self.assertTrue((target / ".bianchini-codex-overlay.json").is_file())
            self.assertFalse((home / ".agents/skills/executar-plano-codex").exists())

    def test_conflicting_installations_and_override_conflict_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / "home"
            home.mkdir()
            self.copy_legacy(home / ".agents/skills")
            self.copy_legacy(home / ".codex/skills")
            result = self.install(home)
            self.assertEqual(result.returncode, 2)
            self.assertIn("conflito ambíguo", result.stderr)

        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / "home"
            home.mkdir()
            self.copy_legacy(home / ".codex/skills")
            result = self.install(home, Path(temp) / "other-skills")
            self.assertEqual(result.returncode, 2)
            self.assertIn("conflita", result.stderr)

    def test_foreign_files_are_never_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / "home"
            target = home / ".agents/skills/executar-plano-codex"
            target.mkdir(parents=True)
            foreign = target / "foreign.txt"
            foreign.write_text("preserve", encoding="utf-8")
            result = self.install(home)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(foreign.read_text(encoding="utf-8"), "preserve")

    def test_base_implicit_policy_is_installed_only_in_codex_target(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / "home"
            base = home / ".agents/skills/executar-plano"
            legacy_base = home / ".codex/skills/executar-plano"
            for candidate in (base, legacy_base):
                candidate.mkdir(parents=True)
                (candidate / "SKILL.md").write_text(
                    "---\nname: executar-plano\n---\n", encoding="utf-8"
                )
            result = self.install(home)
            self.assertEqual(result.returncode, 0, result.stderr)
            for candidate in (base, legacy_base):
                policy = candidate / "agents/openai.yaml"
                self.assertIn(
                    "allow_implicit_invocation: false",
                    policy.read_text(encoding="utf-8"),
                )
            self.assertFalse((home / ".claude").exists())

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            home = root / "home"
            external = root / "external-executar-plano"
            external.mkdir(parents=True)
            (external / "SKILL.md").write_text(
                "---\nname: executar-plano\n---\n", encoding="utf-8"
            )
            link = home / ".agents/skills/executar-plano"
            link.parent.mkdir(parents=True)
            link.symlink_to(external, target_is_directory=True)
            result = self.install(home)
            self.assertEqual(result.returncode, 2)
            self.assertFalse((external / "agents/openai.yaml").exists())


if __name__ == "__main__":
    unittest.main()
