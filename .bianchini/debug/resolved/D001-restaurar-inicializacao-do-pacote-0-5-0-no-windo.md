---
{
  "actual": "Os módulos empacotados bm_close.py e bm_learning.py importam fcntl no topo e falham ao carregar no Windows",
  "created_at": "2026-09-01T22:02:25+00:00",
  "docviva": {
    "after_digest": "240d6f555a63d2b35288f2d62f8a34d88b01a6d8eb7d1bbecb68aa6a6f4e600e",
    "artifacts": [],
    "before_digest": "240d6f555a63d2b35288f2d62f8a34d88b01a6d8eb7d1bbecb68aa6a6f4e600e",
    "changed": [],
    "created": [],
    "justification": "O patch restaura o suporte Windows já documentado e não altera interface, versão ou contrato público.",
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
    "O binário Go windows-amd64 não compila: o builder já cruza esse alvo com CGO_ENABLED=0 e a falha observada ocorre nos módulos Python empacotados"
  ],
  "environment": "Release oficial 0.5.0, target windows-amd64, commit 3a277275bbb491d90110398bf429f241fc0b2e59",
  "events": [
    {
      "at": "2026-09-01T22:03:52+00:00",
      "event": "reproduced",
      "evidence": "python3 import de skills/_shared/scripts/bm.py com fcntl indisponível: exit 1, ModuleNotFoundError em bm_learning.py:12",
      "fingerprint": "abc7627fb5846e88b760f195bc06c0a887d536ba6c8b0d50d8d609e8ca812e41"
    },
    {
      "at": "2026-09-01T22:04:02+00:00",
      "event": "diagnosed",
      "evidence": "Traceback termina em bm_learning.py:12 antes do parser; rg confirma imports incondicionais em bm_learning.py:12 e bm_close.py:11",
      "fingerprint": "abc7627fb5846e88b760f195bc06c0a887d536ba6c8b0d50d8d609e8ca812e41"
    },
    {
      "at": "2026-09-01T22:04:42+00:00",
      "event": "red",
      "evidence": "python3 -m unittest tests.test_windows_portability: FAIL; ModuleNotFoundError No module named fcntl em bm_learning.py:12",
      "fingerprint": "fb04dad0ae6afa8846364cfc8b116be86b57f6df980c6aa718a831f3dba7b243"
    },
    {
      "at": "2026-09-01T22:05:34+00:00",
      "event": "fixing",
      "evidence": "Patch adiciona bm_file_lock.py e substitui chamadas diretas a fcntl em bm_learning.py e bm_close.py",
      "fingerprint": "b1cf9fd138a620499c16dea16747c9f9458fd6aad108f1e22b0d067fbe5f16e3"
    },
    {
      "at": "2026-09-01T22:05:50+00:00",
      "event": "green",
      "evidence": "python3 -m unittest tests.test_windows_portability tests.test_learning tests.test_close_recovery: 37 testes OK",
      "fingerprint": "b1cf9fd138a620499c16dea16747c9f9458fd6aad108f1e22b0d067fbe5f16e3"
    },
    {
      "at": "2026-09-01T22:14:12+00:00",
      "event": "regression_checked",
      "evidence": "Fix de produção no fingerprint GREEN: testes Windows simulados, learning e cycle-close aprovados",
      "fingerprint": "b1cf9fd138a620499c16dea16747c9f9458fd6aad108f1e22b0d067fbe5f16e3"
    },
    {
      "at": "2026-09-01T22:14:24+00:00",
      "event": "documented",
      "evidence": "Regressão Windows registrada em tests/test_windows_portability.py; versão oficial permanece 0.5.0",
      "fingerprint": "b1cf9fd138a620499c16dea16747c9f9458fd6aad108f1e22b0d067fbe5f16e3"
    }
  ],
  "expected": "As instalações Windows carregam o pacote e o CLI inicia sem ModuleNotFoundError para fcntl",
  "experiments": [
    "Bloquear a importação de fcntl e importar publicamente bm.py; a falha ocorre durante a cadeia bm.py -\u003e bm_context -\u003e bm_learning"
  ],
  "finished_at": "2026-09-01T22:14:24+00:00",
  "green": "python3 -m unittest tests.test_windows_portability tests.test_learning tests.test_close_recovery: 37 testes OK",
  "hypotheses": [
    "Imports Unix-only no topo dos módulos bm_learning e bm_close impedem carregar o entrypoint empacotado antes de qualquer comando no Windows"
  ],
  "id": "D001-restaurar-inicializacao-do-pacote-0-5-0-no-windo",
  "neighboring_regressions": [
    "Unix mantém flock; 35 testes vizinhos de learning e cycle-close passaram sem regressão"
  ],
  "objective": "Restaurar inicialização do pacote 0.5.0 no Windows sem alterar a versão oficial",
  "origin_evidence": null,
  "origin_refs": null,
  "reason": "Importação portátil e locks exclusivos preservados em Unix e Windows",
  "red": "python3 -m unittest tests.test_windows_portability: FAIL; ModuleNotFoundError No module named fcntl em bm_learning.py:12",
  "relation": null,
  "residual_risk": "Execução em runner Windows e redistribuição serão validadas após o commit e push",
  "root_cause": "O pacote 0.5.0 inclui bm_learning.py e bm_close.py com import fcntl incondicional e chamadas diretas a flock, sem backend msvcrt para Windows",
  "schema_version": 1,
  "stage": "documented",
  "status": "resolved",
  "updated_at": "2026-09-01T22:14:24+00:00"
}
---

# Debug D001-restaurar-inicializacao-do-pacote-0-5-0-no-windo

Restaurar inicialização do pacote 0.5.0 no Windows sem alterar a versão oficial
