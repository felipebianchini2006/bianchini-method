---
{
  "actual": "coherence approve aceita P01-fase.md, mas roadmap next-wave rejeita WAVE_INCOMPLETE por identidade inválida",
  "created_at": "2026-09-02T12:11:27+00:00",
  "docviva": {
    "after_digest": "240d6f555a63d2b35288f2d62f8a34d88b01a6d8eb7d1bbecb68aa6a6f4e600e",
    "artifacts": [],
    "before_digest": "240d6f555a63d2b35288f2d62f8a34d88b01a6d8eb7d1bbecb68aa6a6f4e600e",
    "changed": [],
    "created": [],
    "justification": "O fix restaura o contrato já documentado pelo sdd-planning e não altera o modelo atual do produto.",
    "kind": "internal",
    "modified": [],
    "outcome": "no_op",
    "removed": [],
    "required": false,
    "schema_version": 1,
    "status": "verified"
  },
  "docviva_before": {
    ".bianchini/current/ARCHITECTURE.md": "1a303e5e11cc8ffb4b5b57d1e9d6ca44f85f7ba687a05fc04004f171e1266cb0",
    ".bianchini/current/SYSTEM_MODEL.md": "9d6fa478d66dc1a1bca209349b0670a768806158d138048e70fbe56393ad958a",
    ".bianchini/current/specs/MANIFEST.json": "8fe693a685236415f33fea34c70ddc1ce4516e1a02f2df031c3cdf4c972f1be3"
  },
  "docviva_contract": 1,
  "eliminated_hypotheses": [
    "Branch main ou divergência com origin não participa do parser de pacote"
  ],
  "environment": "main 4d099b4; Go kernel 0.5.0; reprodução local determinística",
  "events": [
    {
      "at": "2026-09-02T12:12:55+00:00",
      "event": "reproduced",
      "evidence": "go test ./internal/gokernel -run TestCoherenceSchemaTwoCheckReviewApproveAndStartDescriptivePlan -count=1 =\u003e FAIL com WAVE_INCOMPLETE para P01-fundacao.md",
      "fingerprint": "84b026ccac3f608a565cc868ef24f5470f50a1dde651697e12187e7761ed366d"
    },
    {
      "at": "2026-09-02T12:12:55+00:00",
      "event": "diagnosed",
      "evidence": "coherence loadRoadmapPackage usa plans/P*.md e id do frontmatter; waveRoadmapPlans exige stem igual a Pxx",
      "fingerprint": "84b026ccac3f608a565cc868ef24f5470f50a1dde651697e12187e7761ed366d"
    },
    {
      "at": "2026-09-02T12:12:55+00:00",
      "event": "red",
      "evidence": "Regressão pública adicionada em coherence_test.go falha somente no next-wave após aprovação bem-sucedida",
      "fingerprint": "84b026ccac3f608a565cc868ef24f5470f50a1dde651697e12187e7761ed366d"
    },
    {
      "at": "2026-09-02T12:12:55+00:00",
      "event": "fixing",
      "evidence": "RED capturado no fingerprint 4d099b4 com alteração exclusiva de teste",
      "fingerprint": "84b026ccac3f608a565cc868ef24f5470f50a1dde651697e12187e7761ed366d"
    },
    {
      "at": "2026-09-02T12:29:36+00:00",
      "event": "green",
      "evidence": "Regressão pública, jornada completa Python e Go, context pack e next-wave com P01-health-journey.md passaram",
      "fingerprint": "3346563525a597f4eb1df259146eafb3d26f15a5bf1b92245a16c6e8e93b6132"
    },
    {
      "at": "2026-09-02T12:29:36+00:00",
      "event": "regression_checked",
      "evidence": "39 shards, go test ./..., go test -race ./..., go vet ./... e 78 fixtures Go aprovados",
      "fingerprint": "3346563525a597f4eb1df259146eafb3d26f15a5bf1b92245a16c6e8e93b6132"
    },
    {
      "at": "2026-09-02T12:29:37+00:00",
      "event": "documented",
      "evidence": "skills/sdd-planning/SKILL.md documenta Pxx.md ou Pxx-sufixo.md e vincula o prefixo ao id do frontmatter",
      "fingerprint": "3346563525a597f4eb1df259146eafb3d26f15a5bf1b92245a16c6e8e93b6132"
    }
  ],
  "expected": "Pacote aprovado com plans/P01-fase.md deve passar pelo preflight de execução usando P01 como identidade",
  "experiments": [
    "Aprovar pacote P01-fundacao.md e chamar roadmap next-wave"
  ],
  "finished_at": "2026-09-02T12:29:49+00:00",
  "green": "Regressão pública, jornada completa Python e Go, context pack e next-wave com P01-health-journey.md passaram",
  "hypotheses": [
    "Dois parsers de identidade divergentes permitem aprovação e bloqueiam execução"
  ],
  "id": "D002-aceitar-arquivos-de-plano-com-nome-descritivo-no",
  "neighboring_regressions": [
    "P01.md canônico continua coberto; duplicidade P01.md mais P01-fundacao.md, symlink e drift continuam bloqueados"
  ],
  "objective": "Aceitar arquivos de plano com nome descritivo no contrato 0.4",
  "origin_evidence": null,
  "origin_refs": null,
  "reason": "Identidade de plano resolvida pelo prefixo canônico em todos os consumidores, com caminhos reais no manifesto",
  "red": "Regressão pública adicionada em coherence_test.go falha somente no next-wave após aprovação bem-sucedida",
  "relation": null,
  "residual_risk": "A instalação local existente precisa receber o novo binário e as skills antes de retomar o ConectaMarcenaria",
  "root_cause": "waveRoadmapPlans usa o stem completo como ID e exige wavePlanID exato, enquanto o planejamento documenta e coherence aceita Pxx-slug.md",
  "schema_version": 1,
  "stage": "documented",
  "status": "resolved",
  "updated_at": "2026-09-02T12:29:37+00:00"
}
---

# Debug D002-aceitar-arquivos-de-plano-com-nome-descritivo-no

Aceitar arquivos de plano com nome descritivo no contrato 0.4
