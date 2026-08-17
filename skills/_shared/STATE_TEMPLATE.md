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
    "quality_version": 1,
    "research_mode": "targeted_web",
    "research": "docs/bianchini/v1/STACK_RESEARCH.md",
    "spec": "docs/bianchini/v1/specs/YYYY-MM-DD-sistema-system-design.md",
    "review": "docs/bianchini/v1/PLANNING_REVIEW.md"
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
        "docs/bianchini/v1/inputs/APPROVED_SCOPE.md",
        "docs/bianchini/v1/STACK_RESEARCH.md",
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
    "fast": { "commands": ["<substituir pelo comando rápido real>"], "status": "pending" },
    "plan": { "commands": ["<substituir pelo gate real do plano>"], "status": "pending" },
    "release": { "commands": ["<substituir pelo gate real do release>"], "status": "pending" }
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
- `planning_status: idle` é criado somente no encerramento automático de um projeto legado. Nesse estado, `scope` fica pending/sem fonte, `planning.research`, `planning.spec` e `planning.review` ficam nulos, `complexity_review` fica pending, aprovação e manifesto ficam vazios, `plans: []` e `active_execution: null`. O próximo `/sdd-planning` mantém `planning_version: v1` e muda para `in_progress` ao receber novo escopo aprovado.
- Migração explícita pode iniciar com `planning_status: in_progress`, aprovação pending e `plans: []`. Esse bootstrap serve somente para fixar a rota v2; deve receber planos reais antes de `pending_approval`, snapshot ou aprovação.
- `planning_status`: `idle | in_progress | pending_approval | approved | blocked`.
- `planning.quality_version: 1` ativa pesquisa primária, simplificação e orçamento verificáveis. Estados v2 anteriores sem esse campo continuam legíveis; novos planejamentos devem usá-lo.
- `planning.research_mode`: `repo_only | targeted_web | full`; usar o menor modo suficiente e registrar o motivo no `STACK_RESEARCH.md`.
- `planning.research` aponta para `STACK_RESEARCH.md`, incluído no pacote aprovado.
- `complexity_review`: `within_budget`, `split` ou `indivisible`. O orçamento escala com `assurance_profile`; ele nunca autoriza remover requisito aprovado.
- `deferred_scope` só pode receber requisito do escopo aprovado quando o responsável tiver autorizado explicitamente a divisão antes do planejamento. Nesse caso, registrar `scope_split_approved: true`, autor e horário. Sem isso, `planning-audit --strict` bloqueia.
- `assurance_profile`: `lean | standard | full`.
- `architecture_audit`: `disabled | optional | required`; é uma auditoria manual e report-only, nunca ativada automaticamente por risco ou perfil.
- `architecture_audit_status: passed` significa relatório concluído, não certificação nem gate de aprovação.
- `manual_pdf`: `none | quick_start | full | scope`; `scope` gera somente o nível contratado no escopo aprovado.
- `release.candidate`, quando presente, exige fingerprint com `id`, `revision`, `build` e `checksum`.
- `active_execution` pode registrar `plan_id`, `unit` e caminho absoluto de `workspace` durante a execução.
- `telemetry.enabled: false` é o padrão. Quando habilitada explicitamente, registra apenas métricas numéricas locais em JSONL, sem prompts, código ou conteúdo de arquivos.
- `verification.fast`: unitários e integração/contrato focados mais regressão relacionada durante grupo/slice/tarefa; sem E2E completo ou mutação.
- `verification.plan`: suítes afetadas, regressão do plano, E2E crítico e mutação seletiva quando `bm.py policy` exigir.
- `verification.release`: suíte unitária completa configurada, integração/contratos aplicáveis, E2E crítico, regressão completa, build e evidência de mutação vigente quando obrigatória, antes da execução real do RC e da varredura visual.
- As camadas são comandos dentro dos três estágios, não novos estados, tarefas ou campos no schema.

Valide sempre antes de aprovação, execução, homologação e status:

```bash
python3 <caminho-absoluto-de-bm.py> validate-state docs/living/PROJECT_STATE.md
```

Antes do snapshot de um novo planejamento, substitua os comandos ilustrativos por comandos reais e execute:

```bash
python3 <caminho-absoluto-de-bm.py> planning-audit docs/living/PROJECT_STATE.md --root . --strict
```

Após registrar a aprovação, verificar o snapshot e criar um commit local contendo todos os arquivos do manifesto, este estado e o manifesto. `workspace create` recusará árvore suja ou arquivo aprovado ausente do `HEAD`.
