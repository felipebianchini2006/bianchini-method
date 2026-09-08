---
{
  "schema_version": 2,
  "id": "P03",
  "status": "planned",
  "result": "Implementar proveniência honesta e cobertura obrigatória de homologação com testes positivos e negativos.",
  "requirements": [
    "REQ-004",
    "REQ-005"
  ],
  "acceptance": [
    "Selo de escopo distingue integridade, processamento declarado, cobertura registrada por página e revisão semântica; não promete leitura que não verificou.",
    "Requisito, cenário, perfil, plataforma, risco e evidência têm vínculo verificável; cenário obrigatório omitido ou evidência obsoleta bloqueia fechamento."
  ],
  "depends_on": [],
  "provides": [
    "method_garantias_verificaveis"
  ],
  "consumes": [],
  "modules": [],
  "interfaces": [],
  "ownership": [],
  "data": [],
  "model_delta": {
    "contracts": {
      "add": [
        {
          "id": "method_garantias_verificaveis"
        }
      ]
    }
  },
  "migrations": [],
  "effects": [],
  "rollback": "Reverter somente o commit desta entrega, preservando documentação e provas; não reescrever histórico.",
  "verifications": [
    "go test ./internal/acceptance ./internal/gokernel -run 'TestScope|TestHomologation|TestReleaseRejects|TestManualProof|TestTypedLifecycle' -count=1"
  ],
  "future_constraints": [
    "Não restaurar compatibilidade de gerações retiradas."
  ],
  "execution": "grouped",
  "review": "plan_gate",
  "tasks": [
    {
      "id": "T01",
      "name": "Implementar proveniência honesta e cobertura obrigatória de homologação com testes positivos e negativos.",
      "result": "Implementar proveniência honesta e cobertura obrigatória de homologação com testes positivos e negativos.",
      "covers": [
        "REQ-004",
        "REQ-005"
      ],
      "depends_on": [],
      "files": [
        "internal/acceptance/scenarios.go",
        "internal/gokernel/scope.go",
        "internal/gokernel/scope_manifest.go",
        "internal/gokernel/homologation.go",
        "internal/gokernel/verification_release.go",
        "internal/gokernel/release_identity.go"
      ],
      "action": "Implementar proveniência honesta e cobertura obrigatória de homologação com testes positivos e negativos.",
      "verify": {
        "kind": "command",
        "argv": [
          "go",
          "test",
          "./internal/acceptance",
          "./internal/gokernel",
          "-run",
          "TestScope|TestHomologation|TestReleaseRejects|TestManualProof|TestTypedLifecycle",
          "-count=1"
        ],
        "cwd": ".",
        "timeout_seconds": 300,
        "cache": "fresh",
        "proves": "Regressões nativas das responsabilidades alteradas e integração da CLI."
      },
      "done": "Implementação revisada, verificações pertinentes aprovadas, comportamento demonstrado e limitações registradas.",
      "risk_seam": "garantias-verificaveis"
    }
  ],
  "scenarios": [
    {
      "id": "SCN-001",
      "requirements": [
        "REQ-004",
        "REQ-005"
      ],
      "platform": "cli",
      "profile": "maintainer",
      "state": "success-and-rejection",
      "expected": "Implementar proveniência honesta e cobertura obrigatória de homologação com testes positivos e negativos.",
      "risk": "selo ou fechamento aceitar alegação sem evidência atual",
      "evidence_kinds": [
        "observation",
        "log"
      ]
    }
  ]
}
---
# P03 — garantias-verificaveis

Responsável: root.

Implementar proveniência honesta e cobertura obrigatória de homologação com testes positivos e negativos.

Implementação independente dentro do ownership; integração de interfaces entre P01/P02/P03 antes da validação final. Executar testes focais durante edição. P05 executa suite final, race, vet, pacote e jornada pública. Não duplicar revisão de trechos inalterados.

