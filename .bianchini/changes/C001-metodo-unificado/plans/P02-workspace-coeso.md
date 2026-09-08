---
{
  "schema_version": 2,
  "id": "P02",
  "status": "planned",
  "result": "Centralizar caminhos, reunir plano/resultado, aceitar somente contrato atual e preservar transações.",
  "requirements": [
    "REQ-002",
    "REQ-003"
  ],
  "acceptance": [
    "Documentação e evidências do projeto em .bianchini; plano e resultado juntos; caminhos centralizados e estrutura legível.",
    "Responsabilidades Go separadas em módulos úteis, tipos nos novos contratos sensíveis, sem quebrar atomicidade, locks e recuperação."
  ],
  "depends_on": [],
  "provides": [
    "method_workspace_coeso"
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
          "id": "method_workspace_coeso"
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
      "name": "Centralizar caminhos, reunir plano/resultado, aceitar somente contrato atual e preservar transações.",
      "result": "Centralizar caminhos, reunir plano/resultado, aceitar somente contrato atual e preservar transações.",
      "covers": [
        "REQ-002",
        "REQ-003"
      ],
      "depends_on": [],
      "files": [
        "internal/gokernel/workspace.go",
        "internal/gokernel/model.go",
        "internal/gokernel/plan_files.go"
      ],
      "action": "Centralizar caminhos, reunir plano/resultado, aceitar somente contrato atual e preservar transações.",
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
      "risk_seam": "workspace-coeso"
    }
  ]
}
---
# P02 — workspace-coeso

Responsável: workspace.

Centralizar caminhos, reunir plano/resultado, aceitar somente contrato atual e preservar transações.

Implementação independente dentro do ownership; integração de interfaces entre P01/P02/P03 antes da validação final. Executar testes focais durante edição. P05 executa suite final, race, vet, pacote e jornada pública. Não duplicar revisão de trechos inalterados.

