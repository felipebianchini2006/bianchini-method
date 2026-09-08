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
    "go test ./...",
    "go vet ./..."
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
        "internal/gokernel/scope.go",
        "internal/gokernel/verification.go",
        "internal/gokernel/release_identity.go"
      ],
      "action": "Implementar proveniência honesta e cobertura obrigatória de homologação com testes positivos e negativos.",
      "verify": {
        "kind": "command",
        "argv": [
          "go",
          "test",
          "./..."
        ],
        "cwd": ".",
        "timeout_seconds": 300,
        "cache": "fresh",
        "proves": "Regressões nativas das responsabilidades alteradas e integração da CLI."
      },
      "done": "Implementação revisada, verificações pertinentes aprovadas, comportamento demonstrado e limitações registradas.",
      "risk_seam": "garantias-verificaveis"
    }
  ]
}
---
# P03 — garantias-verificaveis

Responsável: root.

Implementar proveniência honesta e cobertura obrigatória de homologação com testes positivos e negativos.

Implementação independente dentro do ownership; integração de interfaces entre P01/P02/P03 antes da validação final. Executar testes focais durante edição. P05 executa suite final, race, vet, pacote e jornada pública. Não duplicar revisão de trechos inalterados.

