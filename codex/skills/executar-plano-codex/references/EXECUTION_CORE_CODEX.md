# Núcleo de Execução — Codex

Este arquivo contém somente preflight, rota, aprovação, worktree, implementação, commits, checkpoints, gates, release, homologação e entrega. Regras de convergência pertencem exclusivamente a `CODEX_CONVERGENCE.md`.

## Preflight, rota e aprovação

1. Resolver `bm.py` da instalação ativa e executar `bm.py route`.
2. Na rota v1, exigir Superpowers e executar integralmente o fluxo legado. Não misturar etapas v2 durante a fase. Após encerramento completo, executar a transição legada descrita abaixo.
3. Na rota v2, executar `bm.py validate-state` e `bm.py snapshot verify`. Em `planning.quality_version: 2`, exigir readiness válido e checker `passed` no digest aprovado.
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

## Execução recuperável

No ledger do plano, registrar digest aprovado, base revision, workspace, branch, modo e perfil.

Quando `telemetry.enabled: true`, registrar ao fim de cada unidade somente deltas numéricos informados pelo host: tokens, duração e falhas de gate. Não estimar tokens. Não persistir prompt, diff ou conteúdo do projeto.

Gerar pelo CLI:

- `task-brief` por grupo, slice ou tarefa, conforme modo;
- `report` persistente do implementador;
- `checkpoint` após cada unidade, falha ou bloqueio local, e antes de encerrar contexto.

Retomada começa com `workspace resume`. Ler checkpoint, estado, unidade atual e final do ledger. Não reler planos concluídos nem reconstruir estado pela conversa.

## Implementação

Antes da unidade, executar `bm.py policy` com perfil, risco e `Change` declarado no brief; planos antigos sem `Change` usam `behavioral` somente por compatibilidade. Confirmar coincidência com `execution` aprovado. Divergência pode aumentar garantia automaticamente; redução exige novo pacote aprovado.

Quando o host suportar subagentes e seu uso for apropriado, passar ao implementador somente brief, relatório, ownership e contexto estritamente necessário. Não fixar nome, modelo, reasoning effort, hierarquia ou quantidade de subagentes: usar os padrões atuais do host. Sem subagentes, cumprir a mesma responsabilidade inline.

## Autonomia e plano congelado

O plano aprovado permanece congelado. Antes de alterar decomposição, comandos, contratos ou design, executar `bm.py change-policy` e seguir uma destas classes:

- `implementation_detail`: decisão técnica interna e reversível. Escolher a opção reversível de menor risco, registrar no relatório e continuar;
- `bounded_amendment`: ajuste limitado de arquivo, comando ou ordem interna sem mudar entrega. Registrar no ledger/checkpoint e continuar, sem nova unidade, revisor ou aprovação;
- `material_change`: mudança de escopo, contrato público, design aprovado ou invariante crítico. Não editar o plano nem improvisar; usar a categoria `material_change` do contrato de convergência com prova estruturada.

A ordem automática é: decisão aprovada, padrão existente no repositório, stack já usada, documentação oficial e opção reversível de menor risco. Ler `USER_ACTIONS.md` uma vez e continuar com fakes, sandbox ou trabalho independente até o ponto em que a ação externa seja indispensável. Decisão interna não gera pergunta, nova decomposição ou revisão extra.

## Profundidade de testes sem overengineering

Na implementação de cada unidade, executar somente `verification.fast`: unitário focado quando lógica mudou, integração/contrato focada quando uma fronteira mudou e regressão diretamente relacionada. E2E focado só entra quando for a menor prova pública da unidade; não executar E2E completo, regressão completa ou mutação por unidade.

Uma família de teste não cria unidade, dispatch, revisor ou subagente. Não dividir uma tarefa aprovada em “unitários”, “integração”, “E2E” e “mutação”, não criar campanha de cobertura e não despachar agente para gate mecânico. O mesmo implementador executa os comandos aplicáveis e registra proofs.

No `verification.plan`, executar suítes afetadas, regressão do plano e E2E das jornadas críticas entregues. Quando `bm.py policy` exigir mutation testing, fazer uma execução seletiva por seam de risco no `HEAD` final do gate, usando somente ferramenta e comando aprovados. Não instalar ferramenta, não perseguir score global e não repetir mutação após cada fix. Mutante sem prova de que altera comportamento aprovado de risco alto/crítico vira hardening adiado; mutante equivalente ou inalcançável recebe justificativa curta.

No `verification.release`, usar os comandos aprovados para suíte unitária completa configurada, integração/contratos aplicáveis, regressão completa, E2E de todas as jornadas críticas, build e evidência de mutação vigente quando obrigatória. Homologação apenas confirma essa baseline e opera o RC real; não abre outra campanha automatizada.

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

1. executar todos os comandos `verification.plan` no RC atual, respeitando o limite de profundidade acima;
2. registrar cada comando como proof do `HEAD` atual, incluindo a mutação seletiva exigida;
3. repetir somente gates afetados e dependentes após correções; mutação volta a rodar apenas no seam alterado e no `HEAD` final;
4. registrar comando, cwd, horário, saída resumida e exit code;
5. gerar checkpoint final;
6. marcar plano concluído no método base somente quando gates obrigatórios estiverem `passed`.

`not_run`, flake aberto ou dependência indispensável mantém conclusão indisponível. Evidência de mutação anterior a alteração no seam é inválida.

## Release, homologação e entrega

Quando último plano aprovado concluir:

1. identificar RC com fingerprint completo: `id`, `revision`, `build` e `checksum`;
2. definir `release.status: candidate`;
3. executar `homologar-sistema`, começando por `verification.release` completo e proporcional, sem criar novas unidades de teste;
4. exigir `homologation: accepted` e status `homologated`;
5. criar `artifacts/delivery/DELIVERY.md`;
6. definir `release.status: ready`;
7. em `planning.quality_version: 2`, executar `bm.py cycle-close` para sincronizar deltas nas specs atuais, arquivar o ciclo e preparar o próximo estado `idle`.

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
