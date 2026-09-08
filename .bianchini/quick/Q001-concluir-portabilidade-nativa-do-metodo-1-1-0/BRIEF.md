---
{
  "acceptance": [
    "CI nativo Linux, macOS e Windows aprovado"
  ],
  "base_head": "427ddc36cd205e09c4935c90c682fd6d5ee2a453",
  "created_at": "2026-09-08T22:39:39+00:00",
  "digest": "9d4e281ddbe40beb4ac0ad4efc7437211e43ee6dd2bad349fb2b86a419a59554",
  "docviva_before": {
    ".bianchini/current/ARCHITECTURE.md": "43ed75572a9e0332523ed6cce3d258f0f24da381a02090a88e8562c7cb52f269",
    ".bianchini/current/SYSTEM_MODEL.md": "62ca1f0c1eb22043c801f0556f257a1260088bd4cc9a62da427b9f37207ed9a0",
    ".bianchini/current/specs/MANIFEST.json": "260aff80512218409d4b789373c73bb12b96b163b2af68aaef6c9c925812aa52",
    ".bianchini/current/specs/method.md": "151d935641de484e47c9459cee78e980469d699013e05ea555fc78c63e1e1aae"
  },
  "docviva_contract": 1,
  "flow": {
    "payment": false,
    "webhook": false
  },
  "guards": [],
  "id": "Q001-concluir-portabilidade-nativa-do-metodo-1-1-0",
  "missing_guards": [],
  "model_before": {
    "capabilities": [],
    "contracts": [
      {
        "id": "method_metodo_unico"
      },
      {
        "id": "method_workspace_coeso"
      },
      {
        "id": "method_garantias_verificaveis"
      },
      {
        "id": "method_skills_integradas"
      },
      {
        "id": "method_integracao_distribuicao"
      }
    ],
    "data": [],
    "effects": [],
    "integrations": [],
    "interfaces": [],
    "invariants": [],
    "journeys": [],
    "modules": [],
    "ownership": [],
    "schema_version": 1
  },
  "objective": "Concluir portabilidade nativa do método 1.1.0",
  "production_checkpoint_required": false,
  "required_guards": [],
  "risk": {
    "additional_guards": [],
    "declared_score": 0,
    "derived_floor": 0,
    "diff_floor": 0,
    "dimensions": {
      "concurrency": 0,
      "external_effect": 0,
      "migration": 0,
      "money": 0,
      "scope": 0
    },
    "effective_score": 0,
    "initial_floor": 0,
    "overrides": [],
    "phase": "start",
    "reasons": [],
    "reclassified": false,
    "risk_contract": "quick-risk-floor-v1",
    "risk_inputs": {
      "declared_paths": [],
      "flags": {
        "concurrency": 0,
        "external_effect": 0,
        "migration": 0,
        "money": 0,
        "payment": false,
        "scope": 0,
        "webhook": false
      }
    },
    "route": "normal",
    "schema_version": 1,
    "score": 0,
    "workflow": "quick"
  },
  "schema_version": 1,
  "scope": "Aceitar caminhos absolutos nativos de Windows preservando contratos relativos seguros; fixtures LF e teste de executável .exe",
  "status": "active",
  "verification": [
    "go test ./..."
  ]
}
---

# Quick Q001-concluir-portabilidade-nativa-do-metodo-1-1-0

Concluir portabilidade nativa do método 1.1.0
