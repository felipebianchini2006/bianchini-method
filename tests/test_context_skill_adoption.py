from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "_shared" / "scripts"
import sys

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))

from bm_context import ContextPackError, compile_context_pack, verify_context_pack  # noqa: E402
from tests import test_context_pack as context_fixture  # noqa: E402


STATE_FIELDS = (
    "active_work",
    "current_unit",
    "status",
    "blockers",
    "next_action",
    "last_completed",
    "pointers",
)
DEBUG_FIELDS = (
    "id",
    "stage",
    "objective",
    "root_cause",
    "hypotheses",
    "experiments",
    "red",
    "green",
    "residual_risk",
)


def read_frontmatter(path: Path) -> dict[str, Any]:
    content = path.read_text(encoding="utf-8")
    match = re.match(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|\Z)", content, re.DOTALL)
    if match is None:
        raise AssertionError(f"frontmatter ausente em {path}")
    value = json.loads(match.group(1))
    if not isinstance(value, dict):
        raise AssertionError(f"frontmatter não é objeto em {path}")
    return value


def state_slice(value: dict[str, Any]) -> dict[str, Any]:
    return {field: value.get(field) for field in STATE_FIELDS}


def markdown_sections(content: str, identifiers: set[str]) -> list[dict[str, str]]:
    headings = list(re.finditer(r"(?m)^(#{1,6})\s+([^\n]+)$", content))
    selected: list[dict[str, str]] = []
    for index, heading in enumerate(headings):
        title = heading.group(2)
        identifier = next(
            (
                candidate
                for candidate in identifiers
                if re.search(rf"(?<![A-Za-z0-9-]){re.escape(candidate)}(?![A-Za-z0-9-])", title)
            ),
            None,
        )
        if identifier is None:
            continue
        level = len(heading.group(1))
        end = len(content)
        for following in headings[index + 1 :]:
            if len(following.group(1)) <= level:
                end = following.start()
                break
        selected.append({"id": identifier, "content": content[heading.start() : end].strip()})
    return sorted(selected, key=lambda item: item["id"])


def install_representative_completion_sources(root: Path) -> None:
    quick = root / ".bianchini/quick/Q012-small"
    (quick / "RESULT.md").write_text(
        context_fixture.frontmatter(
            {
                "status": "completed",
                "actual_delta": ["src/t01.py"],
                "evidence": ["python3 -m unittest tests.test_small"],
            },
            "Resultado quick",
        ),
        encoding="utf-8",
    )

    debug_path = root / ".bianchini/debug/active/D004-login.md"
    debug = read_frontmatter(debug_path)
    debug.update(
        {
            "hypotheses": ["cache obsoleto"],
            "experiments": ["invalidar cache"],
            "red": "teste reproduz falha",
            "green": "teste passa após correção",
            "residual_risk": "ambiente real ainda não validado",
            "gates": ["python3 -m unittest tests.test_login"],
            "findings": [{"id": "real-env", "status": "open"}],
        }
    )
    debug_path.write_text(
        context_fixture.frontmatter(debug, "Debug"), encoding="utf-8"
    )

    homologation = root / ".bianchini/changes/C001-context/results/HOMOLOGATION.md"
    homologation.write_text(
        context_fixture.frontmatter(
            {
                "schema_version": 1,
                "fingerprint": "build-a",
                "change": "C001-context",
                "status": "running",
                "gates": ["release-tests", "visual-review"],
                "blockers": ["aguardar ambiente real"],
                "findings": [
                    {"id": "visual-review", "status": "open"},
                    {"id": "unit-tests", "status": "resolved"},
                ],
                "required_refs": [
                    ".bianchini/changes/C001-context/results/P00.md"
                ],
            },
            "Homologação",
        ),
        encoding="utf-8",
    )


