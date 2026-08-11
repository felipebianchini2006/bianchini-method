---
name: sdd-planning
description: Use somente com invocação explícita de /sdd-planning, ou para continuar um projeto cujo PROJECT_STATE declare method_version 2. Em estado v1, apenas roteia ao legado; não disputa ativação com skills gerais de planejamento.
---

# SDD Planning

**Anuncie:** "Planejando com Bianchini Method <v1 legado|v2 standalone>."

Leia [`../_shared/METHOD_CONTRACT.md`](../_shared/METHOD_CONTRACT.md), [`../_shared/STATE_TEMPLATE.md`](../_shared/STATE_TEMPLATE.md) e [`../_shared/ADAPTIVE_GATES.md`](../_shared/ADAPTIVE_GATES.md). Resolva o caminho absoluto de [`../_shared/scripts/bm.py`](../_shared/scripts/bm.py) uma vez.

## 1. Rotear

1. Ler regras do repositório e `PROJECT_STATE.md`, se existir.
2. Com estado, executar `bm.py route <state>`; sem estado, executar `bm.py route --repo <repo> --new-project`.
3. Se v1, exigir Superpowers e entregar o planejamento ao fluxo legado. Sem Superpowers, declarar `BLOQUEADO`; não criar documentos v2.
4. Se a rota for `v2-new`, iniciar v2 pelo template e validar com `bm.py validate-state`.
5. Se a rota for `v2-standalone` com `planning_status: idle`, iniciar o próximo ciclo sem Superpowers: manter a `planning_version` reservada, materializar o novo escopo aprovado e trocar para `in_progress` antes de produzir spec/planos.
6. Se versão ambígua/inválida, bloquear sem inferir migração.

Exceção: se o responsável pedir explicitamente a migração do projeto atual, executar `route --migrate-to-v2`, nunca inferir essa decisão. Preservar `docs/superpowers/` como histórico, atualizar `AGENTS.md`/`CLAUDE.md` para remover o workflow ativo legado e criar estado bootstrap v2 com `planning_status: in_progress` e `plans: []`. O próximo planejamento deve substituir o bootstrap antes de `pending_approval`.

Um estado v2 `idle` criado automaticamente por `executar-plano` após a conclusão real do último ciclo legado já é migrado e autorizado. Não chamar `writing-plans`, brainstorming ou qualquer skill Superpowers; iniciar diretamente este fluxo standalone. Não renumerar para `v2`: `planning_version: v1` identifica o primeiro planejamento feito pelo método v2.

Executar `bm.py repo-hygiene check --repo <repo>`. Se houver `.superpowers/` rastreado e a migração estiver autorizada, executar `repo-hygiene migrate`; caso contrário, bloquear. A raiz deve conter `/.superpowers/` no `.gitignore`; documentos persistentes pertencem a `docs/bianchini/`, nunca a `.superpowers/`.

Esta skill somente planeja. Não criar código, scaffolding, migração ou dependência de produção.

## 2. Ler fontes uma vez

Ordem: decisão recente do responsável, escopo aprovado, plano mestre, spec/ADR, design, documentação, código/testes/histórico.

- Materializar escopo conversacional ou URL mutável em `docs/bianchini/<planning_version>/inputs/APPROVED_SCOPE.md`.
- Registrar no `PLANNING_REVIEW.md` apenas fatos, conflitos, premissas, riscos e ponteiros.
- Não reabrir decisão aprovada nem copiar documentos inteiros.

## 3. Classificar garantia

Escolher `lean`, `standard` ou `full` pelo risco real:

- `lean`: baixo risco, integração isolada;
- `standard`: risco médio, múltiplos perfis/plataformas ou integração coordenada;
- `full`: regulação, risco crítico ou garantias ampliadas.

Executar `bm.py policy` para cada plano. A auditoria arquitetural é manual e report-only: não a executar automaticamente por perfil ou risco. Definir `architecture_audit: disabled|optional|required` conforme decisão explícita do responsável. Se ele contratar o relatório no pacote (`required`), incluir o arquivo no manifesto quando existir; candidatos de melhoria não bloqueiam aprovação.

## 4. Criar spec central

Caminho v2:

`docs/bianchini/<planning_version>/specs/YYYY-MM-DD-<sistema>-system-design.md`

Incluir somente:

- objetivo, limites e não objetivos;
- arquitetura e contratos públicos;
- entidades, estados, invariantes e permissões;
- jornadas e critérios de aceite;
- segurança/dados/migração/concorrência aplicáveis;
- plataformas e integrações;
- seams de teste observáveis;
- manual/PDF somente se contratado;
- decisões e bloqueios.

