# Contrato da CLI 0.4

> Arquivo gerado de `contracts/cli-surfaces.json`. Não edite manualmente.

- Schema do registry: `1`
- Contrato: `0.4`
- Base congelada: `7c9fa23f524623f3360ebae579048e1765095220`
- Comandos do parser: `30`
- Superfícies do parser: `53`

## Convenções

`$CWD` é o diretório corrente no instante em que o parser é construído. `$PACKAGED_SKILLS_ROOT` é a raiz `skills` da instalação que contém o CLI. A interface listada abaixo inclui flags aceitas pelo argparse mesmo quando uma ação não as consome.

## Comandos e interfaces

### `bm validate-state`

- Geração: `legacy_internal`
- Parser: `state;type=Path;required | --schema;type=Path;default=null`

### `bm model`

- Geração: `core_0_4`
- Parser: `action;choices=init,validate;required | --repo;type=Path;default="$CWD" | --change;default=null`

### `bm scope`

- Geração: `core_0_4`
- Parser: `action;choices=seal,verify;required | --repo;type=Path;default="$CWD" | --change;required | --source;type=Path;default=null | --draft;type=Path;default=null | --pages;type=int;default=null | --extraction;choices=native,ocr,mixed;default=null`

### `bm roadmap`

- Geração: `core_0_4`
- Parser: `action;choices=sync,next-wave;required | --repo;type=Path;default="$CWD" | --change;required | --format;choices=json;default="json"`

### `bm coherence`

- Geração: `core_0_4`
- Parser: `action;choices=check,approve;required | --repo;type=Path;default="$CWD" | --change;required | --structural-only;action=store_true;default=false | --semantic-report;type=Path;default=null | --digest;default=null | --approved-by;default=null`

### `bm impact`

- Geração: `core_0_4`
- Parser: `action;choices=analyze;required | --repo;type=Path;default="$CWD" | --change;required | --plan;required | --changed-contract;action=append;default=[] | --changed-ownership;action=append;default=[] | --changed-interface;action=append;default=[] | --changed-data;action=append;default=[] | --changed-migration;action=append;default=[] | --changed-journey;action=append;default=[] | --changed-effect;action=append;default=[] | --changed-invariant;action=append;default=[] | --global-change;action=store_true;default=false`

### `bm plan`

- Geração: `core_0_4`
- Parser: `action;choices=complete;required | --repo;type=Path;default="$CWD" | --change;required | --plan;required | --actual-delta;type=Path;required | --result;required | --verification;action=append;default=[] | --completed-task;action=append;default=[]`

### `bm context`

- Geração: `core_0_4`
- Parser: `action;choices=pack,verify;required | --repo;type=Path;default="$CWD" | --unit;default=null | --output;type=Path;default=null | --max-bytes;type=int;default=16384 | --path;type=Path;default=null`

### `bm adapter`

- Geração: `operational`
- Parser: `action;choices=render,install;required | --host;choices=generic,codex,claude-compatible;required | --repo;type=Path;default="$CWD" | --overwrite;action=store_true;default=false`

### `bm debug`

- Geração: `core_0_4`
- Parser: `action;choices=start,list,status,resume,checkpoint,finish;required | --repo;type=Path;default="$CWD" | --id;default=null | --objective;default=null | --expected;default=null | --actual;default=null | --environment;default=null | --origin-ref;action=append;default=[] | --origin-evidence;default=null | --relation;choices=caused_by,detected_in,regression_of;default=null | --event;choices=reproduced,diagnosed,red,fixing,green,regression_checked,documented;default=null | --evidence;default=null | --hypothesis;action=append;default=[] | --experiment;action=append;default=[] | --eliminated-hypothesis;action=append;default=[] | --root-cause;default=null | --neighbor-regression;action=append;default=[] | --residual-risk;default=null | --status;choices=resolved,blocked,escalated;default=null | --reason;default=null | --docviva-kind;choices=internal,behavioral,contract,architecture,rule;default=null | --docviva-outcome;choices=updated,not_applicable,no_op;default=null | --docviva-artifact;action=append;default=[] | --docviva-justification;default=null`

### `bm migrate`

- Geração: `core_0_4`
- Parser: `action;choices=check,apply;required | --repo;type=Path;default="$CWD"`

### `bm snapshot`

- Geração: `legacy_internal`
- Parser: `action;choices=create,verify;required | state;type=Path;required | --root;type=Path;required`

### `bm planning-audit`

- Geração: `legacy_internal`
- Parser: `state;type=Path;required | --root;type=Path;required | --strict;action=store_true;default=false`

