# Template de `PROJECT_STATE.md` v2

JSON é YAML válido e permite validação standalone sem dependência externa. Novos ciclos usam `planning.quality_version: 2`.

```json
{
  "method_version": 2,
  "method_mode": "standalone-adaptive",
  "planning_version": "v1",
  "planning_status": "pending_approval",
  "execution_policy": "adaptive",
  "assurance_profile": "standard",
  "architecture_audit": "optional",
  "architecture_audit_status": "not_run",
  "manual_pdf": "scope",
  "scope": {
    "status": "approved",
    "source": "docs/bianchini/changes/v1/inputs/APPROVED_SCOPE.md",
    "approved_at": null
  },
  "planning": {
    "quality_version": 2,
    "research_mode": "targeted_web",
    "research": "docs/bianchini/changes/v1/STACK_RESEARCH.md",
    "readiness": "docs/bianchini/changes/v1/READINESS.md",
    "user_actions": "docs/bianchini/changes/v1/USER_ACTIONS.md",
    "spec": "docs/bianchini/changes/v1/specs/YYYY-MM-DD-sistema-change.md",
    "review": "docs/bianchini/changes/v1/PLANNING_REVIEW.md",
    "checker": {
      "status": "passed",
      "rounds": 1,
      "history_path": "artifacts/bianchini/v1/planning/checker.jsonl",
      "package_digest": "<digest retornado por planning-check>",
      "report_digest": "<digest do PLANNING_REVIEW.md revisado>"
    },
    "design_manifest": null,
    "change_root": "docs/bianchini/changes/v1",
    "current_specs": "docs/bianchini/current/specs"
  },
  "complexity_review": {
    "decision": "within_budget",
    "justification": null,
    "deferred_scope": [],
    "scope_split_approved": false,
    "scope_split_approved_by": null,
    "scope_split_approved_at": null
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
        "docs/bianchini/changes/v1/inputs/APPROVED_SCOPE.md",
        "docs/bianchini/changes/v1/STACK_RESEARCH.md",
        "docs/bianchini/changes/v1/READINESS.md",
        "docs/bianchini/changes/v1/USER_ACTIONS.md",
        "docs/bianchini/changes/v1/specs/YYYY-MM-DD-sistema-change.md",
        "docs/bianchini/changes/v1/spec-deltas/system.md",
        "docs/bianchini/changes/v1/plans/P01-entrega.md",
        "docs/bianchini/changes/v1/PLANNING_REVIEW.md"
      ]
    }
  },
  "plans": [
    {
      "id": "P01",
      "path": "docs/bianchini/changes/v1/plans/P01-entrega.md",
      "status": "planned",
      "risk": "medium",
      "execution": "slice",
      "review": "per_slice",
      "test_seams": ["public-interface"],
      "depends_on": [],
      "ledger": "artifacts/bianchini/v1/ledgers/P01.md",
      "gates": ["test", "build"]
    }
  ],
  "verification": {
    "fast": { "commands": ["<comando rápido real>"], "status": "pending" },
    "plan": { "commands": ["<gate real do plano>"], "status": "pending" },
    "release": { "commands": ["<gate real do release>"], "status": "pending" }
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
  "next_action": "Aprovar uma única vez o digest e todos os planos; depois commitar pacote, estado e manifesto."
}
```

## Pacote de design

Quando `READINESS.md` declarar `design_required: true`, `planning.design_manifest` aponta para `docs/design/<version>/DESIGN_MANIFEST.json`. Adicionar ao pacote o manifesto e todos os arquivos listados nele. Antes do planejamento:

```bash
python3 <bm.py> design-audit verify --root . --scope <scope> --manifest <manifest>
```

Arquivo solto em `docs/design` não é válido.

## Checker

`planning.checker` é atualizado somente por:

```bash
python3 <bm.py> planning-check record --state docs/living/PROJECT_STATE.md --root . --report <PLANNING_REVIEW.md>
```

- passagem 1: `passed`, `changes_requested` ou `blocked`;
- passagem 2, somente após mudança factual no pacote, inclusive ajuste posterior a um primeiro `passed`: exige relatório novo e termina em `passed` ou `blocked`;
- máximo de duas passagens;
- alteração no pacote depois de `passed` invalida `package_digest`; alteração no relatório revisado invalida `report_digest`.

## Semântica

- `planning_version` versiona a mudança (`v1`, `v2`...), não o método.
- `planning_status: idle` existe entre ciclos. Escopo, pesquisa, readiness, ações, spec, review, checker, design e change root ficam nulos; `current_specs` permanece; aprovação, planos, gates e release são reinicializados.
- Migração explícita pode iniciar `in_progress` com `plans: []`; antes de `pending_approval`, o pacote completo é obrigatório.
- `quality_version: 1` permanece compatível para ciclos antigos. Novo ciclo usa `2`.
- `research_mode`: `repo_only | targeted_web | full`; usar o menor modo suficiente.
- `readiness` resolve decisões, suposições, pitfalls, ações externas, spikes, design e specs de domínio antes dos planos.
- `READINESS.md.repository_revision` deve ser o `HEAD` atual antes da aprovação, ou `new-project` sem repositório. Novo commit antes do checker/snapshot invalida o gate; depois da aprovação o valor fica congelado no pacote.
- `design_manifest` é nulo sem interface/design material.
- `change_root` contém somente a mudança atual.
- `current_specs` contém comportamento já aceito e não é editado durante o ciclo.
- `complexity_review`: `within_budget | split | indivisible`. `deferred_scope` exige `scope_split_approved: true`, autor e horário.
- `assurance_profile`: `lean | standard | full`.
- `architecture_audit`: `disabled | optional | required`; auditoria manual e report-only.
- `manual_pdf`: `none | quick_start | full | scope`.
- `release.candidate` exige `id`, `revision`, `build` e `checksum`.
- `active_execution` registra plano, unidade e workspace durante execução.
- telemetria permanece opt-in e numérica.
- `verification.fast`: feedback focal da unidade.
- `verification.plan`: gate completo do plano.
- `verification.release`: regressão/E2E/build/mutação exigida antes do passe real.

## Fluxo de validação

```bash
python3 <bm.py> validate-state docs/living/PROJECT_STATE.md
python3 <bm.py> planning-audit docs/living/PROJECT_STATE.md --root . --strict
python3 <bm.py> snapshot create docs/living/PROJECT_STATE.md --root .
python3 <bm.py> snapshot verify docs/living/PROJECT_STATE.md --root .
```

Substitua comandos ilustrativos antes do audit. Quando uma spec em `docs/bianchini/current/specs/` já existir e for alterada por `SD-*`, inclua a versão atual no pacote para congelar a base.

Após homologação, revisão final e entrega:

```bash
python3 <bm.py> cycle-close --state docs/living/PROJECT_STATE.md --root .
```

O comando sincroniza `spec-deltas`, arquiva a mudança, incrementa a versão e prepara o estado `idle` para o próximo ciclo.
