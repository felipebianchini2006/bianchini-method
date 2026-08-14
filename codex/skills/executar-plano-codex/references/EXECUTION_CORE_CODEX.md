# Núcleo de Execução — Codex

Este arquivo contém somente preflight, rota, aprovação, worktree, implementação, commits, checkpoints, gates, release, homologação e entrega. Regras de convergência pertencem exclusivamente a `CODEX_CONVERGENCE.md`.

## Preflight, rota e aprovação

1. Resolver `bm.py` da instalação ativa e executar `bm.py route`.
2. Na rota v1, exigir Superpowers e executar integralmente o fluxo legado. Não misturar etapas v2 durante a fase. Após encerramento completo, executar a transição legada descrita abaixo.
3. Na rota v2, executar `bm.py validate-state` e `bm.py snapshot verify`.
4. Executar `bm.py repo-hygiene check --repo <repo>`. Exigir ignore versionado e rejeitar `.superpowers/` rastreado.
5. Aprovação `pending` só muda por aprovação explícita inequívoca do digest atual. O comando de execução não vale como aprovação.
6. Na aprovação, verificar snapshot, commitar localmente somente pacote, estado e manifesto, então exigir árvore limpa.
7. Confirmar planos em `approved_plans` e dependências concluídas.
8. Exigir `git status --porcelain` vazio antes de criar worktree. Nunca omitir, copiar ou incluir mudança preexistente em commit do planejamento.

Snapshot divergente invalida aprovação. Não classificar divergência como mudança editorial.

## Worktree isolada

Criar um workspace por plano:

```bash
<bm.py> workspace create --repo <repo> --planning-version <planning_version> --plan <plan_id> --state <PROJECT_STATE.md>
<bm.py> workspace resume --repo <repo> --planning-version <planning_version> --plan <plan_id>
<bm.py> workspace check --repo <workspace>
```

Usar `planning_version` do estado. Branch: `bm/<planning_version>-<plan_id>`. Entrar no caminho retornado antes de editar. Executar `workspace check` no início e antes de cada commit. Main, master, detached HEAD e worktree primária são proibidos. Não usar branch atual como fallback.

Aquecer dependências uma vez no workspace com gerenciador e comandos do projeto. Antes de runtime, respeitar `.mise.toml`, `mise.toml` ou configuração equivalente.

## Orquestração obrigatória de subagentes

Em toda execução de plano, inclusive `$executar-plano-codex all`, manter estes dois subagentes canônicos ativos:

- `/root/luna_max`: `task_name=luna_max`, modelo `gpt-5.6-luna`, reasoning effort `max`; lidera implementação, decisões técnicas e unidades de maior risco;
- `/root/sol_medium`: `task_name=sol_medium`, modelo `gpt-5.6-sol`, reasoning effort `medium`; lidera verificação independente, testes, gates e revisão do resultado.

Se ainda não existirem, criá-los antes da implementação. Se estiverem ociosos, reutilizá-los. Não substituir nomes, modelos ou níveis de esforço e não encerrar um deles enquanto houver trabalho executável. Quando um slot estiver temporariamente indisponível, continuar no coordenador e enfileirar o próximo dispatch para o subagente canônico assim que o slot liberar.

Maximizar paralelismo seguro em todos os planos aprovados:

1. construir uma fila global de unidades prontas a partir das dependências dos planos;
2. distribuir imediatamente unidades independentes entre `/root/luna_max`, `/root/sol_medium` e o coordenador;
3. atribuir ownership explícito e não sobreposto de arquivos, seams ou worktrees;
4. usar worktree distinta por plano e nunca editar o mesmo arquivo concorrentemente;
5. iniciar revisão, gates, documentação ou próxima unidade independente assim que suas entradas estiverem prontas, sem esperar trabalho não relacionado;
6. quando um subagente concluir, entregar imediatamente a próxima unidade pronta;
7. manter implementação e revisão do mesmo delta em agentes diferentes quando houver capacidade.

O coordenador nunca fica ocioso enquanto existir unidade, gate, checkpoint ou entrega executável. Falha local, limite de contexto, duração, orçamento interno ou agente indisponível não interrompem a fila pronta: registrar checkpoint, reatribuir ou seguir trabalho independente. Não fazer polling inútil nem repetir operação sem nova evidência.

