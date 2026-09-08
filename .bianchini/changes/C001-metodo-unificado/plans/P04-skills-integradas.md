---
{
  "schema_version": 2,
  "id": "P04",
  "status": "planned",
  "result": "Integrar orientação enxuta e portátil de design, prova, simplificação, segurança e correção contínua.",
  "requirements": [
    "REQ-006",
    "REQ-007",
    "REQ-008",
    "REQ-011",
    "REQ-012"
  ],
  "acceptance": [
    "Homologação opera aplicação real com ferramentas disponíveis, preferindo browser interno e pedindo instalação só se faltar; corrige defeitos e retesta até conclusão ou bloqueio real.",
    "Planejamento inclui caminho de verificação e provas de viabilidade para premissas incertas de alto impacto antes de liberar dependentes.",
    "Orientações selecionadas de Impeccable, verification-planning, simplify, post-refactor, improve-codebase-architecture e security-audit integradas às skills atuais.",
    "Prontidão operacional proporcional verifica dados, integrações, configuração, implantação/recuperação quando aplicável, sem confundir aceite técnico com deploy.",
    "Simplificação e revisão após refatoração integram execução e correção de bugs; verificação de segurança ao fim do plano é proporcional à superfície alterada."
  ],
  "depends_on": [],
  "provides": [
    "method_skills_integradas"
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
          "id": "method_skills_integradas"
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
      "name": "Integrar orientação enxuta e portátil de design, prova, simplificação, segurança e correção contínua.",
      "result": "Integrar orientação enxuta e portátil de design, prova, simplificação, segurança e correção contínua.",
      "covers": [
        "REQ-006",
        "REQ-007",
        "REQ-008",
        "REQ-011",
        "REQ-012"
      ],
      "depends_on": [],
      "files": [
        "skills/homologar-sistema/SKILL.md",
        "skills/sdd-planning/SKILL.md",
        "skills/executar-plano/SKILL.md",
        "skills/design-projeto/SKILL.md"
      ],
      "action": "Integrar orientação enxuta e portátil de design, prova, simplificação, segurança e correção contínua.",
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
      "risk_seam": "skills-integradas"
    }
  ]
}
---
# P04 — skills-integradas

Responsável: skills.

Integrar orientação enxuta e portátil de design, prova, simplificação, segurança e correção contínua.

Implementação independente dentro do ownership; integração de interfaces entre P01/P02/P03 antes da validação final. Executar testes focais durante edição. P05 executa suite final, race, vet, pacote e jornada pública. Não duplicar revisão de trechos inalterados.

