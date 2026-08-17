# Contrato do Bianchini Method

Referência normativa das sete skills. Use [`scripts/bm.py`](scripts/bm.py) para decisões frágeis e repetíveis; não reimplemente essas primitivas em prompts.

## Execução direta explícita

`/executar-direto` é um fluxo independente e opt-in para uma entrega única, coesa e de risco baixo ou médio localizado. Ele não altera o roteamento v1/v2, não cria `PROJECT_STATE.md` e não invoca Superpowers. O CLI mantém `BRIEF.md`, `PROGRESS.md`, `RESULT.md` e estado mínimo em `.superpowers/bianchini/direct/<slug>/`, sempre ignorado pelo Git e confinado ao repositório.

```bash
bm.py direct start --repo <repo> --slug <slug> --objective <objetivo> --scope <escopo> --current-state <síntese factual> --acceptance <critério> --verification <comando>
bm.py direct status --repo <repo> [--slug <slug>]
bm.py direct checkpoint --repo <repo> --slug <slug> --checkpoint <marco> --next-action <ação>
bm.py direct finish --repo <repo> --slug <slug> --status completed --next-action <ação>
bm.py direct reopen --repo <repo> --slug <slug> --next-action <ação>   # somente execução blocked
```

O início bloqueia detached HEAD e alterações não reconhecidas, registra `/.superpowers/` em `.git/info/exclude` sem tocar o `.gitignore` do projeto, confirma que o scratch não aparece no `git status`, cria `bm/direct/<slug>` quando necessário e escala hazards estruturais para `/sdd-planning` antes de implementar o risco. Não cria worktree, planos, spec, auditoria, homologação completa ou manual.

O brief tem identidade por digest (objetivo, estado atual, escopo, não objetivos, aceite, risco, tipo de mudança, hazards, subsistemas e comandos de verificação): retomada exige digest igual; digest diferente bloqueia e pede novo slug ou `--update-brief` explícito. `finish --status completed` usa evidência estruturada registrada por `checkpoint --evidence` (JSON com `kind`, `status`, `summary`, e `command`/`exit_code` ou `evidence`): exige estado `active`, verificação `passed`, todos os comandos planejados cobertos por evidência aprovada com `exit_code: 0` ou dispensados via `--waive-verification "comando: justificativa"`, nenhuma evidência atual `failed`/`blocked`/`not_run` nem obsoleta (cada evidência é carimbada com digest do brief e fingerprint da árvore; brief ou código alterado depois do registro invalida a prova, e `--update-brief` zera verificação e evidências), ao menos um comportamento entregue, nenhum bloqueio aberto e nenhuma alteração fora de `changed_files` (aceite explícito só com `--accept-unrecorded "caminho: justificativa"`). `blocked` e `escalated` exigem motivo via `--blocker` ou `--limitation`. `completed`, `blocked` e `escalated` são terminais; escalado nunca vira concluído; apenas `blocked` pode ser reaberto preservando o resultado anterior.

## Roteamento v1/v2

Com estado existente, execute `bm.py route docs/living/PROJECT_STATE.md`. Sem estado, execute `bm.py route --repo <repo> --new-project`; artefatos `docs/superpowers/` vencem a flag de projeto novo.

### Projeto v1

`method_version: 1` sempre usa o fluxo legado baseado em Superpowers. Um arquivo sem marcador só é v1 implícito quando `load_state` encontra evidência reconhecida, como `docs/superpowers/`; JSON corrompido ou arquivo desconhecido bloqueia. Localize a instalação e passe `--superpowers-path <caminho>` ao roteador.

- Superpowers disponível: devolver `v1-superpowers` e seguir integralmente o fluxo legado, seus caminhos, ledger, dispatch, revisão e retomada.
- Superpowers ausente: `BLOQUEADO`; informar a dependência e não executar com o motor v2.
- Nunca migrar, renumerar, normalizar estado ou criar artefatos v2 no meio de uma fase legado.

Durante um ciclo ativo, migração para v2 só existe após autorização explícita do responsável. Nesse caso, executar `bm.py route --repo <repo> --new-project --migrate-to-v2`, preservar planos legados sob `docs/` como históricos e criar um estado bootstrap v2 com `planning_status: in_progress`. Para regras do repositório, respeitar exclusivamente a política delimitada abaixo. O bootstrap pode ter `plans: []` somente enquanto o novo planejamento ainda está sendo produzido; antes de `pending_approval`, deve existir ao menos um plano completo.

