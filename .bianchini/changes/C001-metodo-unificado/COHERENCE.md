---
{
  "approval": {
    "decided_at": "2026-09-08T22:19:17+00:00",
    "decided_by": "agent:root",
    "digest": "a7e2d2e383f022683c6117e73699b14673f0f8f57a16e04094672a6ff7beba79",
    "kind": "technical_decision"
  },
  "artifact_manifest": {
    "ARCHITECTURE.md": "43ed75572a9e0332523ed6cce3d258f0f24da381a02090a88e8562c7cb52f269",
    "RESEARCH.md": "1bd1aed85f03cbacbd9a43f6b71f8c41f1b5d76b9ff52cce8ed02f06e8d6b88f",
    "ROADMAP.md": "4c7d2da29d4396f68fcb45aebdacb58f58318ae16764b146ed984f1146ac9c4f",
    "SCOPE.md": "a349f8dfb46c39834b7e0268d6c39c66655210446b085f278abac8a97f8029f3",
    "SYSTEM_MODEL.md": "62ca1f0c1eb22043c801f0556f257a1260088bd4cc9a62da427b9f37207ed9a0",
    "plans/P01-metodo-unico/PLAN.md": "465fc1d270226fbc4f22a6f9448981d5f5a5961ee1d435e3627df2ec98de7f52",
    "plans/P02-workspace-coeso/PLAN.md": "7a370a7062feff67536d7f45b43f6f7237a3bb7c4ca36a7ba9b90ded1c9b76d0",
    "plans/P03-garantias-verificaveis/PLAN.md": "01e4f9243cf84f6d5df1765be4c8b3e9dd2534d81f1cbfd594f0f51bd1c60d3e",
    "plans/P04-skills-integradas/PLAN.md": "fe3648cd51070d5f6f1f93869203a3c996870528c6aa5b53096cabab69f7c6de",
    "plans/P05-integracao-distribuicao/PLAN.md": "d59839f737a40542cbc214a4fe13fd5b5b7c0646a91ac439a5d068b77b45d06a"
  },
  "change": "C001-metodo-unificado",
  "digest": "a7e2d2e383f022683c6117e73699b14673f0f8f57a16e04094672a6ff7beba79",
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
      "scenarios": [
        {
          "evidence_kinds": [
            "observation",
            "log"
          ],
          "expected": "Retirar gerações antigas e tornar contrato/ajuda/testes atuais independentes do oráculo.",
          "id": "SCN-001",
          "platform": "cli",
          "profile": "maintainer",
          "requirements": [
            "REQ-001"
          ],
          "risk": "comando removido ainda acessível ou pacote depender de Python para operar",
          "state": "success-and-rejection"
        }
      ],
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
            "tests/test_cli_help.py",
            "tests/test_method_package.py"
          ],
          "id": "T01",
          "name": "Retirar gerações antigas e tornar contrato/ajuda/testes atuais independentes do oráculo.",
          "result": "Retirar gerações antigas e tornar contrato/ajuda/testes atuais independentes do oráculo.",
          "risk_seam": "metodo-unico",
          "verify": {
            "argv": [
              "python3",
              "-B",
              "-m",
              "unittest",
              "tests.test_cli_help",
              "tests.test_method_package"
            ],
            "cwd": ".",
            "kind": "command",
            "proves": "Regressões nativas das responsabilidades alteradas e integração da CLI.",
            "timeout_seconds": 300
          }
        }
      ],
      "verifications": [
        "python3 -B -m unittest tests.test_cli_help tests.test_method_package"
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
      "scenarios": [
        {
          "evidence_kinds": [
            "observation",
            "log"
          ],
          "expected": "Centralizar caminhos, reunir plano/resultado, aceitar somente contrato atual e preservar transações.",
          "id": "SCN-001",
          "platform": "cli",
          "profile": "maintainer",
          "requirements": [
            "REQ-002",
            "REQ-003"
          ],
          "risk": "plano, resultado ou recuperação usar caminho divergente",
          "state": "success-and-rejection"
        }
      ],
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
              "./internal/workspace",
              "./internal/gokernel",
              "-run",
              "TestContext|TestModel|TestCoherence|TestPlan|TestClose|TestExecutionWorkspace|TestRoadmap",
              "-count=1"
            ],
            "cwd": ".",
            "kind": "command",
            "proves": "Regressões nativas das responsabilidades alteradas e integração da CLI.",
            "timeout_seconds": 300
          }
        }
      ],
      "verifications": [
        "go test ./internal/workspace ./internal/gokernel -run 'TestContext|TestModel|TestCoherence|TestPlan|TestClose|TestExecutionWorkspace|TestRoadmap' -count=1"
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
      "scenarios": [
        {
          "evidence_kinds": [
            "observation",
            "log"
          ],
          "expected": "Implementar proveniência honesta e cobertura obrigatória de homologação com testes positivos e negativos.",
          "id": "SCN-001",
          "platform": "cli",
          "profile": "maintainer",
          "requirements": [
            "REQ-004",
            "REQ-005"
          ],
          "risk": "selo ou fechamento aceitar alegação sem evidência atual",
          "state": "success-and-rejection"
        }
      ],
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
            "internal/acceptance/scenarios.go",
            "internal/gokernel/scope.go",
            "internal/gokernel/scope_manifest.go",
            "internal/gokernel/homologation.go",
            "internal/gokernel/verification_release.go",
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
              "./internal/acceptance",
              "./internal/gokernel",
              "-run",
              "TestScope|TestHomologation|TestReleaseRejects|TestManualProof|TestTypedLifecycle",
              "-count=1"
            ],
            "cwd": ".",
            "kind": "command",
            "proves": "Regressões nativas das responsabilidades alteradas e integração da CLI.",
            "timeout_seconds": 300
          }
        }
      ],
      "verifications": [
        "go test ./internal/acceptance ./internal/gokernel -run 'TestScope|TestHomologation|TestReleaseRejects|TestManualProof|TestTypedLifecycle' -count=1"
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
      "scenarios": [
        {
          "evidence_kinds": [
            "observation",
            "log"
          ],
          "expected": "Integrar orientação enxuta e portátil de design, prova, simplificação, segurança e correção contínua.",
          "id": "SCN-001",
          "platform": "cli",
          "profile": "maintainer",
          "requirements": [
            "REQ-006",
            "REQ-007",
            "REQ-008",
            "REQ-011",
            "REQ-012"
          ],
          "risk": "skill omitir teste real, simplificação, revisão ou correção de defeito",
          "state": "success-and-rejection"
        }
      ],
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
              "python3",
              "-B",
              "-m",
              "unittest",
              "tests.test_method_package"
            ],
            "cwd": ".",
            "kind": "command",
            "proves": "Regressões nativas das responsabilidades alteradas e integração da CLI.",
            "timeout_seconds": 300
          }
        }
      ],
      "verifications": [
        "python3 -B -m unittest tests.test_method_package"
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
      "scenarios": [
        {
          "evidence_kinds": [
            "observation",
            "log"
          ],
          "expected": "Integrar, modularizar distribuição quando útil, validar jornada real e pacote nas plataformas, atualizar 1.1.0 e entregar commits/push.",
          "id": "SCN-001",
          "platform": "cli",
          "profile": "maintainer",
          "requirements": [
            "REQ-009",
            "REQ-010"
          ],
          "risk": "pacote não executar jornada ou regressão escapar da integração",
          "state": "success-and-rejection"
        }
      ],
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
  "review_input_digest": "fbc9c957803752f036310e853d627ef839bfa7af20ee33fe053364e85ab6d741",
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
    "input_digest": "c1c05757bb8388a0b85e7fd8fd6b76ef4c0e64984691a08959ba91f27f32212c",
    "prompt_digest": "10e949c274de25732eb9798f93912477bd8b5534c43c3f84a7d34a7f8a865e81",
    "sources_digest": "2d2aa770fca93d794d20af6a6c798b60bb13278c9d129f9b9993143a2fb0a81e"
  },
  "spec_base_digest": "2c3effa6cac92be128ed68e7733b5ed057b027c01006219120d6ba2d177c335f",
  "spec_contract": 1,
  "spec_diff_digest": "06780e509be0bee75211851c0ca29d41967714fad03aa9dca97f4e0fb3ffca6c",
  "spec_manifest_digest": "260aff80512218409d4b789373c73bb12b96b163b2af68aaef6c9c925812aa52",
  "spec_target_digest": "ef163ccbb40b53b50761d283511bbcfb3d4aeab8430ec7f93be8e5ac0b7dc037",
  "stale_plans": [],
  "status": "approved",
  "structural_only": false,
  "updated_at": "2026-09-08T22:19:17+00:00"
}
---

# Coerência

Status: approved.

## Impact Radius

Ainda não calculado para uma mudança executada.
