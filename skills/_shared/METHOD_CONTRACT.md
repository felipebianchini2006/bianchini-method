# Contrato do Bianchini Method

Referência normativa das seis skills. Use [`scripts/bm.py`](scripts/bm.py) para decisões frágeis e repetíveis; não reimplemente essas primitivas em prompts.

## Roteamento v1/v2

Com estado existente, execute `bm.py route docs/living/PROJECT_STATE.md`. Sem estado, execute `bm.py route --repo <repo> --new-project`; artefatos `docs/superpowers/` vencem a flag de projeto novo.

### Projeto v1

`method_version: 1` sempre usa o fluxo legado baseado em Superpowers. Um arquivo de estado existente sem `method_version` também é v1 por compatibilidade. Localize a instalação e passe `--superpowers-path <caminho>` ao roteador.

- Superpowers disponível: devolver `v1-superpowers` e seguir integralmente o fluxo legado, seus caminhos, ledger, dispatch, revisão e retomada.
- Superpowers ausente: `BLOQUEADO`; informar a dependência e não executar com o motor v2.
- Nunca migrar, renumerar, normalizar estado ou criar artefatos v2 no meio de uma fase legado.

Durante um ciclo ativo, migração para v2 só existe após autorização explícita do responsável. Nesse caso, executar `bm.py route --repo <repo> --new-project --migrate-to-v2`, preservar planos legados sob `docs/` como históricos, atualizar as regras do repositório e criar um estado bootstrap v2 com `planning_status: in_progress`. O bootstrap pode ter `plans: []` somente enquanto o novo planejamento ainda está sendo produzido; antes de `pending_approval`, deve existir ao menos um plano completo.

### Encerramento definitivo do legado

Depois que o executor v1 concluir e commitar todos os gates, verificação final e entrega, a migração deixa de exigir nova aprovação e passa a ser parte obrigatória do encerramento:

```bash
bm.py legacy-transition --repo <repo> --state <PROJECT_STATE.md> --completed
```

O comando exige repositório Git limpo e estado legado commitado, preserva seus bytes em `docs/bianchini/legacy/transitions/PROJECT_STATE-v1-final.md`, aplica a higiene de `/.superpowers/`, substitui o estado ativo por v2 `idle` e prepara as mudanças no índice. O executor atualiza somente as regras ativas de `AGENTS.md`/`CLAUDE.md`, valida, cria um commit local atômico e deixa a árvore limpa. O plano concluído não é convertido nem reexecutado; o próximo escopo começa standalone em `planning_version: v1`.

`--completed` nunca pode ser usado como atalho: fase em andamento, bloqueada ou não commitada permanece v1. O estado `idle` é reproduzível, não possui escopo aprovado, spec, revisão, plano, aprovação ou execução ativa. `/sdd-planning` transforma `idle` em `in_progress` somente quando houver novo escopo aprovado.

Valores legados reconhecidos apenas para leitura/status:

| Canônico | Valores v1 |
|---|---|
| `pending` | `pending`, `planned`, `pendente`, `planejado` |
| `approved` | `approved`, `aprovado` |
| `in_progress` | `in_progress`, `in-progress`, `em_andamento` |
| `completed` | `completed`, `done`, `concluido`, `concluído` |
| `blocked` | `blocked`, `bloqueado` |

### Projeto v2

`method_version: 2` e `method_mode: standalone-adaptive` usam somente o motor deste pacote. Superpowers não é lido nem necessário.

- marcador ausente sem legado: somente `sdd-planning` inicia v2;
- estado v2 `idle`: encerramento legado concluído; o próximo `/sdd-planning` é standalone e não usa Superpowers;
- marcador ausente com `docs/superpowers/vN/`: tratar como v1 provisório;
- marcador inválido, duplicado ou futuro: `BLOQUEADO`, sem downgrade.

Resolva o caminho absoluto do CLI empacotado e substitua `<bm.py>` nos comandos:

```bash
python3 <bm.py> validate-state docs/living/PROJECT_STATE.md
```

O schema canônico está em [`schemas/project-state.schema.json`](schemas/project-state.schema.json).

## Política adaptativa

Classificar cada plano pelo maior risco real e gravar `execution`, `review` e `test_seams`.

| Risco | Execution | Review | Teste |
|---|---|---|---|
| baixo | `grouped` | `plan_gate` | uma verificação por seam do grupo; sem TDD/revisão por microtarefa |
| médio | `slice` | `per_slice` | ciclo comportamental por slice vertical |
| alto/crítico | `strict` | `per_task` | RED/GREEN e revisão independente por tarefa |

Regras:

- agrupar tarefas baixas que compartilham seam e gate;
- nunca agrupar contratos, migrações ou ownership conflitante;
- não criar tarefa ou agente para satisfazer contagem mínima;
- escalar o modo quando risco descoberto aumentar; não reduzir sem atualizar plano aprovado;
- calcular política com `bm.py policy` e registrar o JSON no ledger.

Fix rounds máximos por perfil:

| Perfil | Rodadas |
|---|---|
| `lean` | 2 |
| `standard` | 3 |
| `full` | 5 |

Ao atingir o máximo, `breaker: true`: parar patches, reavaliar causa/arquitetura e bloquear se o problema for estrutural.

## Workspace obrigatório v2

Toda implementação v2 ocorre em linked worktree fora da branch principal.

