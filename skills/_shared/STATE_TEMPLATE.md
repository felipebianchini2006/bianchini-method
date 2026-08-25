# Template de `.bianchini/STATE.md`

`STATE.md` é um índice atual, não um histórico. O frontmatter usa JSON válido e fica abaixo de 64 KiB.

```markdown
---
{
  "schema_version": 1,
  "method": "0.4",
  "status": "pending_approval",
  "active_work": {
    "kind": "change",
    "id": "C001",
    "status": "pending_approval"
  },
  "current_unit": {
    "phase": "planning",
    "plan": null,
    "unit": null,
    "gate": "coherence"
  },
  "blockers": [],
  "next_action": "Obter aprovação explícita do digest global.",
  "last_completed": null,
  "pointers": {
    "architecture": ".bianchini/changes/C001-entrega/ARCHITECTURE.md",
    "system_model": ".bianchini/changes/C001-entrega/SYSTEM_MODEL.md",
    "specs": ".bianchini/current/specs",
    "coherence": ".bianchini/changes/C001-entrega/COHERENCE.md"
  },
  "digest": "<sha256 global ou null>",
  "updated_at": "2026-01-01T00:00:00Z"
}
---

# Estado atual

Resumo humano curto e coerente com o frontmatter. Não adicionar ledger, histórico ou resultados detalhados.
```

## Regras

- Chaves raiz permitidas: `schema_version`, `method`, `status`, `active_work`, `current_unit`, `blockers`, `next_action`, `last_completed`, `pointers`, `digest`, `updated_at`.
- `schema_version` é `1` e versiona apenas o formato compacto do índice.
- `method` é `0.4`; correções do pacote não alteram o contrato do projeto.
- `active_work.kind`: `change | quick | debug | migration | null`.
- IDs: `C001`, `P01`, `Q001` e `D001`.
- `status`: `idle | planning | pending_approval | approved | active | executing | blocked | completed | escalated`.
- `current_unit` é `null`, um estágio compacto (`intake`, `red`, `green`) ou um objeto com fase/plano/unidade/gate; nunca recebe histórico.
- `blockers` contém somente bloqueios abertos e compactos.
- `last_completed` contém somente ID, tipo, resultado e caminho do último trabalho; não é uma lista.
- `pointers` contém somente `architecture`, `system_model`, `specs` e `coherence`, com caminhos relativos confinados a `.bianchini/`.
- `digest` repete somente o SHA-256 global vigente; aprovação, manifest e findings detalhados ficam em `COHERENCE.md`.
- `updated_at` usa ISO 8601 UTC.
- O corpo Markdown é opcional e curto.
- São proibidos no estado: `history`, `ledger`, `events`, `results`, logs, hipóteses, comandos completos, diffs e evidências extensas.

## Estado ocioso

```json
{
  "schema_version": 1,
  "method": "0.4",
  "status": "idle",
  "active_work": null,
  "current_unit": null,
  "blockers": [],
  "next_action": "Aguardar uma nova mudança, quick ou debug.",
  "last_completed": {
    "kind": "change",
    "id": "C001",
    "status": "completed",
    "path": ".bianchini/archive/C001-entrega"
  },
  "pointers": {
    "architecture": ".bianchini/current/ARCHITECTURE.md",
    "system_model": ".bianchini/current/SYSTEM_MODEL.md",
    "specs": ".bianchini/current/specs",
    "coherence": null
  },
  "digest": null,
  "updated_at": "2026-01-01T00:00:00Z"
}
```

## `SYSTEM_MODEL.md`

O modelo usa frontmatter JSON determinístico e corpo humano opcional:

```markdown
---
{
  "schema_version": 1,
  "modules": [{"id":"payments","owns":["payment_intent"]}],
  "interfaces": [{"id":"payment_gateway","provider":"payments","consumers":["checkout"]}],
  "capabilities": [],
  "contracts": [],
  "ownership": [],
  "data": [{"id":"payment_intent","owner":"payments","durable_before":"provider_request"}],
  "integrations": [{"id":"gateway_webhook","authenticity":"required","deduplication":"provider_event_id"}],
  "journeys": [{"id":"checkout_confirmation","path":["checkout","payment_gateway","payment_intent","gateway_webhook","order_status"]}],
  "invariants": [],
  "effects": []
}
---

# Modelo do sistema

Explicação curta do fluxo completo e dos limites relevantes.
```

`ARCHITECTURE.md` guarda decisões e trade-offs. `SYSTEM_MODEL.md` guarda a representação do sistema. Não duplicar histórico em nenhum deles.
