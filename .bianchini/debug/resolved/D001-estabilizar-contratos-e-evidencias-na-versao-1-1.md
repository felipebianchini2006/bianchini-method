---
{
  "actual": "Validação tardia, PNG truncado aceito, caminhos arquivados inválidos e executor removido ainda referenciado",
  "created_at": "2026-09-09T21:09:24+00:00",
  "docviva": {
    "after_digest": "ec569f8b78b2f71c0372c49dcce1f1730c48be7931366958be71051427bb778f",
    "artifacts": [
      ".bianchini/current/ARCHITECTURE.md"
    ],
    "before_digest": "35f69cf1e0cafedf62b0a6d5b78ab7c931672cc91724c87dc20555461a96bb12",
    "changed": [
      ".bianchini/current/ARCHITECTURE.md"
    ],
    "created": [],
    "justification": "Documentados domínio único de aceite, índice central e arquivo, screenshots e compatibilidade dos documentos completos da 1.1.0.",
    "kind": "architecture",
    "modified": [
      ".bianchini/current/ARCHITECTURE.md"
    ],
    "outcome": "updated",
    "removed": [],
    "required": true,
    "schema_version": 1,
    "status": "verified"
  },
  "docviva_before": {
    ".bianchini/current/ARCHITECTURE.md": "43ed75572a9e0332523ed6cce3d258f0f24da381a02090a88e8562c7cb52f269",
    ".bianchini/current/SYSTEM_MODEL.md": "62ca1f0c1eb22043c801f0556f257a1260088bd4cc9a62da427b9f37207ed9a0",
    ".bianchini/current/specs/MANIFEST.json": "260aff80512218409d4b789373c73bb12b96b163b2af68aaef6c9c925812aa52",
    ".bianchini/current/specs/method.md": "151d935641de484e47c9459cee78e980469d699013e05ea555fc78c63e1e1aae"
  },
  "docviva_contract": 1,
  "eliminated_hypotheses": [],
  "environment": "Go local; base 22279ca",
  "events": [
    {
      "at": "2026-09-09T21:10:21+00:00",
      "event": "reproduced",
      "evidence": "Validadores divergentes, screenshot truncado, runner obsoleto e 17 caminhos antigos confirmados na base.",
      "fingerprint": "ad08517b1d2c782c8c3f5b9a2376ab3bb56e75722443f55e48b15f61042ad394",
      "proof_id": ""
    },
    {
      "at": "2026-09-09T21:10:21+00:00",
      "event": "diagnosed",
      "evidence": "Chamadores e escritores inspecionados.",
      "fingerprint": "ad08517b1d2c782c8c3f5b9a2376ab3bb56e75722443f55e48b15f61042ad394",
      "proof_id": ""
    },
    {
      "at": "2026-09-09T21:10:23+00:00",
      "event": "red",
      "evidence": "Regressões determinísticas das lacunas confirmadas.",
      "fingerprint": "ad08517b1d2c782c8c3f5b9a2376ab3bb56e75722443f55e48b15f61042ad394",
      "proof_id": "proof-e6991ee0fe3dee91eb76e8caa3f005eb"
    },
    {
      "at": "2026-09-09T21:11:22+00:00",
      "event": "fixing",
      "evidence": "RED reproduziu parsing permissivo, PNG incompleto e plano antigo ignorado.",
      "fingerprint": "ad08517b1d2c782c8c3f5b9a2376ab3bb56e75722443f55e48b15f61042ad394",
      "proof_id": ""
    },
    {
      "at": "2026-09-09T21:20:33+00:00",
      "event": "green",
      "evidence": "Mesma regressão RED aprovada após integrar acceptance, decode integral e diagnóstico de layout.",
      "fingerprint": "a24f001957ca481832f57b668ec24a9b7af315052c7bc6b8140e1a69768bc42f",
      "proof_id": "proof-336652ac3dfe51c19756fe61a16ac4ec"
    },
    {
      "at": "2026-09-09T21:21:31+00:00",
      "event": "regression_checked",
      "evidence": "Suíte Go completa incluindo ciclo de release, transição de schemas, índices e arquivo.",
      "fingerprint": "a24f001957ca481832f57b668ec24a9b7af315052c7bc6b8140e1a69768bc42f",
      "proof_id": "proof-2b427fe4ea3a9ca10394cb99dd8b3c5c"
    },
    {
      "at": "2026-09-09T21:21:59+00:00",
      "event": "documented",
      "evidence": "Go test completo, race, vet, build, cinco testes Python e jornada pública protocol-test aprovados. CLI 1.1.1 resolveu os 17 logs reais arquivados. Revisão local do diff concluída.",
      "fingerprint": "a24f001957ca481832f57b668ec24a9b7af315052c7bc6b8140e1a69768bc42f",
      "proof_id": ""
    },
    {
      "at": "2026-09-09T21:23:16+00:00",
      "event": "green",
      "evidence": "GREEN repetido com ambiente estável até o fechamento.",
      "fingerprint": "a24f001957ca481832f57b668ec24a9b7af315052c7bc6b8140e1a69768bc42f",
      "proof_id": "proof-0e8876274a21ac8d4ab8409ecc71a3c3"
    },
    {
      "at": "2026-09-09T21:23:43+00:00",
      "event": "regression_checked",
      "evidence": "Suíte completa no mesmo ambiente do fechamento.",
      "fingerprint": "a24f001957ca481832f57b668ec24a9b7af315052c7bc6b8140e1a69768bc42f",
      "proof_id": "proof-7880a787747ba78be74f1f38314cddfe"
    },
    {
      "at": "2026-09-09T21:23:43+00:00",
      "event": "documented",
      "evidence": "Go test, race, vet, build, cinco testes Python, jornada pública de protocolo e leitura dos 17 logs reais aprovados.",
      "fingerprint": "a24f001957ca481832f57b668ec24a9b7af315052c7bc6b8140e1a69768bc42f",
      "proof_id": ""
    }
  ],
  "expected": "Planejamento valida aceite completo; evidências íntegras e localizáveis; formatos antigos têm diagnóstico explícito",
  "experiments": [],
  "finished_at": "2026-09-09T21:23:43+00:00",
  "green": "GREEN repetido com ambiente estável até o fechamento.",
  "hypotheses": [],
  "id": "D001-estabilizar-contratos-e-evidencias-na-versao-1-1",
  "neighboring_regressions": [
    "Planos e escopos completos da 1.1.0 continuam válidos; logs alterados são recusados; fechamento e reabertura preservados.",
    "Compatibilidade 1.1.0, índices e logs arquivados, cenários, screenshots e ciclo completo."
  ],
  "objective": "Estabilizar contratos e evidências na versão 1.1.1",
  "origin_evidence": null,
  "origin_refs": null,
  "reason": null,
  "red": "Regressões determinísticas das lacunas confirmadas.",
  "regression_contract": {
    "argv": [
      "go",
      "test",
      "./internal/gokernel",
      "-run",
      "^TestRelease111Regressions$",
      "-count=1"
    ],
    "failure_pattern": "regression111",
    "test_file": "internal/gokernel/release111_regression_test.go",
    "test_sha256": "abeb8fd61897133833b80b009db324227f29db114ef3d19282314c09761b4c35"
  },
  "relation": null,
  "residual_risk": "Formatos 1.0 e anteriores exigem transição revisada. Revisão da jornada é sintética de protocolo. CI remota será verificada após push.",
  "root_cause": "Acceptance ausente do planejamento; imagem validada só por cabeçalho; caminhos dependem de changes; remoção deixou contratos antigos sem diagnóstico.",
  "schema_version": 1,
  "stage": "documented",
  "status": "resolved",
  "updated_at": "2026-09-09T21:23:43+00:00"
}
---

# Debug D001-estabilizar-contratos-e-evidencias-na-versao-1-1

Estabilizar contratos e evidências na versão 1.1.1