### Encerramento definitivo do legado

Depois que o executor v1 concluir e commitar todos os gates, verificação final e entrega, a migração deixa de exigir nova aprovação e passa a ser parte obrigatória do encerramento:

```bash
bm.py legacy-transition --repo <repo> --state <PROJECT_STATE.md> --completed [--completion-proof <arquivo>]
```

O comando exige repositório Git limpo, estado legado commitado, `--completed` e evidência objetiva de conclusão. Aceita marcador final reconhecido no estado; sem marcador, `--completion-proof` deve apontar para arquivo regular, sem symlink, rastreado e commitado no HEAD, com evidência de gates, entrega ou aceite. O resultado registra caminho e SHA-256 do proof. Depois preserva os bytes legados em `docs/bianchini/legacy/transitions/PROJECT_STATE-v1-final.md`, aplica a higiene de `/.superpowers/`, substitui o estado ativo por v2 `idle` e prepara as mudanças no índice.

Nunca editar conteúdo livre de `AGENTS.md` ou `CLAUDE.md` durante a transição. Sem seção já delimitada por `<!-- bianchini-method:start -->` e `<!-- bianchini-method:end -->`, apenas relatar uma sugestão; com marcadores, qualquer edição fica limitada ao bloco.

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

## Estratégia adaptativa de testes

Regressão é uma estratégia transversal: ela reaproveita unitários, integração/contrato e E2E para provar que comportamento anterior não foi quebrado. Unitários, integração/contrato, E2E e mutation testing são famílias de gate; não são tarefas independentes, fases novas, revisões extras ou um subagente por camada.

A composição obrigatória é proporcional ao estágio:

- `verification.fast`: unitários focados quando lógica mudou, integração/contrato focada quando uma fronteira mudou e regressão diretamente relacionada. E2E focado só entra quando for o menor seam público capaz de provar a unidade; nunca executar a suíte E2E completa ou mutação aqui.
- `verification.plan`: suítes dos módulos e fronteiras afetadas, regressão do plano, E2E das jornadas críticas entregues e mutação seletiva quando `bm.py policy` exigir.
- `verification.release`: suíte unitária completa configurada, integração/contratos aplicáveis, E2E de todas as jornadas críticas, regressão completa configurada, build do RC e evidência de mutação vigente quando obrigatória. “Completa” significa os comandos de release aprovados, não toda combinação possível de plataforma ou tela.

Política de mutation testing:

- `not_required`: risco baixo ou mudança puramente visual, documental ou mecânica;
- `selective`: risco médio com regra material, cálculo, parser, permissão, estado ou transformação; usar somente seams alterados e ferramenta já existente ou aprovada;
- `required_selective`: risco alto/crítico com regra material; o planejamento deve declarar comando e escopo antes da execução.

Não usar score global de mutação como gate nem perseguir percentual. Um mutante sobrevivente só bloqueia quando prova que um comportamento aprovado de risco alto ou crítico pode mudar sem o teste falhar. Mutante equivalente, inalcançável ou sem impacto material recebe justificativa curta e não abre fix loop. Nunca instalar ferramenta de mutação durante uma unidade; ausência de ferramenta obrigatória deve ser resolvida no planejamento ou registrada como bloqueio antes da implementação.

Após correção, reexecutar apenas a regressão afetada e vizinhos de risco. `verification.plan` e `verification.release` voltam a executar somente em seus gates. Evidência de mutação pertence ao commit/RC medido e fica obsoleta após alteração no seam.

Usar os fix rounds máximos retornados por `bm.py policy`. O orçamento é contado por `risk_seam`, não por nome de tarefa ou plano: registrar o seam de risco no ledger a cada rodada e recalcular `bm.py policy` com `--risk-seam` e `--seam-round` acumulado do seam. Renomear, dividir ou reabrir a unidade não zera a contagem do mesmo seam.

O breaker dispara na primeira destas condições:

- contagem acumulada do seam atinge o máximo do perfil;
- dois pareceres consecutivos com finding critical/important no mesmo seam (`--consecutive-seam-findings`);
- qualquer finding de classe estrutural (`--structural-finding`): crash window, partial commit, TOCTOU, efeito externo antes de persistência, retry após timeout, idempotência concorrente ou recuperação após restart.

