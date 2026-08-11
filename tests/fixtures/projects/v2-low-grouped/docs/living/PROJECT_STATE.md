{
  "method_version": 2,
  "method_mode": "standalone-adaptive",
  "planning_version": "v1",
  "planning_status": "pending_approval",
  "execution_policy": "adaptive",
  "assurance_profile": "lean",
  "architecture_audit": "optional",
  "architecture_audit_status": "not_run",
  "manual_pdf": "scope",
  "scope": {
    "status": "approved",
    "source": "docs/bianchini/v1/inputs/APPROVED_SCOPE.md",
    "approved_at": "2026-08-11T00:00:00Z"
  },
  "planning": {
    "spec": "docs/bianchini/v1/specs/system.md",
    "review": "docs/bianchini/v1/PLANNING_REVIEW.md"
  },
  "approval": {
    "status": "pending",
    "approved_at": null,
    "approved_by": null,
    "approved_plans": [],
    "package": {
      "algorithm": "sha256-manifest-v1",
      "manifest_path": "artifacts/bianchini/v1/approval/manifest.sha256",
      "manifest_digest": null,
      "files": [
        "docs/bianchini/v1/inputs/APPROVED_SCOPE.md",
        "docs/bianchini/v1/specs/system.md",
        "docs/bianchini/v1/plans/P01-api.md",
        "docs/bianchini/v1/PLANNING_REVIEW.md"
      ]
    }
  },
  "plans": [
    {
      "id": "P01",
      "path": "docs/bianchini/v1/plans/P01-api.md",
      "status": "planned",
      "risk": "low",
      "execution": "grouped",
      "review": "plan_gate",
      "test_seams": ["http-api"],
      "depends_on": [],
      "ledger": "artifacts/bianchini/v1/ledgers/P01.md",
      "gates": ["pytest -q"]
    }
  ],
  "verification": {
    "fast": { "commands": ["pytest -q tests/api"], "status": "pending" },
    "plan": { "commands": ["pytest -q"], "status": "pending" },
    "release": { "commands": ["pytest -q", "playwright test"], "status": "pending" }
  },
  "release": {
    "status": "pending",
    "platforms": ["web"],
    "profiles": ["admin"],
    "candidate": null,
    "final_gate": "homologar-sistema",
    "homologation": "pending",
    "final_review": "pending",
    "delivery": "pending"
  },
  "active_execution": null,
  "telemetry": {
    "enabled": true,
    "path": "artifacts/bianchini/v1/telemetry.jsonl"
  },
  "blockers": [],
  "next_action": "Gerar snapshot e solicitar aprovação única."
}
