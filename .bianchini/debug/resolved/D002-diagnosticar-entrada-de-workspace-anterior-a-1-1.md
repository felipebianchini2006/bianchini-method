---
{
  "actual": "Validação retorna MODEL_MISMATCH genérico antes de detectar os planos antigos",
  "created_at": "2026-09-09T21:24:30+00:00",
  "docviva": {
    "after_digest": "ec569f8b78b2f71c0372c49dcce1f1730c48be7931366958be71051427bb778f",
    "artifacts": [],
    "before_digest": "ec569f8b78b2f71c0372c49dcce1f1730c48be7931366958be71051427bb778f",
    "changed": [],
    "created": [],
    "justification": "Completa o diagnóstico de formatos incompatíveis já documentado na arquitetura aceita; não muda esse contrato.",
    "kind": "internal",
    "modified": [],
    "outcome": "not_applicable",
    "removed": [],
    "required": false,
    "schema_version": 1,
    "status": "verified"
  },
  "docviva_before": {
    ".bianchini/current/ARCHITECTURE.md": "cf3fe71bade94529d42af2e53926494aba2521cfbdac6330c4710d93f87d909c",
    ".bianchini/current/SYSTEM_MODEL.md": "62ca1f0c1eb22043c801f0556f257a1260088bd4cc9a62da427b9f37207ed9a0",
    ".bianchini/current/specs/MANIFEST.json": "260aff80512218409d4b789373c73bb12b96b163b2af68aaef6c9c925812aa52",
    ".bianchini/current/specs/method.md": "151d935641de484e47c9459cee78e980469d699013e05ea555fc78c63e1e1aae"
  },
  "docviva_contract": 1,
  "eliminated_hypotheses": [],
  "environment": "CLI Go base 22279ca com correções 1.1.1",
  "events": [
    {
      "at": "2026-09-09T21:24:43+00:00",
      "event": "reproduced",
      "evidence": "STATE da tag v1.0.0 usa method 0.4; validateState retorna erro genérico antes do parsing dos planos.",
      "fingerprint": "fc661afa1bdd8e3e6855a848d570b220c6ffae42a89fd52ab64d2fd68c09634f",
      "proof_id": ""
    },
    {
      "at": "2026-09-09T21:24:43+00:00",
      "event": "diagnosed",
      "evidence": "Identidade histórica comprovada no Git e ordem da leitura confirmada no loader.",
      "fingerprint": "fc661afa1bdd8e3e6855a848d570b220c6ffae42a89fd52ab64d2fd68c09634f",
      "proof_id": ""
    },
    {
      "at": "2026-09-09T21:24:45+00:00",
      "event": "red",
      "evidence": "Teste CLI com STATE histórico e expectativa de diagnóstico sem mutação.",
      "fingerprint": "fc661afa1bdd8e3e6855a848d570b220c6ffae42a89fd52ab64d2fd68c09634f",
      "proof_id": "proof-ce003b9443dc92cb8b7097c80809a507"
    },
    {
      "at": "2026-09-09T21:25:04+00:00",
      "event": "fixing",
      "evidence": "RED confirmou ausência do diagnóstico esperado.",
      "fingerprint": "fc661afa1bdd8e3e6855a848d570b220c6ffae42a89fd52ab64d2fd68c09634f",
      "proof_id": ""
    },
    {
      "at": "2026-09-09T21:25:31+00:00",
      "event": "green",
      "evidence": "Mesmo teste CLI aceita diagnóstico explícito e confirma STATE intacto.",
      "fingerprint": "38bc9328f4dd29737fb61f4a361154ddd1d28120c39f484d787f4d378172a2b7",
      "proof_id": "proof-2f77bb837c61554d727bd7ccc6ae8f82"
    },
    {
      "at": "2026-09-09T21:26:02+00:00",
      "event": "regression_checked",
      "evidence": "Suíte Go completa no estado final.",
      "fingerprint": "38bc9328f4dd29737fb61f4a361154ddd1d28120c39f484d787f4d378172a2b7",
      "proof_id": "proof-6fb9e9a4b275ef38014d01850c870878"
    },
    {
      "at": "2026-09-09T21:26:02+00:00",
      "event": "documented",
      "evidence": "Guia distribuído descreve a identidade antiga; diagnóstico ocorre antes dos loaders.",
      "fingerprint": "38bc9328f4dd29737fb61f4a361154ddd1d28120c39f484d787f4d378172a2b7",
      "proof_id": ""
    }
  ],
  "expected": "STATE method 0.4 informa transição antes do planejamento",
  "experiments": [],
  "finished_at": "2026-09-09T21:26:02+00:00",
  "green": "Mesmo teste CLI aceita diagnóstico explícito e confirma STATE intacto.",
  "hypotheses": [],
  "id": "D002-diagnosticar-entrada-de-workspace-anterior-a-1-1",
  "neighboring_regressions": [
    "Workspace atual, planejamento, arquivo, homologação e distribuição."
  ],
  "objective": "Diagnosticar entrada de workspace anterior à 1.1",
  "origin_evidence": null,
  "origin_refs": null,
  "reason": null,
  "red": "Teste CLI com STATE histórico e expectativa de diagnóstico sem mutação.",
  "regression_contract": {
    "argv": [
      "go",
      "test",
      "./internal/gokernel",
      "-run",
      "^TestLegacyWorkspaceReportsUpgradeBeforePlanning$",
      "-count=1"
    ],
    "failure_pattern": "legacy-entry-regression",
    "test_file": "internal/gokernel/workspace_upgrade_test.go",
    "test_sha256": "b2f8c8946278dc8deab9272f98c1b440f7bfdec5562a2121224eef8c45e614d0"
  },
  "relation": null,
  "residual_risk": "Transição continua manual e revisada; nenhum estado antigo é convertido.",
  "root_cause": "Validação da identidade do workspace não distingue contrato anterior reconhecido de estado de outro método.",
  "schema_version": 1,
  "stage": "documented",
  "status": "resolved",
  "updated_at": "2026-09-09T21:26:02+00:00"
}
---

# Debug D002-diagnosticar-entrada-de-workspace-anterior-a-1-1

Diagnosticar entrada de workspace anterior à 1.1
