---
{
  "schema_version": 2,
  "id": "P05",
  "status": "planned",
  "result": "Integrar, modularizar distribuição quando útil, validar jornada real e pacote nas plataformas, atualizar 1.1.0 e entregar commits/push.",
  "requirements": [
    "REQ-009",
    "REQ-010"
  ],
  "acceptance": [
    "Distribuição identifica 1.1.0, ajuda deriva da CLI vigente, CI executa testes nativos em Linux/macOS/Windows e valida pacote real.",
    "Avaliações positivas e negativas demonstram omissão de cenários/páginas, evidência inválida, rejeição de formatos antigos e jornada pública real."
  ],
  "depends_on": [
    "P01",
    "P02",
    "P03",
    "P04"
  ],
  "provides": [
    "method_integracao_distribuicao"
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
          "id": "method_integracao_distribuicao"
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
      "name": "Integrar, modularizar distribuição quando útil, validar jornada real e pacote nas plataformas, atualizar 1.1.0 e entregar commits/push.",
      "result": "Integrar, modularizar distribuição quando útil, validar jornada real e pacote nas plataformas, atualizar 1.1.0 e entregar commits/push.",
      "covers": [
        "REQ-009",
        "REQ-010"
      ],
      "depends_on": [],
      "files": [
        "README.md",
        ".github/workflows/ci.yml",
        "tools/bm-release/main.go",
        "skills/_shared/VERSION"
      ],
      "action": "Integrar, modularizar distribuição quando útil, validar jornada real e pacote nas plataformas, atualizar 1.1.0 e entregar commits/push.",
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
      "risk_seam": "integracao-distribuicao"
    }
  ],
  "scenarios": [
    {
      "id": "SCN-001",
      "requirements": [
        "REQ-009",
        "REQ-010"
      ],
      "platform": "cli",
      "profile": "maintainer",
      "state": "success-and-rejection",
      "expected": "Integrar, modularizar distribuição quando útil, validar jornada real e pacote nas plataformas, atualizar 1.1.0 e entregar commits/push.",
      "risk": "pacote não executar jornada ou regressão escapar da integração",
      "evidence_kinds": [
        "observation",
        "log"
      ]
    }
  ]
}
---
# P05 — integracao-distribuicao

Responsável: root.

Integrar, modularizar distribuição quando útil, validar jornada real e pacote nas plataformas, atualizar 1.1.0 e entregar commits/push.

Implementação independente dentro do ownership; integração de interfaces entre P01/P02/P03 antes da validação final. Executar testes focais durante edição. P05 executa suite final, race, vet, pacote e jornada pública. Não duplicar revisão de trechos inalterados.