def full_task_projection(root: Path) -> dict[str, Any]:
    change = root / ".bianchini/changes/C001-context"
    state = read_frontmatter(root / ".bianchini/STATE.md")
    plan = read_frontmatter(change / "plans/P01.md")
    task = next(item for item in plan["tasks"] if item["id"] == "T01")
    plans = [read_frontmatter(path) for path in sorted((change / "plans").glob("*.md"))]
    by_id = {item["id"]: item for item in plans}
    scope_ids = set(task["covers"])
    manifest = json.loads((change / "specs/MANIFEST.json").read_text(encoding="utf-8"))
    model = read_frontmatter(change / "SYSTEM_MODEL.md")
    coherence = read_frontmatter(change / "COHERENCE.md")
    roadmap = read_frontmatter(change / "ROADMAP.md")

    spec_requirements: list[dict[str, Any]] = []
    for spec in manifest["specs"]:
        spec_sections = {
            item["id"]: item["content"]
            for item in markdown_sections(
                (change / "specs/expected" / spec["path"]).read_text(encoding="utf-8"),
                {declaration["id"] for declaration in spec["requirements"]},
            )
        }
        for declaration in spec["requirements"]:
            relevant = sorted(scope_ids & set(declaration["scope"]))
            if relevant:
                spec_requirements.append(
                    {
                        "id": declaration["id"],
                        "spec": spec["id"],
                        "path": spec["path"],
                        "scope": relevant,
                        "content": spec_sections[declaration["id"]],
                    }
                )

    touches = {
        "modules": set(plan["modules"]),
        "contracts": {
            item["id"] for item in plan["model_delta"]["contracts"]["add"]
        },
    }
    model_nodes = []
    for section in sorted(touches):
        values = {item["id"]: item for item in model[section]}
        for identifier in sorted(touches[section]):
            model_nodes.append(
                {"section": section, "id": identifier, "value": values.get(identifier)}
            )

    provider_ids = sorted(
        {
            item["id"]
            for item in plans
            if item["id"] != plan["id"]
            and set(item["provides"]) & set(plan["consumes"])
        }
        | set(plan["depends_on"])
    )
    dependency_results = [
        {"id": identifier, "result": read_frontmatter(change / f"results/{identifier}.md")}
        for identifier in provider_ids
    ]
    dependency_results.extend(
        {
            "id": f"P01/{identifier}",
            "result": read_frontmatter(change / f"results/tasks/P01/{identifier}.md"),
        }
        for identifier in sorted(task["depends_on"])
    )
    completed_providers = [
        {
            "id": identifier,
            "result": read_frontmatter(change / f"results/{identifier}.md"),
            "contracts": sorted(set(plan["consumes"]) & set(by_id[identifier]["provides"])),
        }
        for identifier in provider_ids
        if set(plan["consumes"]) & set(by_id[identifier]["provides"])
    ]
    affected_consumers = [
        {
            "id": item["id"],
            "contracts": sorted(set(plan["provides"]) & set(item["consumes"])),
        }
        for item in plans
        if item["id"] != plan["id"] and set(plan["provides"]) & set(item["consumes"])
    ]
    decision_ids = set(
        re.findall(r"(?<![A-Za-z0-9])D-\d{3,}(?![A-Za-z0-9])", json.dumps([plan, task]))
    )
    findings = [
        item
        for item in coherence["findings"]
        if item.get("status", "open") == "open"
        and (not item.get("phases") or "P01" in item["phases"])
    ]
    ledger = [
        json.loads(line)
        for line in (change / "results/LEDGER.jsonl").read_text(encoding="utf-8").splitlines()
    ][-20:]

    return {
        "kind": "task",
        "state": state_slice(state),
        "plan": {key: value for key, value in plan.items() if key != "tasks"},
        "task": task,
        "roadmap": {"phase": "P01", "status": roadmap["status"]["P01"]},
        "scope": markdown_sections(
            (change / "SCOPE.md").read_text(encoding="utf-8"), scope_ids
        ),
        "spec_requirements": spec_requirements,
        "risk_coverage": sorted(
            [item for item in manifest["risk_coverage"] if item["scope"] in scope_ids],
            key=lambda item: (item["scope"], item["kind"], item["target"]),
        ),
        "model_nodes": model_nodes,
        "completed_providers": sorted(completed_providers, key=lambda item: item["id"]),
        "affected_consumers": sorted(affected_consumers, key=lambda item: item["id"]),
        "architecture_decisions": markdown_sections(
            (change / "ARCHITECTURE.md").read_text(encoding="utf-8"), decision_ids
        ),
        "gates": [*plan["verifications"], task["verify"]],
        "blockers": state["blockers"],
        "open_findings": findings,
        "dependency_results": dependency_results,
        "ledger_tail": ledger,
    }


def full_quick_projection(root: Path) -> dict[str, Any]:
    directory = root / ".bianchini/quick/Q012-small"
    state = read_frontmatter(root / ".bianchini/STATE.md")
    brief = read_frontmatter(directory / "BRIEF.md")
    progress = read_frontmatter(directory / "PROGRESS.md")
    return {
        "kind": "quick",
        "state": state_slice(state),
        "brief": brief,
        "latest_event": progress["events"][-1],
        "result": read_frontmatter(directory / "RESULT.md"),
        "gates": brief["gates"],
        "blockers": brief["blockers"],
        "open_findings": brief.get("findings", []),
    }


def full_debug_projection(root: Path) -> dict[str, Any]:
    state = read_frontmatter(root / ".bianchini/STATE.md")
    debug = read_frontmatter(root / ".bianchini/debug/active/D004-login.md")
    return {
        "kind": "debug",
        "state": state_slice(state),
        "debug": {key: debug[key] for key in DEBUG_FIELDS if key in debug},
        "latest_event": debug["events"][-1],
        "gates": debug["gates"],
        "blockers": debug["blockers"],
        "open_findings": debug["findings"],
    }