```bash
python3 <bm.py> workspace create --repo . --planning-version v1 --plan P01 --state docs/living/PROJECT_STATE.md
python3 <bm.py> workspace locate --repo . --planning-version v1 --plan P01
python3 <bm.py> workspace resume --repo . --planning-version v1 --plan P01
python3 <bm.py> workspace check --repo <workspace>
```

`workspace create` bloqueia qualquer alteração tracked/untracked, exige estado e snapshot aprovados e confirma que escopo, spec, planos, revisão, estado e manifesto existem no `HEAD` com os mesmos bytes. Arquivo ignorado mas não commitado também bloqueia. A identidade usa `<planning_version>-<plan_id>` (`bm/v1-p01`, `bm/v2-p01`) para não reutilizar ciclos antigos.

`workspace check` bloqueia `main`, `master`, detached HEAD e a worktree primária. Não existe fallback para implementação na branch atual. Planejamento, status e o commit local do pacote aprovado podem ocorrer na principal; edição de código não.

## Higiene da raiz

`.superpowers/` na raiz contém somente artefatos locais/transitórios e deve estar coberto por `/.superpowers/` no `.gitignore` versionado. Nenhum arquivo sob essa raiz pode permanecer rastreado.

```bash
bm.py repo-hygiene check --repo <repo>
bm.py repo-hygiene migrate --repo <repo>
```

`migrate` exige ausência de mudanças alheias, move somente arquivos já rastreados preservando seus bytes para `docs/bianchini/legacy/root-superpowers/`, adiciona o ignore e prepara essas mudanças no índice. `docs/superpowers/` pode permanecer como histórico v1; documentos ativos v2 ficam exclusivamente em `docs/bianchini/<planning_version>/`. `workspace create` executa o check e bloqueia qualquer violação.

## Artefatos determinísticos

Para cada unidade executada, use:

```bash
bm.py task-brief --plan <plano> --tasks <1,2|1-3> --output <brief.md>
bm.py report --brief <brief.md> --output <report.md>
bm.py review-package --base <base> --head HEAD --brief <brief.md> --report <report.md> --output <review.md>
bm.py checkpoint --state <state> --ledger <ledger> --cwd <workspace> --output <checkpoint.json>
```

- `task-brief`: extrai uma tarefa, lista/intervalo ou heading explícito de grupo, preserva ordem e fixa hashes do plano e unidades;
- `report`: contrato persistente do implementador;
- `review-package`: diff completo sanitizado do intervalo, commits, brief e relatório;
- `checkpoint`: estado mínimo e caminho absoluto do workspace para retomar após compactação ou nova sessão.

## Auditoria arquitetural manual

`auditar-arquitetura` só roda por pedido explícito. Ela começa por histórico Git, hotspots e arquivos recentemente alterados, produz candidatos `Strong | Worth exploring | Speculative` e não implementa. Melhorias estruturais não bloqueiam planejamento; defeitos funcionais diretamente comprovados são separados e seguem os gates normais.

## Fingerprint do release

Um candidato ativo contém `id`, `revision`, `build` e `checksum`. Toda evidência automatizada repete os quatro campos; `proof-map` só aceita correspondência exata. Reutilizar ID com revisão, build ou checksum diferente não transfere prova.

## Telemetria opcional

Telemetria é opt-in e local. Com `telemetry.enabled: true`, registrar deltas numéricos sem prompt, código, diff, segredo ou dado pessoal:

```bash
bm.py telemetry record --state <state> --root <repo> --plan P01 \
  --phase execution --duration-ms 1200 --input-tokens 800 --output-tokens 300
bm.py telemetry summary --state <state> --root <repo>
```

As métricas suportadas são tokens de entrada/saída, duração, fix rounds, falhas de gate e bugs de homologação. O arquivo JSONL é append-only e confinado à raiz do projeto. Desabilitada, a operação não cria artefato.

O ledger é append-only. Logs completos, diffs e screenshots ficam em arquivos apontados pelo ledger.

## Aprovação única

O pacote contém escopo local, spec, planos, revisão de planejamento e decisões contratuais. Se o escopo existir somente na conversa/URL mutável, materializar `docs/bianchini/vN/inputs/APPROVED_SCOPE.md`.

Criar e verificar o manifesto:

```bash
bm.py snapshot create <state> --root <repo>
bm.py snapshot verify <state> --root <repo>
```

`sha256-manifest-v1` ordena caminhos relativos e calcula hashes dos bytes. `PROJECT_STATE.md` e o manifesto não entram no próprio manifesto. Registrar aprovação explícita do digest antes de executar. O comando de execução não vale como aprovação; não existe aprovação parcial.

## Economia de contexto

- planejamento lê fontes uma vez e grava síntese com ponteiros;
- execução lê plano atual e somente seus `spec_refs`;
- grouped usa um brief/revisão por grupo; slice, por slice; strict, por tarefa;
- revisor recebe brief, relatório e pacote de diff, nunca histórico inteiro;
- homologação lê critérios, gates e resumos, abrindo detalhe só para lacuna/falha;
- referências opcionais são carregadas na fase indicada.

## Fontes de verdade e segurança

| Informação | Fonte |
|---|---|
| comportamento | spec aprovada |
| estado | `PROJECT_STATE.md` validado |
| operação | ledger + checkpoint |
| problema aberto | `KNOWN_ISSUES.md` |
| aceite | `artifacts/qa/final/<data>/SUMMARY.md` |
| entrega | `artifacts/delivery/DELIVERY.md` |

Sem autorização explícita, não alterar produção, cobrar, publicar, enviar mensagem real, apagar dados, executar migração destrutiva ou expor segredo/dado pessoal.
