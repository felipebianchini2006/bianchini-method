---
{
  "approval": {
    "decided_at": "2026-09-08T21:56:14+00:00",
    "decided_by": "agent:root",
    "digest": "30c22e028d12986d666fb15c787fe37516339fa3aef10b4fc538e703ab18950f",
    "kind": "technical_decision"
  },
  "artifact_manifest": {
    "ARCHITECTURE.md": "43ed75572a9e0332523ed6cce3d258f0f24da381a02090a88e8562c7cb52f269",
    "RESEARCH.md": "1bd1aed85f03cbacbd9a43f6b71f8c41f1b5d76b9ff52cce8ed02f06e8d6b88f",
    "ROADMAP.md": "4c7d2da29d4396f68fcb45aebdacb58f58318ae16764b146ed984f1146ac9c4f",
    "SCOPE.md": "a349f8dfb46c39834b7e0268d6c39c66655210446b085f278abac8a97f8029f3",
    "SYSTEM_MODEL.md": "62ca1f0c1eb22043c801f0556f257a1260088bd4cc9a62da427b9f37207ed9a0",
    "plans/P01-metodo-unico.md": "95746423b12bdff1341550c10c48aa3bb1bee8e528a3c18d2ffede767b8014c1",
    "plans/P02-workspace-coeso.md": "14ff5049b30b7996c449e81bdb05290094cdaee50483ee4aed0b4887d2c3deb4",
    "plans/P03-garantias-verificaveis.md": "1d79e60d374c52b2ac7fa9a2cfce9fbcd1a9553e0783f3d8f63fb599bb0b5de0",
    "plans/P04-skills-integradas.md": "b87ed2c45311ee35b73a9d60c211d014eee3fa471724314210ab07c34f9c61c3",
    "plans/P05-integracao-distribuicao.md": "e9908f05757236e824b4e3f2aa2c74d4ea1adaa54809b0326453dda1c4407efc"
  },
  "change": "C001-metodo-unificado",
  "digest": "30c22e028d12986d666fb15c787fe37516339fa3aef10b4fc538e703ab18950f",
  "findings": [],
  "impact": null,
  "model": {
    "current": "d51ceb25e1ba2ab66e5ea1b297f5cea13629e187d4c1edc2b1ce9c174825334a",
    "expected": "d0a64fc593ae68151905dbf0ee3f83b3b9b6680ff54d572acb916d7966e69b08"
  },
  "planning_contract": 2,
  "plans": [
    {
      "acceptance": [
        "Um único método Go, removendo oráculo Python, comandos antigos, standalone, overlay e migração de gerações anteriores."
      ],
      "consumes": [],
      "data": [],
      "depends_on": [],
      "effects": [],
      "execution": "grouped",
      "future_constraints": [
        "Não restaurar compatibilidade de gerações retiradas."
      ],
      "id": "P01",
      "interfaces": [],
      "migrations": [],
      "model_delta": {
        "contracts": {
          "add": [
            {
              "id": "method_metodo_unico"
            }
          ]
        }
      },
      "modules": [],
      "ownership": [],
      "provides": [
        "method_metodo_unico"
      ],
      "requirements": [
        "REQ-001"
      ],
      "result": "Retirar gerações antigas e tornar contrato/ajuda/testes atuais independentes do oráculo.",
      "review": "plan_gate",
      "rollback": "Reverter somente o commit desta entrega, preservando documentação e provas; não reescrever histórico.",
      "schema_version": 2,
      "status": "planned",
      "tasks": [
        {
          "action": "Retirar gerações antigas e tornar contrato/ajuda/testes atuais independentes do oráculo.",
          "covers": [
            "REQ-001"
          ],
          "depends_on": [],
          "done": "Implementação revisada, verificações pertinentes aprovadas, comportamento demonstrado e limitações registradas.",
          "files": [
            "internal/gokernel/cli.go",
            "contracts/cli-surfaces.json",
            "scripts/generate_cli_help.py"
          ],
          "id": "T01",
          "name": "Retirar gerações antigas e tornar contrato/ajuda/testes atuais independentes do oráculo.",
          "result": "Retirar gerações antigas e tornar contrato/ajuda/testes atuais independentes do oráculo.",
          "risk_seam": "metodo-unico",
          "verify": {
            "argv": [
              "go",
              "test",
              "./..."
            ],
            "cwd": ".",
            "kind": "command",
            "proves": "Regressões nativas das responsabilidades alteradas e integração da CLI.",
            "timeout_seconds": 300
          }
        }
      ],
      "verifications": [
        "go test ./...",
        "go vet ./..."
      ]
    },
    {
      "acceptance": [
        "Documentação e evidências do projeto em .bianchini; plano e resultado juntos; caminhos centralizados e estrutura legível.",
        "Responsabilidades Go separadas em módulos úteis, tipos nos novos contratos sensíveis, sem quebrar atomicidade, locks e recuperação."
      ],
      "consumes": [],
      "data": [],
      "depends_on": [],
      "effects": [],
      "execution": "grouped",
      "future_constraints": [
        "Não restaurar compatibilidade de gerações retiradas."
      ],
      "id": "P02",
      "interfaces": [],
      "migrations": [],
      "model_delta": {
        "contracts": {
          "add": [
            {
              "id": "method_workspace_coeso"
            }
          ]
        }
      },
      "modules": [],
      "ownership": [],
      "provides": [
        "method_workspace_coeso"
      ],
      "requirements": [
        "REQ-002",
        "REQ-003"
      ],
      "result": "Centralizar caminhos, reunir plano/resultado, aceitar somente contrato atual e preservar transações.",
      "review": "plan_gate",
      "rollback": "Reverter somente o commit desta entrega, preservando documentação e provas; não reescrever histórico.",
      "schema_version": 2,
      "status": "planned",
      "tasks": [
        {
          "action": "Centralizar caminhos, reunir plano/resultado, aceitar somente contrato atual e preservar transações.",
          "covers": [
            "REQ-002",
            "REQ-003"
          ],
          "depends_on": [],
          "done": "Implementação revisada, verificações pertinentes aprovadas, comportamento demonstrado e limitações registradas.",
          "files": [
            "internal/gokernel/workspace.go",
            "internal/gokernel/model.go",
            "internal/gokernel/plan_files.go"
          ],
          "id": "T01",
          "name": "Centralizar caminhos, reunir plano/resultado, aceitar somente contrato atual e preservar transações.",
          "result": "Centralizar caminhos, reunir plano/resultado, aceitar somente contrato atual e preservar transações.",
          "risk_seam": "workspace-coeso",
          "verify": {
            "argv": [
              "go",
              "test",
              "./..."
            ],
            "cwd": ".",
            "kind": "command",
            "proves": "Regressões nativas das responsabilidades alteradas e integração da CLI.",
            "timeout_seconds": 300
          }
        }
      ],
      "verifications": [
        "go test ./...",
        "go vet ./..."
      ]
    },
    {
      "acceptance": [
        "Selo de escopo distingue integridade, processamento declarado, cobertura registrada por página e revisão semântica; não promete leitura que não verificou.",
        "Requisito, cenário, perfil, plataforma, risco e evidência têm vínculo verificável; cenário obrigatório omitido ou evidência obsoleta bloqueia fechamento."
      ],
      "consumes": [],
      "data": [],
      "depends_on": [],
      "effects": [],
      "execution": "grouped",
      "future_constraints": [
        "Não restaurar compatibilidade de gerações retiradas."
      ],
      "id": "P03",
      "interfaces": [],
      "migrations": [],
      "model_delta": {
        "contracts": {
          "add": [
            {
              "id": "method_garantias_verificaveis"
            }
          ]
        }
      },
      "modules": [],
      "ownership": [],
      "provides": [
        "method_garantias_verificaveis"
      ],
      "requirements": [
        "REQ-004",
        "REQ-005"
      ],
      "result": "Implementar proveniência honesta e cobertura obrigatória de homologação com testes positivos e negativos.",
      "review": "plan_gate",
      "rollback": "Reverter somente o commit desta entrega, preservando documentação e provas; não reescrever histórico.",
      "schema_version": 2,
      "status": "planned",
      "tasks": [
        {
          "action": "Implementar proveniência honesta e cobertura obrigatória de homologação com testes positivos e negativos.",
          "covers": [
            "REQ-004",
            "REQ-005"
          ],
          "depends_on": [],
          "done": "Implementação revisada, verificações pertinentes aprovadas, comportamento demonstrado e limitações registradas.",
          "files": [
            "internal/gokernel/scope.go",
            "internal/gokernel/verification.go",
            "internal/gokernel/release_identity.go"
          ],
          "id": "T01",
          "name": "Implementar proveniência honesta e cobertura obrigatória de homologação com testes positivos e negativos.",
          "result": "Implementar proveniência honesta e cobertura obrigatória de homologação com testes positivos e negativos.",
          "risk_seam": "garantias-verificaveis",
          "verify": {
            "argv": [
              "go",
              "test",
              "./..."
            ],
            "cwd": ".",
            "kind": "command",
            "proves": "Regressões nativas das responsabilidades alteradas e integração da CLI.",
            "timeout_seconds": 300
          }
        }
      ],
      "verifications": [
        "go test ./...",
        "go vet ./..."
      ]
    },
    {
      "acceptance": [
        "Homologação opera aplicação real com ferramentas disponíveis, preferindo browser interno e pedindo instalação só se faltar; corrige defeitos e retesta até conclusão ou bloqueio real.",
        "Planejamento inclui caminho de verificação e provas de viabilidade para premissas incertas de alto impacto antes de liberar dependentes.",
        "Orientações selecionadas de Impeccable, verification-planning, simplify, post-refactor, improve-codebase-architecture e security-audit integradas às skills atuais.",
        "Prontidão operacional proporcional verifica dados, integrações, configuração, implantação/recuperação quando aplicável, sem confundir aceite técnico com deploy.",
        "Simplificação e revisão após refatoração integram execução e correção de bugs; verificação de segurança ao fim do plano é proporcional à superfície alterada."
      ],
      "consumes": [],
      "data": [],
      "depends_on": [],
      "effects": [],
      "execution": "grouped",
      "future_constraints": [
        "Não restaurar compatibilidade de gerações retiradas."
      ],
      "id": "P04",
      "interfaces": [],
      "migrations": [],
      "model_delta": {
        "contracts": {
          "add": [
            {
              "id": "method_skills_integradas"
            }
          ]
        }
      },
      "modules": [],
      "ownership": [],
      "provides": [
        "method_skills_integradas"
      ],
      "requirements": [
        "REQ-006",
        "REQ-007",
        "REQ-008",
        "REQ-011",
        "REQ-012"
      ],
      "result": "Integrar orientação enxuta e portátil de design, prova, simplificação, segurança e correção contínua.",
      "review": "plan_gate",
      "rollback": "Reverter somente o commit desta entrega, preservando documentação e provas; não reescrever histórico.",
      "schema_version": 2,
      "status": "planned",
      "tasks": [
        {
          "action": "Integrar orientação enxuta e portátil de design, prova, simplificação, segurança e correção contínua.",
          "covers": [
            "REQ-006",
            "REQ-007",
            "REQ-008",
            "REQ-011",
            "REQ-012"
          ],
          "depends_on": [],
          "done": "Implementação revisada, verificações pertinentes aprovadas, comportamento demonstrado e limitações registradas.",
          "files": [
            "skills/homologar-sistema/SKILL.md",
            "skills/sdd-planning/SKILL.md",
            "skills/executar-plano/SKILL.md",
            "skills/design-projeto/SKILL.md"
          ],
          "id": "T01",
          "name": "Integrar orientação enxuta e portátil de design, prova, simplificação, segurança e correção contínua.",
          "result": "Integrar orientação enxuta e portátil de design, prova, simplificação, segurança e correção contínua.",
          "risk_seam": "skills-integradas",
          "verify": {
            "argv": [
              "go",
              "test",
              "./..."
            ],
            "cwd": ".",
            "kind": "command",
            "proves": "Regressões nativas das responsabilidades alteradas e integração da CLI.",
            "timeout_seconds": 300
          }
        }
      ],
      "verifications": [
        "go test ./...",
        "go vet ./..."
      ]
    },
    {
      "acceptance": [
        "Distribuição identifica 1.1.0, ajuda deriva da CLI vigente, CI executa testes nativos em Linux/macOS/Windows e valida pacote real.",
        "Avaliações positivas e negativas demonstram omissão de cenários/páginas, evidência inválida, rejeição de formatos antigos e jornada pública real."
      ],
      "consumes": [],
      "data": [],
      "depends_on": [
        "P01",
        "P02",
        "P03",
        "P04"
      ],
      "effects": [],
      "execution": "grouped",
      "future_constraints": [
        "Não restaurar compatibilidade de gerações retiradas."
      ],
      "id": "P05",
      "interfaces": [],
      "migrations": [],
      "model_delta": {
        "contracts": {
          "add": [
            {
              "id": "method_integracao_distribuicao"
            }
          ]
        }
      },
      "modules": [],
      "ownership": [],
      "provides": [
        "method_integracao_distribuicao"
      ],
      "requirements": [
        "REQ-009",
        "REQ-010"
      ],
      "result": "Integrar, modularizar distribuição quando útil, validar jornada real e pacote nas plataformas, atualizar 1.1.0 e entregar commits/push.",
      "review": "plan_gate",
      "rollback": "Reverter somente o commit desta entrega, preservando documentação e provas; não reescrever histórico.",
      "schema_version": 2,
      "status": "planned",
      "tasks": [
        {
          "action": "Integrar, modularizar distribuição quando útil, validar jornada real e pacote nas plataformas, atualizar 1.1.0 e entregar commits/push.",
          "covers": [
            "REQ-009",
            "REQ-010"
          ],
          "depends_on": [],
          "done": "Implementação revisada, verificações pertinentes aprovadas, comportamento demonstrado e limitações registradas.",
          "files": [
            "README.md",
            ".github/workflows/ci.yml",
            "tools/bm-release/main.go",
            "skills/_shared/VERSION"
          ],
          "id": "T01",
          "name": "Integrar, modularizar distribuição quando útil, validar jornada real e pacote nas plataformas, atualizar 1.1.0 e entregar commits/push.",
          "result": "Integrar, modularizar distribuição quando útil, validar jornada real e pacote nas plataformas, atualizar 1.1.0 e entregar commits/push.",
          "risk_seam": "integracao-distribuicao",
          "verify": {
            "argv": [
              "go",
              "test",
              "./..."
            ],
            "cwd": ".",
            "kind": "command",
            "proves": "Regressões nativas das responsabilidades alteradas e integração da CLI.",
            "timeout_seconds": 300
          }
        }
      ],
      "verifications": [
        "go test ./...",
        "go vet ./..."
      ]
    }
  ],
  "review_input_digest": "33010ee9d13db18eafd98f8d0301697ce2ad2ff7e392dd00ec2975bfc98ac6d9",
  "schedule": {
    "plan_waves": [
      [
        "P01",
        "P02",
        "P03",
        "P04"
      ],
      [
        "P05"
      ]
    ],
    "task_waves": {
      "P01": [
        [
          "T01"
        ]
      ],
      "P02": [
        [
          "T01"
        ]
      ],
      "P03": [
        [
          "T01"
        ]
      ],
      "P04": [
        [
          "T01"
        ]
      ],
      "P05": [
        [
          "T01"
        ]
      ]
    }
  },
  "schema_version": 2,
  "semantic": {
    "available": true,
    "findings": [],
    "input_digest": "e0d1206f763ecbe49f5034792566ee4a8a1a147338f4c5f3c08e156b7edb34df",
    "prompt_digest": "c18155143a6fa66ccea2ad829da656ba825c2337414cf06d9bfb621987732a98",
    "sources_digest": "a73c21f1b0c2b7439ef13b533b1dbc0210e20c938ac27082762ff6063eace096"
  },
  "spec_base_digest": "2c3effa6cac92be128ed68e7733b5ed057b027c01006219120d6ba2d177c335f",
  "spec_contract": 1,
  "spec_diff_digest": "06780e509be0bee75211851c0ca29d41967714fad03aa9dca97f4e0fb3ffca6c",
  "spec_manifest_digest": "260aff80512218409d4b789373c73bb12b96b163b2af68aaef6c9c925812aa52",
  "spec_target_digest": "ef163ccbb40b53b50761d283511bbcfb3d4aeab8430ec7f93be8e5ac0b7dc037",
  "stale_plans": [],
  "status": "approved",
  "structural_only": false,
  "updated_at": "2026-09-08T21:56:14+00:00"
}
---

# Coerência

Status: approved.

## Impact Radius

Ainda não calculado para uma mudança executada.
