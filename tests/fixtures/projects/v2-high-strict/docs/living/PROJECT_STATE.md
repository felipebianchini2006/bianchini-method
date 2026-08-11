{
  "method_version": 2,
  "method_mode": "standalone-adaptive",
  "planning_version": "v1",
  "planning_status": "approved",
  "execution_policy": "adaptive",
  "assurance_profile": "full",
  "architecture_audit": "optional",
  "architecture_audit_status": "not_run",
  "manual_pdf": "none",
  "scope": { "status": "approved", "source": "docs/scope.md", "approved_at": null },
  "planning": { "spec": "docs/spec.md", "review": "docs/review.md" },
  "approval": {
    "status": "approved",
    "approved_at": "2026-08-11T00:00:00Z",
    "approved_by": "owner",
    "approved_plans": ["P01"],
    "package": {
      "algorithm": "sha256-manifest-v1",
      "manifest_path": "artifacts/approval/manifest.sha256",
      "manifest_digest": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
      "files": ["docs/scope.md", "docs/spec.md", "docs/plans/P01-payment.md", "docs/review.md"]
    }
  },
  "plans": [{
    "id": "P01",
    "path": "docs/plans/P01-payment.md",
    "status": "approved",
    "risk": "high",
    "execution": "strict",
    "review": "per_task",
    "test_seams": ["payment-contract"],
    "depends_on": [],
    "ledger": "artifacts/ledgers/P01.md",
    "gates": ["pytest -q tests/payment"]
  }],
  "verification": {
    "fast": { "commands": ["pytest -q tests/payment/unit"], "status": "pending" },
    "plan": { "commands": ["pytest -q tests/payment"], "status": "pending" },
    "release": { "commands": ["pytest -q", "payment-sandbox-e2e"], "status": "pending" }
  },
  "release": {
    "status": "pending",
    "platforms": ["api"],
    "profiles": ["service"],
    "candidate": null,
    "final_gate": "homologar-sistema",
    "homologation": "pending",
    "final_review": "pending",
    "delivery": "pending"
  },
  "telemetry": { "enabled": false, "path": "artifacts/telemetry.jsonl" },
  "blockers": [],
  "next_action": "Executar P01 em modo strict."
}
