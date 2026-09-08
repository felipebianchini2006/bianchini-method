---
{
  "schema_version": 2,
  "id": "P01",
  "status": "planned",
  "result": "Retirar gerações antigas e tornar contrato/ajuda/testes atuais independentes do oráculo.",
  "requirements": [
    "REQ-001"
  ],
  "acceptance": [
    "Um único método Go, removendo oráculo Python, comandos antigos, standalone, overlay e migração de gerações anteriores."
  ],
  "depends_on": [],
  "provides": [
    "method_metodo_unico"
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
          "id": "method_metodo_unico"
        }
      ]
    }
  },
  "migrations": [],
  "effects": [],
  "rollback": "Reverter somente o commit desta entrega, preservando documentação e provas; não reescrever histórico.",
  "verifications": [
    "python3 -B -m unittest tests.test_cli_help tests.test_method_package"
  ],
  "future_constraints": [
    "Não restaurar compatibilidade de gerações retiradas."
  ],
  "execution": "grouped",
  "review": "plan_gate",
  "tasks": [
    {
      "id": "T01",
      "name": "Retirar gerações antigas e tornar contrato/ajuda/testes atuais independentes do oráculo.",
      "result": "Retirar gerações antigas e tornar contrato/ajuda/testes atuais independentes do oráculo.",
      "covers": [
        "REQ-001"
      ],
      "depends_on": [],
      "files": [
        "internal/gokernel/cli.go",
        "contracts/cli-surfaces.json",
        "tests/test_cli_help.py",
        "tests/test_method_package.py"
      ],
      "action": "Retirar gerações antigas e tornar contrato/ajuda/testes atuais independentes do oráculo.",
      "verify": {
        "kind": "command",
        "argv": [
          "python3",
          "-B",
          "-m",
          "unittest",
          "tests.test_cli_help",
          "tests.test_method_package"
        ],
        "cwd": ".",
        "timeout_seconds": 300,
        "cache": "fresh",
        "proves": "Regressões nativas das responsabilidades alteradas e integração da CLI."
      },
      "done": "Implementação revisada, verificações pertinentes aprovadas, comportamento demonstrado e limitações registradas.",
      "risk_seam": "metodo-unico"
    }
  ],
  "scenarios": [
    {
      "id": "SCN-001",
      "requirements": [
        "REQ-001"
      ],
      "platform": "cli",
      "profile": "maintainer",
      "state": "success-and-rejection",
      "expected": "Retirar gerações antigas e tornar contrato/ajuda/testes atuais independentes do oráculo.",
      "risk": "comando removido ainda acessível ou pacote depender de Python para operar",
      "evidence_kinds": [
        "observation",
        "log"
      ]
    }
  ]
}
---
# P01 — metodo-unico

Responsável: single_method.

Retirar gerações antigas e tornar contrato/ajuda/testes atuais independentes do oráculo.

Implementação independente dentro do ownership; integração de interfaces entre P01/P02/P03 antes da validação final. Executar testes focais durante edição. P05 executa suite final, race, vet, pacote e jornada pública. Não duplicar revisão de trechos inalterados.

