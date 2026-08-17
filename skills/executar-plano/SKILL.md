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
2. V1: exigir Superpowers e usar integralmente o executor legado. Se ausente, `BLOQUEADO`. Não usar nenhuma etapa v2 enquanto a fase estiver em andamento. Depois do encerramento completo, executar a transição da seção 8.
3. V2: executar `bm.py validate-state` e `bm.py snapshot verify`.
4. Executar `bm.py repo-hygiene check --repo <repo>`; bloquear `.superpowers/` rastreado ou ausência do ignore versionado.
5. Se aprovação ainda estiver pending, registrar apenas aprovação explícita inequívoca do digest atual. Concluir a transação descrita em `sdd-planning`: verificar snapshot, commitar localmente somente pacote/estado/manifesto e exigir árvore limpa. O comando de execução não vale como aprovação.
6. Confirmar planos em `approved_plans` e dependências concluídas. Auditoria arquitetural manual não é gate de execução; defeitos funcionais registrados continuam sujeitos aos gates normais.
7. Exigir `git status --porcelain` vazio. Mudança preexistente bloqueia a criação da worktree; nunca omitir, copiar informalmente ou incluir mudança alheia no commit do planejamento.

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

Antes da unidade, executar `bm.py policy` com perfil, risco e `Change` declarado no brief; planos antigos sem `Change` usam `behavioral` somente por compatibilidade. Confirmar que o resultado coincide com `execution` e `review` aprovados. Divergência aumenta garantia automaticamente; redução exige novo pacote aprovado.

Quando o host suportar subagentes, o implementador padrão dos três modos segue o contrato [`../_shared/agents/implementation-worker.md`](../_shared/agents/implementation-worker.md). Passar ao subagente somente o caminho do contrato, o caminho do brief, o caminho do relatório e o contexto adicional estritamente necessário; não copiar o conteúdo do contrato para o brief ou prompt. Sem subagentes, cumprir o contrato inline.

Durante a unidade, executar somente `verification.fast` proporcional ao seam: unitário focado, integração/contrato focada e regressão relacionada; não executar E2E completo ou mutação por unidade. E2E focado só é permitido quando for a menor prova pública da própria unidade. As camadas de teste não criam nova tarefa, dispatch, revisor ou subagente.

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

A revisão segue o contrato [`../_shared/agents/plan-reviewer.md`](../_shared/agents/plan-reviewer.md) na cadência do modo: `grouped` recebe uma revisão no gate do plano (nunca por microtarefa), `slice` uma revisão por slice e `strict` revisão independente por tarefa. Entregar ao revisor somente o caminho do contrato, do brief, do relatório, do review package e o caminho do arquivo de saída da revisão; o revisor grava o relatório completo nesse arquivo e devolve ao contexto apenas veredito, contagem por severidade, caminho e bloqueios.

Quando a unidade tiver risco alto ou crítico envolvendo autenticação, autorização, pagamentos, webhooks, multi-tenant, RLS, segredos, dados pessoais, upload, LLM com entrada não confiável, migração ou infraestrutura sensível, adicionar uma passagem somente leitura pelo contrato [`../_shared/agents/security-reviewer.md`](../_shared/agents/security-reviewer.md), entregando também o caminho do arquivo de saída do parecer; o retorno ao contexto é apenas veredito, contagem por severidade e caminho. Não executá-la em tarefa comum. As correções continuam no fix loop abaixo.

Eixos obrigatórios na cadência do modo:

- **Spec:** comportamento, contratos, escopo e critérios.
- **Qualidade:** correção, segurança, manutenção, compatibilidade e testes sensíveis.

Classificar `critical`, `important`, `minor`, `note`. Critical/important abre fix round; minor pode ser adiado com risco explícito para revisão final.

Máximo retornado por `bm.py policy`:

- Lean: 2;
- Standard: 3;
- Full: 5.

Em cada rodada: registrar o `risk_seam` no ledger, corrigir causa mínima, executar teste cobrindo, gerar novo pacote do delta e revisar achados abertos. Recalcular `bm.py policy` com `--risk-seam`, `--seam-round` acumulado do seam, `--consecutive-seam-findings` e `--structural-finding` quando o parecer apontar classe estrutural (crash window, partial commit, TOCTOU, efeito externo antes de persistência, retry após timeout, idempotência concorrente, recuperação após restart).

