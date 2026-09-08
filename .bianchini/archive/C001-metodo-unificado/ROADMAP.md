---
{
  "phases": [
    {
      "depends_on": [],
      "execution": "grouped",
      "id": "P01",
      "requirements": [
        "REQ-001"
      ],
      "result": "Retirar gerações antigas e tornar contrato/ajuda/testes atuais independentes do oráculo.",
      "tasks": [
        "T01"
      ]
    },
    {
      "depends_on": [],
      "execution": "grouped",
      "id": "P02",
      "requirements": [
        "REQ-002",
        "REQ-003"
      ],
      "result": "Centralizar caminhos, reunir plano/resultado, aceitar somente contrato atual e preservar transações.",
      "tasks": [
        "T01"
      ]
    },
    {
      "depends_on": [],
      "execution": "grouped",
      "id": "P03",
      "requirements": [
        "REQ-004",
        "REQ-005"
      ],
      "result": "Implementar proveniência honesta e cobertura obrigatória de homologação com testes positivos e negativos.",
      "tasks": [
        "T01"
      ]
    },
    {
      "depends_on": [],
      "execution": "grouped",
      "id": "P04",
      "requirements": [
        "REQ-006",
        "REQ-007",
        "REQ-008",
        "REQ-011",
        "REQ-012"
      ],
      "result": "Integrar orientação enxuta e portátil de design, prova, simplificação, segurança e correção contínua.",
      "tasks": [
        "T01"
      ]
    },
    {
      "depends_on": [
        "P01",
        "P02",
        "P03",
        "P04"
      ],
      "execution": "grouped",
      "id": "P05",
      "requirements": [
        "REQ-009",
        "REQ-010"
      ],
      "result": "Integrar, modularizar distribuição quando útil, validar jornada real e pacote nas plataformas, atualizar 1.1.0 e entregar commits/push.",
      "tasks": [
        "T01"
      ]
    }
  ],
  "planning_contract": 2,
  "schema_version": 1
}
---

# Roadmap

Gerado deterministicamente a partir dos planos.

## P01 — Retirar gerações antigas e tornar contrato/ajuda/testes atuais independentes do oráculo.

- Depende de: nenhum
- Escopo: REQ-001
- Tarefas: T01

## P02 — Centralizar caminhos, reunir plano/resultado, aceitar somente contrato atual e preservar transações.

- Depende de: nenhum
- Escopo: REQ-002, REQ-003
- Tarefas: T01

## P03 — Implementar proveniência honesta e cobertura obrigatória de homologação com testes positivos e negativos.

- Depende de: nenhum
- Escopo: REQ-004, REQ-005
- Tarefas: T01

## P04 — Integrar orientação enxuta e portátil de design, prova, simplificação, segurança e correção contínua.

- Depende de: nenhum
- Escopo: REQ-006, REQ-007, REQ-008, REQ-011, REQ-012
- Tarefas: T01

## P05 — Integrar, modularizar distribuição quando útil, validar jornada real e pacote nas plataformas, atualizar 1.1.0 e entregar commits/push.

- Depende de: P01, P02, P03, P04
- Escopo: REQ-009, REQ-010
- Tarefas: T01