### `bm design-audit`

- Geração: `operational`
- Parser: `action;choices=seal,verify;required | --root;type=Path;required | --scope;type=Path;required | --manifest;type=Path;required`

### `bm planning-check`

- Geração: `legacy_internal`
- Parser: `action;choices=record;required | --state;type=Path;required | --root;type=Path;required | --report;type=Path;required`

### `bm change-policy`

- Geração: `companion`
- Parser: `--scope-change;action=store_true;default=false | --public-contract-change;action=store_true;default=false | --approved-design-change;action=store_true;default=false | --new-cost;action=store_true;default=false | --irreversible-action;action=store_true;default=false | --external-impossibility;action=store_true;default=false | --critical-invariant;action=store_true;default=false | --plan-command;action=store_true;default=false | --file-location;action=store_true;default=false | --internal-order;action=store_true;default=false`

### `bm cycle-close`

- Geração: `core_0_4`
- Parser: `--repo;type=Path;default="$CWD" | --change;required`

### `bm policy`

- Geração: `operational`
- Parser: `--profile;choices=lean,standard,full;required | --risk;choices=low,medium,high,critical;required | --change;default="behavioral" | --manual-pdf;choices=none,quick_start,full,scope;default="scope" | --manual-in-scope;action=store_true;default=false | --round;type=int;default=0 | --risk-seam;default=null | --seam-round;type=int;default=null | --structural-finding;choices=crash_window,partial_commit,toctou,external_effect_before_persistence,retry_after_timeout,concurrent_idempotency,recovery_after_restart;action=append;default=[] | --consecutive-seam-findings;type=int;default=0`

### `bm workspace`

- Geração: `core_0_4`
- Parser: `action;choices=create,check,locate,resume;required | --repo;type=Path;default="$CWD" | --plan;default=null | --change;default=null | --target;type=Path;default=null`

### `bm task-brief`

- Geração: `companion`
- Parser: `--plan;type=Path;required | --task;default=null | --tasks;default=null | --group;default=null | --state;type=Path;default=null | --root;type=Path;default=null | --hydrate-context;action=store_true;default=false | --ledger-tail-lines;type=int;default=40 | --output;type=Path;required`

### `bm spec-diff`

- Geração: `operational`
- Parser: `--root;type=Path;required | --base;type=Path;required | --target;type=Path;required | --output;type=Path;required`

### `bm mutation-evidence`

- Geração: `operational`
- Parser: `action;choices=verify;required | --state;type=Path;required | --root;type=Path;required | --plan;required | --risk-seam;required | --tool;choices=normalized,stryker;required | --command;required | --report;type=Path;required | --revision;required | --classifications;type=Path;default=null | --output;type=Path;required`

### `bm report`

- Geração: `companion`
- Parser: `--brief;type=Path;required | --output;type=Path;required`

### `bm review-package`

- Geração: `companion`
- Parser: `--cwd;type=Path;default="$CWD" | --base;required | --head;default="HEAD" | --brief;type=Path;required | --report;type=Path;required | --output;type=Path;required`

### `bm checkpoint`

- Geração: `companion`
- Parser: `--state;type=Path;required | --ledger;type=Path;required | --cwd;type=Path;default="$CWD" | --output;type=Path;required`

### `bm proof-map`

- Geração: `operational`
- Parser: `--state;type=Path;required | --evidence;type=Path;required | --mutation-evidence;type=Path;action=append;default=[] | --output;type=Path;required`

### `bm telemetry`

- Geração: `operational`
- Parser: `action;choices=record,summary;required | --state;type=Path;required | --root;type=Path;required | --plan;default=null | --phase;choices=planning,execution,gate,homologation,final_review;default="execution" | --at;default=null | --input-tokens;type=int;default=0 | --output-tokens;type=int;default=0 | --duration-ms;type=int;default=0 | --fix-rounds;type=int;default=0 | --gate-failures;type=int;default=0 | --homologation-bugs;type=int;default=0`

### `bm direct`

