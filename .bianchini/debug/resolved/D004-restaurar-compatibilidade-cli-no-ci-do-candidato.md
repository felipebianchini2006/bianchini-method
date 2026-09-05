---
{
  "actual": "CI falha em test_golden_behavior_fixtures_pass_on_python_oracle sem mostrar a diferença",
  "created_at": "2026-09-05T12:15:13+00:00",
  "docviva": {
    "after_digest": "240d6f555a63d2b35288f2d62f8a34d88b01a6d8eb7d1bbecb68aa6a6f4e600e",
    "artifacts": [],
    "before_digest": "240d6f555a63d2b35288f2d62f8a34d88b01a6d8eb7d1bbecb68aa6a6f4e600e",
    "changed": [],
    "created": [],
    "justification": "Restaura ordenação e isolamento do harness sem alterar conteúdo migrado, escopo ou arquitetura.",
    "kind": "internal",
    "modified": [],
    "outcome": "not_applicable",
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
    "Diferença Python 3.13.13/3.13.15 não explica a falha remota; log identifica ordem de arquivos. Descoberta Git foi defeito adicional, não a causa remota."
  ],
  "environment": "GitHub Ubuntu, Python 3.13.15; local macOS Python 3.13.13",
  "events": [
    {
      "at": "2026-09-05T12:19:46+00:00",
      "event": "reproduced",
      "evidence": "85 fixtures passam no macOS; Linux reproduz erro Git na fronteira do filesystem. Novo teste demonstra descoberta indevida de repositório pai.",
      "fingerprint": "528248a1fe96fabe67edeb8e72593606fe58961a3df5cfccb473b065a0c1e1aa",
      "proof_id": ""
    },
    {
      "at": "2026-09-05T12:20:07+00:00",
      "event": "diagnosed",
      "evidence": "Sondagem Linux: erro Git em tmpfs; mesma fixture passa com GIT_CEILING_DIRECTORIES. Regressão local falha ao descobrir repositório pai.",
      "fingerprint": "528248a1fe96fabe67edeb8e72593606fe58961a3df5cfccb473b065a0c1e1aa",
      "proof_id": ""
    },
    {
      "at": "2026-09-05T12:20:07+00:00",
      "event": "red",
      "evidence": "Regressão real: fixture destinada a não-repositório herda Git de diretório pai.",
      "fingerprint": "528248a1fe96fabe67edeb8e72593606fe58961a3df5cfccb473b065a0c1e1aa",
      "proof_id": "proof-5879fccf7c6fcdca8cf05295838e704a"
    },
    {
      "at": "2026-09-05T12:20:07+00:00",
      "event": "fixing",
      "evidence": "Confinar descoberta Git na raiz temporária; preservar comparação exata de erros e mutações.",
      "fingerprint": "528248a1fe96fabe67edeb8e72593606fe58961a3df5cfccb473b065a0c1e1aa",
      "proof_id": ""
    },
    {
      "at": "2026-09-05T12:20:17+00:00",
      "event": "green",
      "evidence": "Mesmo teste RED passa após confinar descoberta Git; arquivo de regressão preservado.",
      "fingerprint": "b60bc64c5fbbfa41a4b0b373d7128490157cedce1d9f2a9046cfa1ca9fb577b6",
      "proof_id": "proof-520a402b4266d874f1b712aba9094fe5"
    },
    {
      "at": "2026-09-05T12:24:33+00:00",
      "event": "green",
      "evidence": "Regressão Git preservada passa após patch final; regressão de migração falhou nas duas ordens antes do patch e passou depois. CI diagnóstico 33965647402 confirma success-migration como falha remota.",
      "fingerprint": "77a314c3242b7b6ed764a7715d52af123c110450d349de2f11d03736a2770b2b",
      "proof_id": "proof-7896cef2df69cd15d722745b5ff24174"
    },
    {
      "at": "2026-09-05T12:26:31+00:00",
      "event": "regression_checked",
      "evidence": "Executar suíte completa sobre o patch final; Go nativo inalterado e aprovado no CI diagnóstico a1bdc7d.",
      "fingerprint": "77a314c3242b7b6ed764a7715d52af123c110450d349de2f11d03736a2770b2b",
      "proof_id": "proof-85fb91288a3818923f0b09208417fe47"
    },
    {
      "at": "2026-09-05T12:27:13+00:00",
      "event": "documented",
      "evidence": "Causa remota, regressão de enumeração, isolamento Git e limites registrados em reports/v1/ci-followup.md. Suíte completa executada pelo checkpoint regression_checked passou; Linux Python 3.13.15 passou 85 fixtures.",
      "fingerprint": "77a314c3242b7b6ed764a7715d52af123c110450d349de2f11d03736a2770b2b",
      "proof_id": ""
    },
    {
      "at": "2026-09-05T12:27:43+00:00",
      "event": "green",
      "evidence": "GREEN repetido no ambiente estável de fechamento; suíte completa anterior passou.",
      "fingerprint": "77a314c3242b7b6ed764a7715d52af123c110450d349de2f11d03736a2770b2b",
      "proof_id": "proof-d6f63b07bfa81683a0457d4ed2988b79"
    },
    {
      "at": "2026-09-05T12:27:44+00:00",
      "event": "regression_checked",
      "evidence": "Suíte completa passou em proof-85fb91288a3818923f0b09208417fe47. Revalidar regressões focais e GREEN no mesmo ambiente do fechamento; flags BM da suíte alteravam fingerprint ambiental.",
      "fingerprint": "77a314c3242b7b6ed764a7715d52af123c110450d349de2f11d03736a2770b2b",
      "proof_id": "proof-f0ed72c4b7c65e6558a1e5e2b5612b21"
    },
    {
      "at": "2026-09-05T12:27:44+00:00",
      "event": "documented",
      "evidence": "reports/v1/ci-followup.md registra causa e limites.",
      "fingerprint": "77a314c3242b7b6ed764a7715d52af123c110450d349de2f11d03736a2770b2b",
      "proof_id": ""
    }
  ],
  "expected": "Fixtures públicas passam com Python 3.13 no CI e permitem executar a jornada Go",
  "experiments": [
    "Executar review-package em tmpfs e dentro de repositório pai; limitar descoberta corrige ambos"
  ],
  "finished_at": "2026-09-05T12:27:44+00:00",
  "green": "GREEN repetido no ambiente estável de fechamento; suíte completa anterior passou.",
  "hypotheses": [
    "A fixture sem Git depende da descoberta ambiental do Git fora do diretório temporário isolado"
  ],
  "id": "D004-restaurar-compatibilidade-cli-no-ci-do-candidato",
  "neighboring_regressions": [
    "Suíte completa: migração check/apply em duas ordens, fixtures Python, compatibilidade, jornada pública Go e demais 39 grupos.",
    "Migração check/apply, ordenação em dois filesystems simulados, hashes e preservação .planning."
  ],
  "objective": "Restaurar compatibilidade CLI no CI do candidato 1.0",
  "origin_evidence": null,
  "origin_refs": null,
  "reason": "Correções reproduzidas com RED/GREEN e regressões; suíte completa passou.",
  "red": "Regressão real: fixture destinada a não-repositório herda Git de diretório pai.",
  "regression_contract": {
    "argv": [
      "python3",
      "-B",
      "-m",
      "unittest",
      "tests.test_cli_contract.CliContractScenarios.test_fixture_git_discovery_does_not_escape_its_temporary_root"
    ],
    "failure_pattern": "fixture discovered an unrelated parent Git repository",
    "test_file": "tests/test_cli_contract.py",
    "test_sha256": "e4892cb6ba56439c43f56f64452ba7d0c912f21e22b46095d88a064504e2651b"
  },
  "relation": null,
  "residual_risk": "CI final ainda confirmará Ubuntu x64 e Windows; não inferir sucesso remoto da execução local.",
  "root_cause": "A migração Python preservava ordem de os.walk, divergindo do contrato determinístico e manifesto por último do Go. Separadamente, o harness não confinava descoberta Git à raiz temporária.",
  "schema_version": 1,
  "stage": "documented",
  "status": "resolved",
  "updated_at": "2026-09-05T12:27:44+00:00"
}
---

# Debug D004-restaurar-compatibilidade-cli-no-ci-do-candidato

Restaurar compatibilidade CLI no CI do candidato 1.0