def full_rc_projection(root: Path) -> dict[str, Any]:
    state = read_frontmatter(root / ".bianchini/STATE.md")
    source = root / ".bianchini/changes/C001-context/results/HOMOLOGATION.md"
    candidate = read_frontmatter(source)
    evidence_path = root / candidate["required_refs"][0]
    return {
        "kind": "release_candidate",
        "state": state_slice(state),
        "release_candidate": candidate,
        "source": source.relative_to(root).as_posix(),
        "gates": candidate["gates"],
        "blockers": candidate["blockers"],
        "open_findings": [
            item
            for item in candidate["findings"]
            if item.get("status", "open") == "open"
        ],
        "evidence": [
            {
                "path": evidence_path.relative_to(root).as_posix(),
                "value": read_frontmatter(evidence_path),
            }
        ],
    }


def compile_and_read(root: Path, unit: str) -> dict[str, Any]:
    result = compile_context_pack(root, unit)
    path = root / str(result["path"])
    verified = verify_context_pack(root, path)
    if verified["unit"] != unit:
        raise AssertionError("verify retornou unidade divergente")
    payload = json.loads(path.read_text(encoding="utf-8"))
    context = dict(payload["context"])
    context.pop("approved_lessons", None)
    return context


class ContextSkillAdoptionScenarios(unittest.TestCase):
    SKILLS = (
        "executar-plano",
        "executar-direto",
        "corrigir-bug",
        "homologar-sistema",
        "status-projeto",
    )

    def make_repo(self, base: Path) -> Path:
        root = context_fixture.ContextPackScenarios().make_repo(base)
        install_representative_completion_sources(root)
        return root

    def test_representative_full_context_and_pack_are_operationally_equivalent(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = self.make_repo(Path(temp))
            cases = (
                ("C/P/T", "C001/P01/T01", full_task_projection),
                ("Q", "Q012", full_quick_projection),
                ("D", "D004", full_debug_projection),
                ("RC", "RC:build-a", full_rc_projection),
            )
            compiled: dict[str, dict[str, Any]] = {}
            for label, unit, baseline_projection in cases:
                with self.subTest(interface=label):
                    expected = baseline_projection(root)
                    actual = compile_and_read(root, unit)
                    self.assertEqual(actual, expected)
                    compiled[unit] = actual

            # status-projeto usa a unidade ativa e não cria uma segunda fonte de estado.
            baseline_state = state_slice(read_frontmatter(root / ".bianchini/STATE.md"))
            self.assertEqual(compiled["C001/P01/T01"]["state"], baseline_state)
            self.assertEqual(
                compiled["C001/P01/T01"]["state"]["current_unit"], "P01/T01"
            )

    def test_adopted_packs_fail_closed_on_missing_or_stale_required_source(self) -> None:
        missing_sources = (
            ("C/P/T", "C001/P01/T01", ".bianchini/changes/C001-context/results/tasks/P01/T00.md"),
            ("Q", "Q012", ".bianchini/quick/Q012-small/BRIEF.md"),
            ("D", "D004", ".bianchini/debug/active/D004-login.md"),
            ("RC", "RC:build-a", ".bianchini/changes/C001-context/results/P00.md"),
            ("status", "C001/P01/T01", ".bianchini/STATE.md"),
        )
        for label, unit, relative in missing_sources:
            with self.subTest(interface=label), tempfile.TemporaryDirectory() as temp:
                root = self.make_repo(Path(temp))
                (root / relative).unlink()
                with self.assertRaisesRegex(ContextPackError, "PACK_INCOMPLETE"):
                    compile_context_pack(root, unit)

        with tempfile.TemporaryDirectory() as temp:
            root = self.make_repo(Path(temp))
            packs = {
                unit: root / str(compile_context_pack(root, unit)["path"])
                for unit in ("C001/P01/T01", "Q012", "D004", "RC:build-a")
            }
            state_path = root / ".bianchini/STATE.md"
            state_path.write_text(
                state_path.read_text(encoding="utf-8") + "\nDrift após compilação.\n",
                encoding="utf-8",
            )
            for unit, path in packs.items():
                with self.subTest(stale_unit=unit), self.assertRaisesRegex(
                    ContextPackError, "STALE_EVIDENCE"
                ):
                    verify_context_pack(root, path)

    def test_operational_skills_use_context_pack_as_primary_interface(self) -> None:
        for name in self.SKILLS:
            with self.subTest(skill=name):
                content = (ROOT / "skills" / name / "SKILL.md").read_text(
                    encoding="utf-8"
                )
                self.assertIn("bm context pack", content)
                self.assertIn("PACK_INCOMPLETE", content)
                self.assertNotRegex(content, r"Leia \[.*METHOD_CONTRACT\.md")

    def test_execution_skills_reject_stale_pack_instead_of_full_contract_fallback(self) -> None:
        for name in ("executar-plano", "executar-direto", "corrigir-bug"):
            with self.subTest(skill=name):
                content = (ROOT / "skills" / name / "SKILL.md").read_text(
                    encoding="utf-8"
                )
                self.assertIn("STALE_EVIDENCE", content)
                self.assertIn("sem reler o contrato completo", content)


if __name__ == "__main__":
    unittest.main()