- Geração: `core_0_4`
- Parser: `action;choices=classify,start,status,checkpoint,finish,reopen;required | --repo;type=Path;default="$CWD" | --slug;default=null | --objective;default=null | --scope;default=null | --acceptance;action=append;default=[] | --verification;action=append;default=[] | --checkpoint;default=null | --changed-file;action=append;default=[] | --command;action=append;default=[] | --blocker;action=append;default=[] | --next-action;default=null | --status;choices=completed,blocked;default=null | --behavior;action=append;default=[] | --limitation;action=append;default=[] | --evidence;action=append;default=[] | --scope-score;type=int;choices=0,1,2;default=0 | --external-effect-score;type=int;choices=0,1,2;default=0 | --migration-score;type=int;choices=0,1,2;default=0 | --concurrency-score;type=int;choices=0,1,2;default=0 | --money-score;type=int;choices=0,1,2;default=0 | --guard;action=append;default=[] | --webhook-flow;action=store_true;default=false | --payment-flow;action=store_true;default=false | --production-authorized;action=store_true;default=false | --multiple-objectives;action=store_true;default=false | --destructive-migration;action=store_true;default=false | --uncontrolled-concurrency;action=store_true;default=false | --undefined-ownership;action=store_true;default=false | --ambiguous-financial-rule;action=store_true;default=false | --new-material-architecture;action=store_true;default=false | --docviva-kind;choices=internal,behavioral,contract,architecture,rule;default=null | --docviva-outcome;choices=updated,not_applicable,no_op;default=null | --docviva-artifact;action=append;default=[] | --docviva-justification;default=null`

### `bm update-bm`

- Geração: `operational`
- Parser: `--check;action=store_true;default=false | --skills-root;type=Path;default="$PACKAGED_SKILLS_ROOT" | --timeout;type=float;default=15.0 | --format;choices=text,json;default="text"`

### `bm status`

- Geração: `core_0_4`
- Parser: `state;type=Path;required | --root;type=Path;default=null | --format;choices=json,text;default="json"`

## Superfícies

