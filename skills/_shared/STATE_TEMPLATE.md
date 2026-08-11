# Template de `PROJECT_STATE.md` v2

Copie o JSON abaixo. JSON é YAML válido e permite validação standalone sem dependência externa.

```json
{
  "method_version": 2,
  "method_mode": "standalone-adaptive",
  "planning_version": "v1",
  "planning_status": "pending_approval",
  "execution_policy": "adaptive",
  "assurance_profile": "lean",
  "architecture_audit": "optional",
  "architecture_audit_status": "not_run",
  "manual_pdf": "scope",
  "scope": {
    "status": "approved",
    "source": "docs/bianchini/v1/inputs/APPROVED_SCOPE.md",
    "approved_at": null
  },
  "planning": {
    "spec": "docs/bianchini/v1/specs/YYYY-MM-DD-sistema-system-design.md",
    "review": "docs/bianchini/v1/PLANNING_REVIEW.md"
  },
  "approval": {
    "status": "pending",
    "approved_at": null,
    "approved_by": null,
    "approved_plans": [],
    "package": {
      "algorithm": "sha256-manifest-v1",
      "manifest_path": "artifacts/bianchini/v1/approval/manifest.sha256",
      "manifest_digest": null,
      "files": [
        "docs/bianchini/v1/inputs/APPROVED_SCOPE.md",
        "docs/bianchini/v1/specs/YYYY-MM-DD-sistema-system-design.md",
        "docs/bianchini/v1/plans/P01-entrega.md",
        "docs/bianchini/v1/PLANNING_REVIEW.md"
      ]
    }
  },
  "plans": [
    {
      "id": "P01",
      "path": "docs/bianchini/v1/plans/P01-entrega.md",
      "status": "planned",
      "risk": "low",
      "execution": "grouped",
      "review": "plan_gate",
      "test_seams": ["public-interface"],
      "depends_on": [],
      "ledger": "artifacts/bianchini/v1/ledgers/P01.md",
      "gates": ["test", "build"]
    }
  ],
  "verification": {
    "fast": { "commands": [], "status": "pending" },
    "plan": { "commands": [], "status": "pending" },
    "release": { "commands": [], "status": "pending" }
  },
  "release": {
    "status": "pending",
    "platforms": [],
    "profiles": [],
    "candidate": null,
    "final_gate": "homologar-sistema",
    "homologation": "pending",
    "final_review": "pending",
    "delivery": "pending"
  },
  "active_execution": null,
  "telemetry": {
    "enabled": false,
    "path": "artifacts/bianchini/v1/telemetry.jsonl"
  },
  "blockers": [],
  "next_action": "Aprovar uma única vez o digest e todos os planos; depois commitar localmente pacote, estado e manifesto."
}
```

## Semântica

- `planning_version` versiona o ciclo documental (`v1`, `v2`...), não o método.
- Migração explícita pode iniciar com `planning_status: in_progress`, aprovação pending e `plans: []`. Esse bootstrap serve somente para fixar a rota v2; deve receber planos reais antes de `pending_approval`, snapshot ou aprovação.
- `planning_status`: `in_progress | pending_approval | approved | blocked`.
- `assurance_profile`: `lean | standard | full`.
- `architecture_audit`: `disabled | optional | required`; é uma auditoria manual e report-only, nunca ativada automaticamente por risco ou perfil.
- `architecture_audit_status: passed` significa relatório concluído, não certificação nem gate de aprovação.
- `manual_pdf`: `none | quick_start | full | scope`; `scope` gera somente o nível contratado no escopo aprovado.
- `release.candidate`, quando presente, exige fingerprint com `id`, `revision`, `build` e `checksum`.
- `active_execution` pode registrar `plan_id`, `unit` e caminho absoluto de `workspace` durante a execução.
- `telemetry.enabled: false` é o padrão. Quando habilitada explicitamente, registra apenas métricas numéricas locais em JSONL, sem prompts, código ou conteúdo de arquivos.
- `verification.fast`: feedback durante grupo/slice/tarefa.
- `verification.plan`: gate completo de cada plano.
- `verification.release`: regressão e E2E automatizados antes da exploração manual.

Valide sempre antes de aprovação, execução, homologação e status:

```bash
python3 <caminho-absoluto-de-bm.py> validate-state docs/living/PROJECT_STATE.md
```

Após registrar a aprovação, verificar o snapshot e criar um commit local contendo todos os arquivos do manifesto, este estado e o manifesto. `workspace create` recusará árvore suja ou arquivo aprovado ausente do `HEAD`.
