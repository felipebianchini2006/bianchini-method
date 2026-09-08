---
{
  "candidate": {
    "build": ".bianchini/.runtime/distribution/bianchini-method_1.1.0_darwin-arm64.tar.gz",
    "checksum": "2b6d407d5e33555047615c5c11d96e3326208e5dfa76180bd6d472d7e7275a2f",
    "id": "RC-504a61275f03",
    "kind": "file",
    "package_digest": "a7e2d2e383f022683c6117e73699b14673f0f8f57a16e04094672a6ff7beba79",
    "revision": "4d750e9f0339e1c1911480c0dcb26340daa46d85"
  },
  "change": "C001-metodo-unificado",
  "delivery": "ready",
  "fingerprint": "504a61275f039e77aca80dcc16ce247d77dcbdd788d58968434f9fa992cd2f0a",
  "manual_requirements": [],
  "package_digest": "a7e2d2e383f022683c6117e73699b14673f0f8f57a16e04094672a6ff7beba79",
  "proof_ids": [
    "proof-1d1f40f0c0ced92fc66b4a5b7c1609fa",
    "proof-9ff6b8c3cb6209c2a0bd07b111d2f310",
    "proof-cbca59e888a5975584b58692274f4081",
    "proof-31be76fed9cf6b4b6017641ed2654ccd",
    "proof-e8aa13035d53b9b43da21c63f0d30f4e",
    "proof-22a5ce831b4124b15e28705d4bea3f7e"
  ],
  "review_id": "review-c196f45a04fe7f4721166d35cd77f0f5",
  "reviewed_at": "2026-09-08T22:33:34+00:00",
  "scenario_requirements": [
    {
      "evidence_kinds": [
        "observation",
        "log"
      ],
      "expected": "Retirar gerações antigas e tornar contrato/ajuda/testes atuais independentes do oráculo.",
      "id": "SCN-001",
      "plan": "P01",
      "platform": "cli",
      "profile": "maintainer",
      "requirements": [
        "REQ-001"
      ],
      "risk": "comando removido ainda acessível ou pacote depender de Python para operar",
      "state": "success-and-rejection"
    },
    {
      "evidence_kinds": [
        "observation",
        "log"
      ],
      "expected": "Centralizar caminhos, reunir plano/resultado, aceitar somente contrato atual e preservar transações.",
      "id": "SCN-001",
      "plan": "P02",
      "platform": "cli",
      "profile": "maintainer",
      "requirements": [
        "REQ-002",
        "REQ-003"
      ],
      "risk": "plano, resultado ou recuperação usar caminho divergente",
      "state": "success-and-rejection"
    },
    {
      "evidence_kinds": [
        "observation",
        "log"
      ],
      "expected": "Implementar proveniência honesta e cobertura obrigatória de homologação com testes positivos e negativos.",
      "id": "SCN-001",
      "plan": "P03",
      "platform": "cli",
      "profile": "maintainer",
      "requirements": [
        "REQ-004",
        "REQ-005"
      ],
      "risk": "selo ou fechamento aceitar alegação sem evidência atual",
      "state": "success-and-rejection"
    },
    {
      "evidence_kinds": [
        "observation",
        "log"
      ],
      "expected": "Integrar orientação enxuta e portátil de design, prova, simplificação, segurança e correção contínua.",
      "id": "SCN-001",
      "plan": "P04",
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
    },
    {
      "evidence_kinds": [
        "observation",
        "log"
      ],
      "expected": "Integrar, modularizar distribuição quando útil, validar jornada real e pacote nas plataformas, atualizar 1.1.0 e entregar commits/push.",
      "id": "SCN-001",
      "plan": "P05",
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
  "schema_version": 1,
  "source_fingerprint": "f1dc63eb8a9257f5943f6ce04838c173d664752ac73e3bd7c7601b878956c656",
  "status": "reviewed",
  "verified_at": "2026-09-08T22:33:34+00:00"
}
---

# Release candidate

Baseline automatizada e revisão final aprovadas.