Com `breaker: true` ou `redesign_required: true`, a hipótese atual está invalidada: parar patches imediatamente. Antes de qualquer novo patch no seam, produzir e registrar redesenho com máquina de estados, limites transacionais, operações irreversíveis, pontos de crash, atores concorrentes, estado durável de retomada e matriz de falhas; problema estrutural bloqueia o plano. A menor mudança aceitável é a menor que torna o invariante verdadeiro; preservar uma coreografia comprovadamente insegura não é mudança mínima, é hipótese inválida.

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

O pacote contém escopo local, pesquisa da stack, spec, planos, revisão de planejamento e decisões contratuais. Se o escopo existir somente na conversa/URL mutável, materializar `docs/bianchini/vN/inputs/APPROVED_SCOPE.md`.

## Pesquisa e simplificação do planejamento

Todo novo planejamento v2 usa `planning.quality_version: 1`, registra `planning.research_mode` e inclui `STACK_RESEARCH.md`. Selecionar o menor modo suficiente: `repo_only` para stack estabelecida sem integração/decisão sensível nova; `targeted_web` para API, biblioteca, pagamento, autenticação, mobile, infraestrutura ou decisão sensível a versão; `full` somente para garantia Full explícita, auditoria/regulação, arquitetura nova de alto impacto ou várias decisões críticas. `repo_only` inventaria manifests, lockfiles, CI, testes e padrões locais sem exigir URL. Os modos web exigem fontes primárias oficiais, URL e data. Registrar sempre o modo, o motivo e somente decisões aplicadas.

O escopo aprovado define resultados e invariantes, não a decomposição operacional. Preservar 100% dele; simplificar implementação nunca significa retirar requisito. Reescrever planos legados ou externos em slices de entrega autocontidos; execução nunca deve depender de `inputs/`, `docs/superpowers/` ou “PLANO Task N”. Setup, lint, documentação e baseline entram na primeira entrega que os utiliza. Regressão final, evidências, execução real do RC e varredura visual pertencem aos gates e a `homologar-sistema`, salvo artefato distribuível independente contratado.

Antes do snapshot, executar:

```bash
bm.py planning-audit docs/living/PROJECT_STATE.md --root <repo> --strict
```

O gate exige pesquisa proporcional, unidades completas, comandos reproduzíveis e orçamento proporcional ao perfil. Seguir os limites e a recomendação retornados por `planning-audit`; eles têm fonte executável única no CLI, são tetos e nunca metas ou mínimos. Exceder o perfil exige escalar mantendo todo o escopo. Acima de Full, usar `indivisible` com justificativa e otimizar contexto; nunca reduzir escopo automaticamente.

`deferred_scope` não é ferramenta de economia. Só pode conter requisito aprovado quando o responsável tiver autorizado explicitamente a divisão antes do planejamento, com `scope_split_approved: true`, autor e horário. Sem essa prova, o audit e o snapshot bloqueiam. “Menor ciclo”, simplicidade, custo ou limite de contexto não constituem autorização.

Estados com `planning.quality_version: 1` também executam esse gate dentro de `snapshot create|verify`; portanto, um pacote novo não consegue contornar a auditoria omitindo o comando explícito.

Criar e verificar o manifesto:

```bash
bm.py snapshot create <state> --root <repo>
bm.py snapshot verify <state> --root <repo>
```

`sha256-manifest-v1` ordena caminhos relativos e calcula hashes dos bytes. `PROJECT_STATE.md` e o manifesto não entram no próprio manifesto. Registrar aprovação explícita do digest antes de executar. O comando de execução não vale como aprovação; não existe aprovação parcial.

## Economia de contexto

- `planning-audit` informa `package_words` apenas como tamanho documental e limita contexto operacional por `shared_context_words`, `max_plan_words` e `max_execution_unit_words`;
- planejamento lê fontes uma vez e grava síntese com ponteiros;
- execução lê plano atual e somente seus `spec_refs`;
- grouped usa um brief/revisão por grupo; slice, por slice; strict, por tarefa;
- revisor recebe brief, relatório e pacote de diff, nunca histórico inteiro;
- homologação lê critérios, gates e resumos, inventaria a superfície do RC e abre detalhes somente para executar jornadas, investigar falha ou validar divergência;
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