## Execução recuperável

No ledger do plano, registrar digest aprovado, base revision, workspace, branch, modo e perfil.

Quando `telemetry.enabled: true`, registrar ao fim de cada unidade somente deltas numéricos informados pelo host: tokens, duração e falhas de gate. Não estimar tokens. Não persistir prompt, diff ou conteúdo do projeto.

Gerar pelo CLI:

- `task-brief` por grupo, slice ou tarefa, conforme modo;
- `report` persistente do implementador;
- `checkpoint` após cada unidade, falha ou bloqueio local, e antes de encerrar contexto.

Retomada começa com `workspace resume`. Ler checkpoint, estado, unidade atual e final do ledger. Não reler planos concluídos nem reconstruir estado pela conversa.

## Implementação

Antes da unidade, executar `bm.py policy` com perfil e risco. Confirmar coincidência com `execution` aprovado. Divergência pode aumentar garantia automaticamente; redução exige novo pacote aprovado.

Em cada dispatch, passar ao subagente somente brief, relatório, ownership e contexto estritamente necessário. O coordenador mantém a fila global, integra resultados e executa em paralelo outra unidade independente.

### Grouped — baixo risco

- Agrupar tarefas do mesmo seam sem conflito de ownership.
- Gerar `task-brief --tasks <intervalo>` e confirmar `kind: group`, `group_id`, hash do grupo e hashes das unidades.
- Executar `verification.fast` nos seams afetados.
- Criar commit atômico por grupo coerente.

### Slice — risco médio

- Cada slice entrega comportamento vertical observável.
- Gerar brief, relatório e teste comportamental por slice.
- Usar RED/GREEN quando teste detecta regressão real. Usar validation-first para configuração e documentação.
- Criar commit atômico por slice.

### Strict — risco alto ou crítico

- Executar uma unidade crítica por dispatch.
- Exigir teste RED pela interface pública, implementação mínima GREEN e vizinhos de risco.
- Criar commit atômico por tarefa.

Nenhum modo implementa necessidade futura. Testes observam seams públicos, não detalhes internos.

## Commits e checkpoints

Antes de cada commit:

1. executar `workspace check`;
2. inspecionar arquivos staged e excluir segredos, credenciais, `.env`, builds e artefatos indevidos;
3. executar verificações proporcionais à unidade;
4. criar commit local atômico com mensagem coerente;
5. registrar revision e evidências no ledger e checkpoint.

Não fazer push, merge, deploy ou publicação por inferência.

## Gates por plano

Depois das unidades:

1. executar todos os comandos `verification.plan` no RC atual;
2. registrar comando, cwd, horário, saída resumida e exit code;
3. repetir gates afetados e dependentes após correções;
4. gerar checkpoint final;
5. marcar plano concluído no método base somente quando gates obrigatórios estiverem `passed`.

`not_run`, flake aberto ou dependência indispensável mantém conclusão indisponível.

## Release, homologação e entrega

Quando último plano aprovado concluir:

1. identificar RC com fingerprint completo: `id`, `revision`, `build` e `checksum`;
2. definir `release.status: candidate`;
3. executar `homologar-sistema`, começando por `verification.release`;
4. exigir `homologation: accepted` e status `homologated`;
5. criar `artifacts/delivery/DELIVERY.md`;
6. definir `release.status: ready`.

Manual ou PDF entra na entrega somente quando `manual_pdf` e escopo exigirem.

## Transição após encerramento legado

Após fase v1 concluir gates, verificação final e entrega do fluxo legado:

1. commitar integralmente fase e exigir árvore limpa;
2. executar:

```bash
<bm.py> legacy-transition --repo <repo> --state <PROJECT_STATE.md> --completed
```

3. confirmar preservação do estado legado em `docs/bianchini/legacy/transitions/`, estado ativo v2 `idle` e `repo-hygiene check` aprovado;
4. não editar conteúdo livre de `AGENTS.md` ou `CLAUDE.md`; limitar atualização a bloco Bianchini Method existente, senão somente relatar sugestão;
5. validar e criar commit local atômico `chore: transition completed legacy project to Bianchini Method v2`;
6. confirmar árvore limpa.

`--completed` exige marcador objetivo no estado ou `--completion-proof` rastreado e commitado. Transição não reexecuta nem converte plano concluído.