Design visual existente usa [`references/design-import.md`](references/design-import.md). Full usa [`references/full-assurance.md`](references/full-assurance.md). Abrir cada referência apenas quando aplicável.

## 5. Criar planos por entregas reais

Caminho:

`docs/bianchini/<planning_version>/plans/P<NN>-<entrega>.md`

Não há mínimo ou alvo de tarefas. Um plano pode ter uma ou duas tarefas quando essas são as entregas reais. Separar somente quando uma unidade puder ser rejeitada ou verificada independentemente.

Cabeçalho:

```yaml
plan_id: P01
method_version: 2
risk: low | medium | high | critical
execution: grouped | slice | strict
review: plan_gate | per_slice | per_task
depends_on: []
spec_refs: [<caminho#seção>]
```

Cada tarefa/slice/grupo declara:

```markdown
### Tarefa N — <resultado observável>

**Execution:** grouped | slice | strict
**Review:** plan_gate | per_slice | per_task
**Test seams:** <interfaces públicas verificadas>
**Spec refs:** <seções exatas>
**Files:** <caminhos>
**Contract:** <entradas, saídas, invariantes>
**Verification:** <comando e resultado esperado>
**Done when:** <evidência objetiva>
```

### Política de decomposição

- `grouped`: reunir mudanças baixas no mesmo seam; uma revisão no gate do plano.
- `slice`: cada slice entrega comportamento vertical; revisão por slice.
- `strict`: uma tarefa por unidade crítica, RED/GREEN e revisão independente.
- Setup/config/docs pertencem à primeira unidade que os usa.
- Não usar `TBD`, “tratar erros”, tarefas horizontais ou abstração futura.

## 6. Definir verificação

Descobrir comandos nativos do repositório e preencher:

- `verification.fast`: feedback mínimo do grupo/slice/tarefa;
- `verification.plan`: gate completo por plano;
- `verification.release`: regressão, E2E codificado e build do RC.

Gate indispensável indisponível é bloqueio, nunca `passed` presumido.

## 7. Criar estado e pacote

Criar `PROJECT_STATE.md` em JSON conforme o template, usando:

- `planning_version: v1` no primeiro ciclo;
- `planning_status: pending_approval`;
- `execution_policy: adaptive`;
- `assurance_profile: lean|standard|full`;
- `architecture_audit: disabled|optional|required`;
- `manual_pdf: scope` por padrão;
- `telemetry.enabled: false` por padrão; habilitar somente por decisão explícita;
- política adaptativa em cada plano;
- três estágios de `verification`.

Em `idle`, escopo/spec/revisão ainda são nulos e `plans: []`; ao receber o novo escopo aprovado, trocar para `in_progress` e preencher as fontes locais. Durante bootstrap explícito de migração, `plans: []` também é permitido em `in_progress` com aprovação pending. Antes de gerar snapshot ou pedir aprovação, criar os planos reais e remover o estado bootstrap.

Depois:

1. validar estado com `bm.py validate-state`;
2. criar manifesto com `bm.py snapshot create`;
3. gravar o digest retornado em `approval.package.manifest_digest`;
4. validar estado novamente e verificar snapshot;
5. pedir uma única aprovação do digest e de todos os planos.

Não aprovar em nome do responsável. Se ele reduzir o conjunto, regenerar pacote inteiro; não existe aprovação parcial.

Quando o responsável aprovar:

1. registrar `planning_status: approved`, `approval.status: approved`, responsável, horário e planos;
2. validar estado e executar `snapshot verify` novamente;
3. adicionar somente os arquivos do pacote, `PROJECT_STATE.md` e o manifesto; se o manifesto estiver ignorado, usar inclusão explícita apenas para ele;
4. criar commit local atômico `plan: approve <planning_version> package <digest-curto>`;
5. confirmar `git status --porcelain` vazio.

Não incluir mudanças alheias no commit, não fazer push e não criar worktree antes dele. Se já houver mudanças externas que impeçam árvore limpa, declarar `BLOQUEADO` e pedir ao responsável para commitá-las, guardá-las ou removê-las.

## 8. Revisar planejamento

Passagem Spec: cobertura, não objetivos, contratos, seams, dependências e plataformas.

Passagem Qualidade: simplicidade, política de execução correta, gates executáveis, ausência de placeholders e custo proporcional.

Salvar `PLANNING_REVIEW.md`. Corrigir achados antes do manifesto final.

## Saída

Informar rota v1/v2, perfil, arquitetura auditada ou opcional, spec, planos, estado validado, digest e bloqueios. Antes da aprovação, encerrar pedindo a decisão única; quando ela chegar, concluir o commit local do pacote sem implementar.
