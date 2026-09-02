---
{
  "actual": "workspace create retorna MISSING_PROVIDER quando o item consumido existe em interfaces",
  "created_at": "2026-09-02T16:37:40+00:00",
  "docviva": {
    "after_digest": "240d6f555a63d2b35288f2d62f8a34d88b01a6d8eb7d1bbecb68aa6a6f4e600e",
    "artifacts": [],
    "before_digest": "240d6f555a63d2b35288f2d62f8a34d88b01a6d8eb7d1bbecb68aa6a6f4e600e",
    "changed": [],
    "created": [],
    "justification": "Correção interna restaura contrato aprovado; nenhuma spec, arquitetura ou regra mudou.",
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
    "P01 incompleto ou pacote stale: roadmap next-wave reconhece P01 concluído, P02/T01 elegível e digest vigente."
  ],
  "environment": "bm 0.5.0 Go, macOS arm64, commit 033f1955bd624e2ca7f2b973e3fdabb28a7e3869",
  "events": [
    {
      "at": "2026-09-02T16:38:36+00:00",
      "event": "reproduced",
      "evidence": "No checkout limpo de conectarmarcearia, bm workspace create --change C001-mvp-conectamarcenaria --plan P02 retornou MISSING_PROVIDER para account_session; roadmap next-wave confirmou C001/P02/T01 elegível.",
      "fingerprint": "8a69f8baa82290545bc5e72a10c2e3046f34d36c37cf67d1696839d0e7a66782"
    },
    {
      "at": "2026-09-02T16:38:49+00:00",
      "event": "diagnosed",
      "evidence": "P01 actual_delta adiciona account_session em interfaces; o modelo esperado também contém interfaces.account_session. execution_workspace.go e plan.go testam consumes somente em effective.sections[contracts], enquanto coherence_validate.go considera IDs de todas as coleções.",
      "fingerprint": "8a69f8baa82290545bc5e72a10c2e3046f34d36c37cf67d1696839d0e7a66782"
    },
    {
      "at": "2026-09-02T16:39:20+00:00",
      "event": "red",
      "evidence": "go test ./internal/gokernel -run TestExecutionWorkspaceCreateAcceptsConsumedEffectiveModelComponent -count=1 falhou com MISSING_PROVIDER para account_session presente em interfaces.",
      "fingerprint": "089b5351387ef198ee47868ffa927ed07e1ec3779820f7b549fe4c8e9aabea22"
    },
    {
      "at": "2026-09-02T16:39:25+00:00",
      "event": "fixing",
      "evidence": "Aplicar validação central de component ID do ProjectModel nos dois gates de consumes, preservando MISSING_PROVIDER para ID ausente.",
      "fingerprint": "089b5351387ef198ee47868ffa927ed07e1ec3779820f7b549fe4c8e9aabea22"
    },
    {
      "at": "2026-09-02T16:40:21+00:00",
      "event": "green",
      "evidence": "A mesma regressão passou após o patch: go test ./internal/gokernel -run TestExecutionWorkspaceCreateAcceptsConsumedEffectiveModelComponent -count=1.",
      "fingerprint": "6580a3236d9f29bdbb2b8cf243817f459aedebd7aed18bbfc9b9653e66bb8a42"
    },
    {
      "at": "2026-09-02T16:41:12+00:00",
      "event": "regression_checked",
      "evidence": "go test ./... passou; go test -race ./... passou; go vet ./... passou; python3 -m unittest tests.test_method_v04_cli passou 34 testes.",
      "fingerprint": "6580a3236d9f29bdbb2b8cf243817f459aedebd7aed18bbfc9b9653e66bb8a42"
    },
    {
      "at": "2026-09-02T16:41:44+00:00",
      "event": "documented",
      "evidence": "Fix restaura a semântica já usada por coherence: consumes aceita qualquer component ID do ProjectModel efetivo. Não altera schema, plano ou DocViva.",
      "fingerprint": "6580a3236d9f29bdbb2b8cf243817f459aedebd7aed18bbfc9b9653e66bb8a42"
    }
  ],
  "expected": "workspace create e plan complete aceitam um consume presente como interface no modelo efetivo",
  "experiments": [
    "Adicionar regressão de workspace público com consume em interfaces e manter caso vizinho de consume inexistente."
  ],
  "finished_at": "2026-09-02T16:41:44+00:00",
  "green": "A mesma regressão passou após o patch: go test ./internal/gokernel -run TestExecutionWorkspaceCreateAcceptsConsumedEffectiveModelComponent -count=1.",
  "hypotheses": [
    "A causa é a validação de execução consultar apenas contracts, porque account_session está em interfaces; se a presença for verificada em todas as coleções do ProjectModel, o workspace será criado sem enfraquecer a rejeição de IDs realmente ausentes."
  ],
  "id": "D003-corrigir-validacao-de-consumes-para-aceitar-prov",
  "neighboring_regressions": [
    "TestExecutionWorkspaceCreateGates preserva MISSING_PROVIDER quando o consume não existe em nenhuma coleção; TestExecutionWorkspaceCreateLocateResumeAndCheck preserva criação, locate, resume e check."
  ],
  "objective": "Corrigir validação de consumes para aceitar providers efetivos em qualquer coleção do ProjectModel",
  "origin_evidence": null,
  "origin_refs": null,
  "reason": "Validação corrigida e regressões Go/Python aprovadas.",
  "red": "go test ./internal/gokernel -run TestExecutionWorkspaceCreateAcceptsConsumedEffectiveModelComponent -count=1 falhou com MISSING_PROVIDER para account_session presente em interfaces.",
  "relation": null,
  "residual_risk": "A prova nativa cobre interface e provider ausente; as demais coleções compartilham o mesmo iterador modelCollections e foram exercitadas pela suíte completa.",
  "root_cause": "Os gates workspace create e plan complete divergiram da semântica de coherence: uses de consumes foram codificados contra a coleção contracts, não contra os component IDs do modelo efetivo.",
  "schema_version": 1,
  "stage": "documented",
  "status": "resolved",
  "updated_at": "2026-09-02T16:41:44+00:00"
}
---

# Debug D003-corrigir-validacao-de-consumes-para-aceitar-prov

Corrigir validação de consumes para aceitar providers efetivos em qualquer coleção do ProjectModel