Fix round é hipótese, não entrega: somente RED/GREEN focal, regressão diretamente relacionada e revisão do delta. Gates completos, documentação e mudança de status permanecem no gate do plano, após zero critical/important. Quando `breaker: true` ou `redesign_required: true`, parar tentativas e redesenhar conforme o contrato antes de novo patch no seam. Problema estrutural ou load-bearing marca plano `blocked`; nunca exceder o limite.

## 6. Gate por plano

Depois das unidades:

1. executar todos os comandos `verification.plan` no RC atual: suítes afetadas de unitários e integração/contrato, regressão do plano, E2E das jornadas críticas entregues e mutação seletiva quando `bm.py policy` exigir;
2. limitar mutação aos seams materiais alterados, usando ferramenta e comando já aprovados. Não perseguir score global, não instalar ferramenta neste estágio e não criar tarefa separada para “melhorar cobertura”;
3. mutante sobrevivente só bloqueia quando demonstra que comportamento aprovado de risco alto/crítico pode mudar sem o teste falhar. Equivalente, inalcançável ou sem impacto material recebe justificativa e não abre fix loop;
4. registrar comando, cwd, horário, saída resumida, código de retorno e fingerprint do commit medido;
5. usar `corrigir-bug` para falha de produto e repetir somente gate afetado/dependentes; mutação volta a rodar apenas no seam afetado e no `HEAD` final do gate;
6. gerar checkpoint final;
7. marcar plano `completed` somente com gates obrigatórios `passed`.

`not_run`, flake aberto ou dependência indispensável mantém `blocked`. Evidência de mutação anterior a uma alteração no seam fica obsoleta.

## 7. Release, homologação e revisão final

Quando o último plano aprovado concluir:

1. identificar RC com fingerprint completo `id`, `revision`, `build` e `checksum`, então definir `release.status: candidate`;
2. executar `homologar-sistema`, que começa por `verification.release` com suíte unitária completa configurada, integração/contratos aplicáveis, regressão completa, E2E crítico, build e evidência de mutação obrigatória;
3. somente com `homologation: accepted` e status `homologated`, revisar o release inteiro;
4. comparar spec, planos, contratos cruzados, achados adiados, segurança e diff desde a primeira `base_revision`;
5. executar verificação ampla proporcional e registrar `final_review: approved`;
6. criar `artifacts/delivery/DELIVERY.md` e definir `release.status: ready`.

Se o host não invocar skills por nome, ler e cumprir diretamente `corrigir-bug` ou `homologar-sistema`.

Manual/PDF só entra na entrega quando `manual_pdf` e o escopo exigirem.

## 8. Transição automática após encerramento legado

Quando uma fase v1 concluir todos os gates, verificação final e entrega do próprio fluxo legado, não pedir nova aprovação de migração e não iniciar outro ciclo v1.

1. concluir e commitar integralmente a fase legado; exigir `git status --porcelain` vazio;
2. executar somente então:

```bash
<bm.py> legacy-transition --repo <repo> --state <PROJECT_STATE.md> --completed
```

3. confirmar que o estado legado foi preservado em `docs/bianchini/legacy/transitions/`, que o estado ativo valida como v2 `idle` e que `repo-hygiene check` passa;
4. não editar conteúdo livre de `AGENTS.md` ou `CLAUDE.md`; se já existir bloco entre `<!-- bianchini-method:start -->` e `<!-- bianchini-method:end -->`, limitar qualquer atualização a ele, senão apenas relatar sugestão;
5. validar novamente e criar commit local atômico `chore: transition completed legacy project to Bianchini Method v2`;
6. confirmar árvore limpa. O próximo escopo usa `/sdd-planning` standalone com `planning_version: v1`.

`--completed` nunca basta sozinho: o CLI exige marcador objetivo no estado ou `--completion-proof` rastreado e commitado. A transição não reexecuta nem converte o plano concluído. Se qualquer precondição falhar, manter v1 e bloquear sem escrita parcial deliberada.

## Paradas

Parar por Superpowers ausente em v1, estado/snapshot inválido, worktree insegura, aprovação ausente, mudança de contrato, defeito direto bloqueante, ação sensível sem autorização, breaker, gate irrecuperável ou dependência externa indispensável.

## Saída

Informar rota, planos/modos, workspaces, gates, homologação, revisão final, commits, ledgers/checkpoints, transição legado → v2 quando aplicável, manual e bloqueios. Não fazer push, merge, deploy ou publicação por inferência.