| ID | Geração | Saída | Exits | Mutações permitidas | Handlers | Módulos | Consumidores | Evidência |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `validate-state` | legacy_internal | JSON object indentado, chaves ordenadas, UTF-8 e newline final | 0, 2, 3, 4 | nenhuma | validate_state | skills/_shared/scripts/bm.py | codex/skills/executar-plano-codex/references/EXECUTION_CORE_CODEX.md | tests/test_method_package.py::test_v2_state_validates_and_status_is_structured |
| `model.init` | core_0_4 | JSON object indentado, chaves ordenadas, UTF-8 e newline final | 0, 2, 3, 4 | .bianchini/** | v04.init_workspace<br>v04_planning.create_change | skills/_shared/scripts/bm_v04_planning.py<br>skills/_shared/scripts/bm_v04_workflows.py | skills/design-projeto/SKILL.md<br>skills/preparar-escopo/SKILL.md<br>skills/sdd-planning/SKILL.md | tests/test_method_v04_cli.py::test_model_init_creates_only_bianchini_workspace |
| `model.validate` | core_0_4 | JSON object indentado, chaves ordenadas, UTF-8 e newline final | 0, 2, 3, 4 | nenhuma | v04.validate_workspace<br>v04_planning.validate_change_model | skills/_shared/scripts/bm_v04_planning.py<br>skills/_shared/scripts/bm_v04_workflows.py | skills/auditar-arquitetura/SKILL.md<br>skills/executar-plano/SKILL.md<br>skills/homologar-sistema/SKILL.md<br>skills/migrar-bianchini/SKILL.md<br>skills/sdd-planning/SKILL.md<br>skills/status-projeto/SKILL.md | tests/test_method_v04_cli.py::test_change_model_coherence_and_impact_are_integrated |
| `scope.seal` | core_0_4 | JSON object indentado, chaves ordenadas, UTF-8 e newline final | 0, 2, 3, 4 | .bianchini/changes/<change>/SCOPE.md<br>.bianchini/changes/<change>/COHERENCE.md<br>.bianchini/STATE.md | bm_scope.seal_scope | skills/_shared/scripts/bm_scope.py | skills/preparar-escopo/SKILL.md | tests/test_method_v04_cli.py::test_scope_seal_creates_verified_scope_and_preserves_foreign_planning |
| `scope.verify` | core_0_4 | JSON object indentado, chaves ordenadas, UTF-8 e newline final | 0, 2, 3, 4 | nenhuma | bm_scope.verify_scope | skills/_shared/scripts/bm_scope.py | skills/preparar-escopo/SKILL.md<br>skills/sdd-planning/SKILL.md | tests/test_method_v04_cli.py::test_scope_verify_detects_tampering_and_different_pdf |
| `roadmap.sync` | core_0_4 | JSON object indentado, chaves ordenadas, UTF-8 e newline final | 0, 2, 3, 4 | .bianchini/changes/<change>/ROADMAP.md<br>.bianchini/STATE.md | v04_planning.sync_roadmap | skills/_shared/scripts/bm_v04_planning.py | skills/sdd-planning/SKILL.md | tests/test_method_v04_cli.py::test_typed_planning_binds_scope_roadmap_tasks_semantic_review_and_package |
| `roadmap.next-wave` | core_0_4 | JSON object indentado, chaves ordenadas, UTF-8 e newline final | 0, 2, 3, 4 | nenhuma | next_wave | skills/_shared/scripts/bm_wave.py | skills/executar-plano/SKILL.md | tests/test_phase3_cli.py::test_next_wave_is_public_read_only_projection |
| `coherence.check` | core_0_4 | JSON object indentado, chaves ordenadas, UTF-8 e newline final | 0, 2, 3, 4 | .bianchini/changes/<change>/COHERENCE.md | v04_planning.coherence_check | skills/_shared/scripts/bm_v04_planning.py | skills/sdd-planning/SKILL.md | tests/test_method_v04_cli.py::test_change_model_coherence_and_impact_are_integrated |
| `coherence.approve` | core_0_4 | JSON object indentado, chaves ordenadas, UTF-8 e newline final | 0, 2, 3, 4 | .bianchini/changes/<change>/COHERENCE.md<br>.bianchini/STATE.md | v04_planning.coherence_approve | skills/_shared/scripts/bm_v04_planning.py | skills/sdd-planning/SKILL.md | tests/test_method_v04_cli.py::test_typed_planning_binds_scope_roadmap_tasks_semantic_review_and_package |
| `impact.analyze` | core_0_4 | JSON object indentado, chaves ordenadas, UTF-8 e newline final | 0, 2, 3, 4 | .bianchini/changes/<change>/COHERENCE.md<br>.bianchini/STATE.md | v04_planning.impact_analyze | skills/_shared/scripts/bm_v04_planning.py | skills/executar-plano/SKILL.md<br>skills/sdd-planning/SKILL.md | tests/test_method_v04_cli.py::test_change_model_coherence_and_impact_are_integrated |
| `plan.complete` | core_0_4 | JSON object indentado, chaves ordenadas, UTF-8 e newline final | 0, 2, 3, 4 | .bianchini/changes/<change>/results/<plan>.md<br>.bianchini/changes/<change>/results/tasks/<plan>/<task>.md<br>.bianchini/STATE.md | v04_planning.plan_complete | skills/_shared/scripts/bm_v04_planning.py | skills/executar-plano/SKILL.md | tests/test_method_v04_cli.py::test_typed_plan_completion_requires_every_task |
| `context.pack` | core_0_4 | JSON object indentado, chaves ordenadas, UTF-8 e newline final | 0, 2, 3, 4 | .bianchini/.runtime/context/<unit>.json ou --output confinado ao repo | compile_context_pack | skills/_shared/scripts/bm_context.py | skills/corrigir-bug/SKILL.md<br>skills/executar-direto/SKILL.md<br>skills/executar-plano/SKILL.md<br>skills/homologar-sistema/SKILL.md<br>skills/status-projeto/SKILL.md | tests/test_context_cli.py::test_context_pack_and_verify_are_public_and_json_observable |
| `context.verify` | core_0_4 | JSON object indentado, chaves ordenadas, UTF-8 e newline final | 0, 2, 3, 4 | nenhuma | verify_context_pack | skills/_shared/scripts/bm_context.py | — | tests/test_context_cli.py::test_context_pack_and_verify_are_public_and_json_observable |
| `adapter.render` | operational | JSON object indentado, chaves ordenadas, UTF-8 e newline final | 0, 2, 3, 4 | nenhuma | render_adapter | skills/_shared/scripts/bm_host_adapters.py | — | tests/test_phase3_cli.py::test_adapter_render_and_explicit_install_are_public |
| `adapter.install` | operational | JSON object indentado, chaves ordenadas, UTF-8 e newline final | 0, 2, 3, 4 | bloco gerenciado em AGENTS.md ou CLAUDE.md no --repo explícito | install_adapter | skills/_shared/scripts/bm_host_adapters.py | — | tests/test_phase3_cli.py::test_adapter_render_and_explicit_install_are_public |
| `debug.start` | core_0_4 | JSON object indentado, chaves ordenadas, UTF-8 e newline final | 0, 2, 3, 4 | .bianchini/debug/active/<id>/**<br>.bianchini/STATE.md | v04.debug_start | skills/_shared/scripts/bm_v04_workflows.py | skills/corrigir-bug/SKILL.md | tests/test_method_v04_cli.py::test_debug_persists_red_green_and_rejects_wrong_order |
| `debug.list` | core_0_4 | JSON object indentado, chaves ordenadas, UTF-8 e newline final | 0, 2, 3, 4 | nenhuma | v04.debug_status | skills/_shared/scripts/bm_v04_workflows.py | skills/corrigir-bug/SKILL.md | tests/test_method_v04_cli.py::test_debug_persists_red_green_and_rejects_wrong_order |
| `debug.status` | core_0_4 | JSON object indentado, chaves ordenadas, UTF-8 e newline final | 0, 2, 3, 4 | nenhuma | v04.debug_status | skills/_shared/scripts/bm_v04_workflows.py | skills/corrigir-bug/SKILL.md<br>skills/status-projeto/SKILL.md | tests/test_method_v04_cli.py::test_debug_persists_red_green_and_rejects_wrong_order |
| `debug.resume` | core_0_4 | JSON object indentado, chaves ordenadas, UTF-8 e newline final | 0, 2, 3, 4 | nenhuma | v04.debug_status | skills/_shared/scripts/bm_v04_workflows.py | skills/corrigir-bug/SKILL.md | tests/test_method_v04_cli.py::test_debug_persists_red_green_and_rejects_wrong_order |
| `debug.checkpoint` | core_0_4 | JSON object indentado, chaves ordenadas, UTF-8 e newline final | 0, 2, 3, 4 | .bianchini/debug/active/<id>/**<br>.bianchini/STATE.md | v04.debug_checkpoint | skills/_shared/scripts/bm_v04_workflows.py | skills/corrigir-bug/SKILL.md | tests/test_method_v04_cli.py::test_debug_persists_red_green_and_rejects_wrong_order |
| `debug.finish` | core_0_4 | JSON object indentado, chaves ordenadas, UTF-8 e newline final | 0, 2, 3, 4 | .bianchini/debug/active/<id>/**<br>.bianchini/debug/resolved/<id>/** ou .bianchini/debug/blocked/<id>/**<br>.bianchini/STATE.md | v04.debug_finish | skills/_shared/scripts/bm_v04_workflows.py | skills/corrigir-bug/SKILL.md | tests/test_method_v04_cli.py::test_debug_persists_red_green_and_rejects_wrong_order |
| `migrate.check` | core_0_4 | JSON object indentado, chaves ordenadas, UTF-8 e newline final | 0, 2, 3, 4 | nenhuma | v04.migration_check | skills/_shared/scripts/bm_v04_workflows.py | skills/migrar-bianchini/SKILL.md | tests/test_method_v04_cli.py::test_migration_is_explicit_and_never_touches_planning |
| `migrate.apply` | core_0_4 | JSON object indentado, chaves ordenadas, UTF-8 e newline final | 0, 2, 3, 4 | .bianchini/**<br>docs/bianchini/legacy/** | v04.migration_apply | skills/_shared/scripts/bm_v04_workflows.py | skills/migrar-bianchini/SKILL.md | tests/test_method_v04_cli.py::test_migration_is_explicit_and_never_touches_planning |
| `snapshot.create` | legacy_internal | JSON object indentado, chaves ordenadas, UTF-8 e newline final | 0, 2, 3, 4 | manifest_path declarado no estado | snapshot | skills/_shared/scripts/bm.py | — | tests/test_method_package.py::test_snapshot_detects_tampering |
| `snapshot.verify` | legacy_internal | JSON object indentado, chaves ordenadas, UTF-8 e newline final | 0, 2, 3, 4 | nenhuma | snapshot | skills/_shared/scripts/bm.py | codex/skills/executar-plano-codex/references/EXECUTION_CORE_CODEX.md | tests/test_method_package.py::test_snapshot_detects_tampering |
| `planning-audit` | legacy_internal | JSON object indentado, chaves ordenadas, UTF-8 e newline final | 0, 2, 3, 4 | nenhuma | planning_audit | skills/_shared/scripts/bm.py | — | tests/test_method_package.py::test_strict_audit_accepts_researched_compact_plan |
| `design-audit.seal` | operational | JSON object indentado, chaves ordenadas, UTF-8 e newline final | 0, 2, 3, 4 | manifest informado por --manifest | design_audit | skills/_shared/scripts/bm.py | skills/design-projeto/SKILL.md | tests/test_method_package.py::test_design_can_be_sealed_and_verified_before_project_state |
| `design-audit.verify` | operational | JSON object indentado, chaves ordenadas, UTF-8 e newline final | 0, 2, 3, 4 | nenhuma | design_audit | skills/_shared/scripts/bm.py | skills/design-projeto/SKILL.md | tests/test_method_package.py::test_design_can_be_sealed_and_verified_before_project_state |
| `planning-check.record` | legacy_internal | JSON object indentado, chaves ordenadas, UTF-8 e newline final | 0, 2, 3, 4 | report informado por --report<br>estado informado por --state | planning_check_record | skills/_shared/scripts/bm.py | — | tests/test_method_package.py::test_planning_checker_allows_one_correction_only |
| `change-policy` | companion | JSON object indentado, chaves ordenadas, UTF-8 e newline final | 0, 2, 3, 4 | nenhuma | change_policy | skills/_shared/scripts/bm.py | codex/skills/executar-plano-codex/SKILL.md<br>codex/skills/executar-plano-codex/references/CODEX_CONVERGENCE.md<br>codex/skills/executar-plano-codex/references/EXECUTION_CORE_CODEX.md<br>codex/skills/executar-plano-codex/references/plan-reviewer-codex.md | change-policy-read-only<br>change-policy-material<br>tests/test_method_package.py::test_change_policy_prevents_redesign_for_internal_adjustments |
| `cycle-close` | core_0_4 | JSON object indentado, chaves ordenadas, UTF-8 e newline final | 0, 2, 3, 4 | .bianchini/current/**<br>.bianchini/archive/<change>/**<br>.bianchini/STATE.md<br>remove .bianchini/changes/<change> após promoção | v04_planning.close_change | skills/_shared/scripts/bm_v04_planning.py | skills/executar-plano/SKILL.md<br>codex/skills/executar-plano-codex/references/EXECUTION_CORE_CODEX.md | tests/test_method_v04_cli.py::test_cycle_close_legacy_schema1_preserves_specs |
| `policy` | operational | JSON object indentado, chaves ordenadas, UTF-8 e newline final | 0, 2, 3, 4 | nenhuma | policy | skills/_shared/scripts/bm.py | skills/homologar-sistema/SKILL.md<br>codex/skills/executar-plano-codex/references/CODEX_CONVERGENCE.md<br>codex/skills/executar-plano-codex/references/EXECUTION_CORE_CODEX.md | tests/test_method_package.py::test_manual_policy_supports_none_quick_start_and_full |
| `workspace.create` | core_0_4 | JSON object indentado, chaves ordenadas, UTF-8 e newline final | 0, 2, 3, 4 | git worktree alvo<br>.bianchini/STATE.md | v04_planning.execution_workspace_create | skills/_shared/scripts/bm_v04_planning.py | skills/executar-plano/SKILL.md<br>codex/skills/executar-plano-codex/references/EXECUTION_CORE_CODEX.md | tests/test_method_v04_cli.py::test_execution_workspace_uses_change_and_plan_identity |
| `workspace.check` | core_0_4 | JSON object indentado, chaves ordenadas, UTF-8 e newline final | 0, 2, 3, 4 | nenhuma | v04_planning.execution_workspace_check | skills/_shared/scripts/bm_v04_planning.py | codex/skills/executar-plano-codex/references/EXECUTION_CORE_CODEX.md | tests/test_method_v04_cli.py::test_execution_workspace_uses_change_and_plan_identity |
| `workspace.locate` | core_0_4 | JSON object indentado, chaves ordenadas, UTF-8 e newline final | 0, 2, 3, 4 | nenhuma | v04_planning.execution_workspace_locate | skills/_shared/scripts/bm_v04_planning.py | — | tests/test_method_v04_cli.py::test_execution_workspace_uses_change_and_plan_identity |
| `workspace.resume` | core_0_4 | JSON object indentado, chaves ordenadas, UTF-8 e newline final | 0, 2, 3, 4 | nenhuma | v04_planning.execution_workspace_locate | skills/_shared/scripts/bm_v04_planning.py | codex/skills/executar-plano-codex/references/EXECUTION_CORE_CODEX.md | tests/test_method_v04_cli.py::test_execution_workspace_uses_change_and_plan_identity |
| `task-brief` | companion | JSON object indentado, chaves ordenadas, UTF-8 e newline final | 0, 2, 3, 4 | arquivo informado por --output | write_task_brief | skills/_shared/scripts/bm.py | codex/skills/executar-plano-codex/references/EXECUTION_CORE_CODEX.md | tests/test_context_efficiency.py::test_hydrated_task_brief_contains_only_referenced_context |
| `spec-diff` | operational | JSON object indentado, chaves ordenadas, UTF-8 e newline final | 0, 2, 3, 4 | arquivo informado por --output | spec_diff | skills/_shared/scripts/bm_spec_diff.py | — | spec-diff-created-output<br>tests/test_context_efficiency.py::test_spec_diff_derives_added_modified_and_removed_requirements |
| `mutation-evidence.verify` | operational | JSON object indentado, chaves ordenadas, UTF-8 e newline final | 0, 2, 3, 4 | arquivo informado por --output | mutation_evidence_verify | skills/_shared/scripts/bm_mutation.py | — | tests/test_context_efficiency.py::test_mutation_evidence_accepts_classified_survivors_and_ignores_score |
| `report` | companion | JSON object indentado, chaves ordenadas, UTF-8 e newline final | 0, 2, 3, 4 | arquivo informado por --output | write_report | skills/_shared/scripts/bm.py | codex/skills/executar-plano-codex/references/EXECUTION_CORE_CODEX.md | tests/test_method_package.py::test_real_low_risk_project_runs_snapshot_group_status_and_telemetry |
| `review-package` | companion | JSON object indentado, chaves ordenadas, UTF-8 e newline final | 0, 2, 3, 4 | arquivo informado por --output | write_review_package | skills/_shared/scripts/bm.py | codex/skills/executar-plano-codex/references/CODEX_CONVERGENCE.md | tests/test_codex_overlay.py::test_codex_preserves_frozen_plan_and_autonomy_envelope |
| `checkpoint` | companion | JSON object indentado, chaves ordenadas, UTF-8 e newline final | 0, 2, 3, 4 | arquivo informado por --output | write_checkpoint | skills/_shared/scripts/bm.py | codex/skills/executar-plano-codex/references/EXECUTION_CORE_CODEX.md | tests/test_method_package.py::test_real_low_risk_project_runs_snapshot_group_status_and_telemetry |
| `proof-map` | operational | JSON object indentado, chaves ordenadas, UTF-8 e newline final | 0, 2, 3, 4 | arquivo informado por --output | write_proof_map | skills/_shared/scripts/bm.py | skills/homologar-sistema/SKILL.md | tests/test_method_package.py::test_proof_map_rejects_evidence_from_old_candidate_fingerprint |
| `telemetry.record` | operational | JSON object indentado, chaves ordenadas, UTF-8 e newline final | 0, 2, 3, 4 | telemetry path declarado no estado, somente quando enabled | telemetry_record | skills/_shared/scripts/bm.py | — | tests/test_method_package.py::test_real_low_risk_project_runs_snapshot_group_status_and_telemetry |
| `telemetry.summary` | operational | JSON object indentado, chaves ordenadas, UTF-8 e newline final | 0, 2, 3, 4 | nenhuma | telemetry_summary | skills/_shared/scripts/bm.py | — | tests/test_method_package.py::test_real_low_risk_project_runs_snapshot_group_status_and_telemetry |
| `direct.classify` | core_0_4 | JSON object indentado, chaves ordenadas, UTF-8 e newline final | 0, 2, 3, 4 | nenhuma | direct_risk_from_args | skills/_shared/scripts/bm.py | skills/executar-direto/SKILL.md | direct-classify-default<br>direct-classify-protected<br>tests/test_method_v04_cli.py::test_direct_risk_classification_is_deterministic |
| `direct.start` | core_0_4 | JSON object indentado, chaves ordenadas, UTF-8 e newline final | 0, 2, 3, 4 | .bianchini/quick/<id>/**<br>.bianchini/STATE.md | v04.quick_start | skills/_shared/scripts/bm_v04_workflows.py | skills/executar-direto/SKILL.md | tests/test_method_v04_cli.py::test_critical_direct_work_stays_active_without_planning_redirect |
| `direct.status` | core_0_4 | JSON object indentado, chaves ordenadas, UTF-8 e newline final | 0, 2, 3, 4 | nenhuma | v04.quick_status | skills/_shared/scripts/bm_v04_workflows.py | skills/executar-direto/SKILL.md<br>skills/status-projeto/SKILL.md | tests/test_method_v04_cli.py::test_critical_direct_work_stays_active_without_planning_redirect |
| `direct.checkpoint` | core_0_4 | JSON object indentado, chaves ordenadas, UTF-8 e newline final | 0, 2, 3, 4 | .bianchini/quick/<id>/**<br>.bianchini/STATE.md | v04.quick_checkpoint | skills/_shared/scripts/bm_v04_workflows.py | skills/executar-direto/SKILL.md | tests/test_method_v04_cli.py::test_critical_direct_work_stays_active_without_planning_redirect |
| `direct.finish` | core_0_4 | JSON object indentado, chaves ordenadas, UTF-8 e newline final | 0, 2, 3, 4 | .bianchini/quick/<id>/**<br>.bianchini/STATE.md | v04.quick_finish | skills/_shared/scripts/bm_v04_workflows.py | skills/executar-direto/SKILL.md | tests/test_method_v04_cli.py::test_direct_finish_rejects_escalated_status |
| `direct.reopen` | core_0_4 | vazio | 2 | nenhuma | parser_only_terminal_error | nenhum | — | direct-reopen-terminal<br>tests/test_method_v04_cli.py::test_legacy_fallback_arguments_are_not_public_in_v04 |
| `update-bm` | operational | texto UTF-8 ou JSON conforme --format, sempre com newline final | 0, 2, 3, 4 | instalação informada por --skills-root quando sem --check | update_bianchini_method<br>render_update_result | skills/_shared/scripts/bm_update.py | skills/update-bm/SKILL.md | tests/test_self_update.py::test_public_skill_and_cli_expose_explicit_update |
| `status` | core_0_4 | texto UTF-8 ou JSON conforme --format, sempre com newline final | 0, 2, 3, 4 | nenhuma | state_summary<br>render_status | skills/_shared/scripts/bm.py | — | status-legacy-text<br>status-legacy-json<br>tests/test_method_package.py::test_status_reports_active_plan_unit_mode_and_workspace |

## Superfícies negativas

| ID | Estado | Argv | Exit | Mutações | Consumidores | Evidência |
| --- | --- | --- | --- | --- | --- | --- |
| `route.retired` | retired | route --repo {repo} --new-project | 2 | nenhuma | codex/skills/executar-plano-codex/references/EXECUTION_CORE_CODEX.md | retired-route<br>tests/test_method_v04_cli.py::test_legacy_adapter_commands_are_not_public |
| `legacy-transition.retired` | retired | legacy-transition --repo {repo} | 2 | nenhuma | codex/skills/executar-plano-codex/references/EXECUTION_CORE_CODEX.md | retired-legacy-transition<br>tests/test_method_v04_cli.py::test_legacy_adapter_commands_are_not_public |
| `repo-hygiene.retired` | retired | repo-hygiene check --repo {repo} | 2 | nenhuma | codex/skills/executar-plano-codex/references/EXECUTION_CORE_CODEX.md | retired-repo-hygiene<br>tests/test_method_v04_cli.py::test_legacy_adapter_commands_are_not_public |
| `workspace.companion-v2-flags` | known_incompatibility | workspace create --repo {repo} --plan P01 --planning-version v2 --state {repo}/legacy-state.json | 2 | nenhuma | codex/skills/executar-plano-codex/references/EXECUTION_CORE_CODEX.md | workspace-old-companion-flags<br>tests/test_method_v04_cli.py::test_legacy_fallback_arguments_are_not_public_in_v04 |

## Perfis de comportamento

### `json_read_only`

- stdout: JSON object indentado, chaves ordenadas, UTF-8 e newline final
- stderr: vazio no sucesso; uma mensagem canônica no erro
- exits: `0` = sucesso; `2` = entrada inválida; `3` = gate bloqueado; `4` = workspace inseguro
- mutações-base: nenhuma

### `json_mutating`

- stdout: JSON object indentado, chaves ordenadas, UTF-8 e newline final
- stderr: vazio no sucesso; uma mensagem canônica no erro
- exits: `0` = sucesso; `2` = entrada inválida; `3` = gate bloqueado; `4` = workspace inseguro
- mutações-base: somente os paths declarados pela superfície; superfícies que persistem evidência em bloqueio declaram essa escrita explicitamente

### `text_or_json_read_only`

- stdout: texto UTF-8 ou JSON conforme --format, sempre com newline final
- stderr: vazio no sucesso; uma mensagem canônica no erro
- exits: `0` = sucesso; `2` = entrada inválida; `3` = gate bloqueado; `4` = workspace inseguro
- mutações-base: nenhuma

### `text_or_json_mutating`

- stdout: texto UTF-8 ou JSON conforme --format, sempre com newline final
- stderr: vazio no sucesso; uma mensagem canônica no erro
- exits: `0` = sucesso; `2` = entrada inválida ou update indisponível; `3` = gate bloqueado; `4` = workspace inseguro
- mutações-base: somente a instalação explicitada por --skills-root quando --check não foi usado

### `parser_terminal_error`

- stdout: vazio
- stderr: ORDER_VIOLATION: quick 0.4 terminal é imutável + newline
- exits: `2` = erro terminal conhecido
- mutações-base: nenhuma

### `negative_argparse`

- stdout: vazio
- stderr: usage do argparse e erro canônico de escolha ou flag inválida
- exits: `2` = superfície aposentada ou incompatível
- mutações-base: nenhuma
