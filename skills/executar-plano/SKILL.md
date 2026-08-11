---
name: executar-plano
description: Use somente com invocação explícita de /executar-plano ou quando PROJECT_STATE declarar method_version 2 e houver plano aprovado. Em estado v1, apenas roteia ao executor legado e não concorre com executores gerais.
---

# Executar Plano

**Anuncie:** "Executando <planos> no modo <v1 legado|grouped|slice|strict>."

Argumentos: `all`, `N`, `N-M`. Sem argumento, mostrar `status-projeto`; executar `all` somente quando o pedido atual já for explícito.

Leia [`../_shared/METHOD_CONTRACT.md`](../_shared/METHOD_CONTRACT.md). Resolva o caminho de [`../_shared/scripts/bm.py`](../_shared/scripts/bm.py).

## 1. Preflight e rota

1. Executar `bm.py route`.
2. V1: exigir Superpowers e usar integralmente o executor legado. Se ausente, `BLOQUEADO`. Não usar nenhuma etapa v2 abaixo.
3. V2: executar `bm.py validate-state` e `bm.py snapshot verify`.
4. Se aprovação ainda estiver pending, registrar apenas aprovação explícita inequívoca do digest atual. Concluir a transação descrita em `sdd-planning`: verificar snapshot, commitar localmente somente pacote/estado/manifesto e exigir árvore limpa. O comando de execução não vale como aprovação.
5. Confirmar planos em `approved_plans` e dependências concluídas. Auditoria arquitetural manual não é gate de execução; defeitos funcionais registrados continuam sujeitos aos gates normais.
6. Exigir `git status --porcelain` vazio. Mudança preexistente bloqueia a criação da worktree; nunca omitir, copiar informalmente ou incluir mudança alheia no commit do planejamento.

Snapshot divergente invalida aprovação e bloqueia. Não classificar mudança como “editorial”.

## 2. Workspace isolado obrigatório

Criar um workspace por plano:

```bash
<bm.py> workspace create --repo <repo> --planning-version v1 --plan P01 --state <PROJECT_STATE.md>
<bm.py> workspace resume --repo <repo> --planning-version v1 --plan P01
<bm.py> workspace check --repo <workspace>
```

Usar a `planning_version` do estado, nunca valor fixo copiado do exemplo. A branch será `bm/<planning_version>-<plan_id>`. Entrar no caminho retornado antes de editar. `workspace check` deve passar no início e antes de cada commit. Main, master, detached HEAD e worktree primária são proibidos. Não existe fallback para branch atual.

Aquecer dependências uma vez no workspace, usando gerenciador e comandos do projeto.

## 3. Inicializar execução recuperável

No ledger do plano, registrar digest aprovado, base revision, workspace, branch, modo, perfil e máximo de fix rounds.

Quando `telemetry.enabled: true`, registrar ao fim de cada grupo/slice/tarefa apenas deltas numéricos com `bm.py telemetry record`: tokens informados pelo host, duração, fix rounds e falhas de gate. Não estimar tokens nem persistir prompt, diff ou conteúdo do projeto.

Gerar com o CLI:

- `task-brief`: um por grupo, slice ou tarefa conforme modo;
- `report`: relatório persistente do implementador;
- `review-package`: entrada determinística da revisão;
- `checkpoint`: após cada unidade aprovada, falha, bloqueio e antes de encerrar contexto.

Retomada começa com `workspace resume`, lendo o caminho absoluto do checkpoint, estado, unidade atual e ledger tail. Não reler planos concluídos nem histórico da conversa.

## 4. Executar pela política do plano

Antes da unidade, executar `bm.py policy` com perfil/risco e confirmar que o resultado coincide com `execution` e `review` aprovados. Divergência aumenta garantia automaticamente; redução exige novo pacote aprovado.

### Grouped — baixo risco

- Agrupar tarefas do mesmo seam e sem conflitos de ownership.
- Gerar um brief com `task-brief --tasks 1-3`; confirmar `kind: group`, `group_id`, hash do grupo e hashes das unidades. O CLI rejeita grupo com unidade não-grouped.
- Executar `verification.fast` nos seams afetados, não RED/GREEN artificial por microtarefa.
- Fazer auto-revisão do grupo e uma revisão Spec/Qualidade no `plan_gate`.
- Commit atômico por grupo coerente.

### Slice — risco médio

- Cada slice entrega comportamento vertical observável.
- Gerar brief, relatório e teste comportamental por slice.
- Usar RED/GREEN quando o teste detecta regressão real; validation-first para config/docs.
- Revisar Spec/Qualidade uma vez por slice.
- Commit atômico por slice.

### Strict — risco alto/crítico

- Uma unidade crítica por dispatch/execução.
- Exigir teste RED pela interface pública, implementação mínima GREEN e vizinhos de risco.
- Exigir revisor independente quando a capacidade existir; sem revisor, registrar bloqueio para Full e compensação explícita para Standard.
- Revisar cada tarefa e commit atômico.

Nenhum modo implementa necessidade de tarefa futura. Testes observam seams públicos, não detalhes internos.

## 5. Revisão e fix loop

Eixos obrigatórios na cadência do modo:

- **Spec:** comportamento, contratos, escopo e critérios.
- **Qualidade:** correção, segurança, manutenção, compatibilidade e testes sensíveis.

Classificar `critical`, `important`, `minor`, `note`. Critical/important abre fix round; minor pode ser adiado com risco explícito para revisão final.

Máximo retornado por `bm.py policy`:

- Lean: 2;
- Standard: 3;
- Full: 5.

Em cada rodada: corrigir causa mínima, executar teste cobrindo, gerar novo pacote do delta e revisar achados abertos. Quando `breaker: true`, parar tentativas. Problema estrutural ou load-bearing marca plano `blocked`; nunca exceder o limite.

## 6. Gate por plano

Depois das unidades:

1. executar todos os comandos `verification.plan` no RC atual;
2. registrar comando, cwd, horário, saída resumida e código de retorno;
3. usar `corrigir-bug` para falha de produto e repetir gate afetado/dependentes;
4. gerar checkpoint final;
5. marcar plano `completed` somente com gates obrigatórios `passed`.

`not_run`, flake aberto ou dependência indispensável mantém `blocked`.

## 7. Release, homologação e revisão final

Quando o último plano aprovado concluir:

1. identificar RC com fingerprint completo `id`, `revision`, `build` e `checksum`, então definir `release.status: candidate`;
2. executar `homologar-sistema`, que começa por `verification.release`;
3. somente com `homologation: accepted` e status `homologated`, revisar o release inteiro;
4. comparar spec, planos, contratos cruzados, achados adiados, segurança e diff desde a primeira `base_revision`;
5. executar verificação ampla proporcional e registrar `final_review: approved`;
6. criar `artifacts/delivery/DELIVERY.md` e definir `release.status: ready`.

Se o host não invocar skills por nome, ler e cumprir diretamente `corrigir-bug` ou `homologar-sistema`.

Manual/PDF só entra na entrega quando `manual_pdf` e o escopo exigirem.

## Paradas

Parar por Superpowers ausente em v1, estado/snapshot inválido, worktree insegura, aprovação ausente, mudança de contrato, defeito direto bloqueante, ação sensível sem autorização, breaker, gate irrecuperável ou dependência externa indispensável.

## Saída

Informar rota, planos/modos, workspaces, gates, homologação, revisão final, commits, ledgers/checkpoints, manual quando aplicável e bloqueios. Não fazer push, merge, deploy ou publicação por inferência.
