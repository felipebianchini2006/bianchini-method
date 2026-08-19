# Bianchini Method v3.2 — Self Update

`v3.2` é a versão do pacote. `method_version` permanece `2` para preservar compatibilidade dos projetos standalone existentes.

Sistema de nove skills para planejar, executar, auditar, corrigir, homologar e acompanhar projetos em diferentes stacks.

| Situação | Fluxo |
|---|---|
| Tarefa pontual ou experimento | Superpowers diretamente |
| Projeto pequeno ou entrega coesa | `/executar-direto` |
| Projeto complexo, multifase ou de alto risco | `/sdd-planning` + `/executar-plano` |

## Fluxo atual

```text
escopo aprovado
  -> design-projeto, somente para UI nova/material sem design válido
  -> readiness: decisões, suposições, pitfalls, ações externas e spikes
  -> sdd-planning
  -> checker semântico, no máximo duas passagens
  -> aprovação única
  -> executar-plano com autonomia e plano congelado
  -> gates por plano
  -> homologar-sistema: automação + uso real do RC
  -> revisão final e entrega
  -> cycle-close: sincronizar specs atuais e arquivar ciclo
```

`sdd-planning` valida readiness, pesquisa a stack, aplica decisões e pitfalls à spec e congela planos sem reduzir o escopo aprovado. `status-projeto` é somente leitura. `corrigir-bug` é usado dentro da execução e homologação.
`auditar-arquitetura` é manual, report-only e executada apenas sob pedido explícito.

## Compatibilidade

### Projetos v1

```yaml
method_version: 1 # ou estado legado existente sem method_version
```

Continuam integralmente no fluxo legado Superpowers enquanto a fase atual estiver em andamento. A v2 preserva caminhos, ledger, dispatch, revisão e retomada existentes. Se Superpowers não estiver disponível, a execução v1 bloqueia claramente; nunca usa o executor standalone no meio da fase.

Quando o responsável autorizar explicitamente, `route --migrate-to-v2` inicia uma migração controlada: preserva documentação v1 sob `docs/` e cria um estado bootstrap v2. `AGENTS.md` e `CLAUDE.md` nunca são reescritos livremente. Sem essa autorização, a compatibilidade legado continua vencendo.

Ao concluir e commitar todos os gates e a entrega da última fase legado, `executar-plano` roda `legacy-transition --completed`: arquiva o estado v1, aplica a higiene da raiz e cria um estado v2 `idle`. O próximo escopo abre `planning_version: v1` por `/sdd-planning` standalone, sem nova aprovação de migração e sem reexecutar a fase encerrada.

### Projetos v2

```json
{
  "method_version": 2,
  "method_mode": "standalone-adaptive"
}
```

Não dependem do Superpowers. Usam estado validado, worktree obrigatória, artefatos persistentes e gates nativos do projeto.

## Estabilidade e autonomia

Novos ciclos usam:

```text
docs/bianchini/current/specs/      -> comportamento atual aceito
docs/bianchini/changes/vN/         -> mudança atual
docs/bianchini/archive/vN/         -> ciclo encerrado
docs/design/vN/                    -> protótipo e contrato visual aprovados
```

`READINESS.md` resolve antes do plano:

```text
D-* decisões
A-* suposições
P-* pitfalls
U-* ações externas
S-* spikes
DS-* superfícies visuais
SD-* próximas specs de domínio
```

O checker permite uma correção. Depois da aprovação, detalhes internos e ajustes limitados são registrados no ledger sem editar o plano. Escopo, contrato público, design aprovado, impossibilidade externa ou invariante crítico comprovado invalidam o plano apenas na área afetada. Novo custo ou ação irreversível apenas pausam para autorização; não autorizam redesign por si só.

A ordem autônoma é: decisão aprovada -> padrão do repositório -> stack existente -> documentação oficial -> opção reversível de menor risco. O agente não interrompe por escolha técnica interna.

## Política adaptativa

| Risco | Execução | Revisão | Testes |
|---|---|---|---|
| baixo | `grouped` | gate do plano | unitário/integração/regressão focados; sem mutação |
| médio | `slice` | por slice vertical | focados por slice; E2E crítico e mutação seletiva no gate |
| alto/crítico | `strict` | por tarefa | RED/GREEN focal; mutação seletiva obrigatória no gate material |

As camadas são distribuídas por estágio, sem nova tarefa por tipo de teste:

```text
verification.fast
  -> unitários focados + integração/contrato focada + regressão relacionada

verification.plan
  -> suítes afetadas + regressão do plano + E2E crítico + mutação seletiva

verification.release
  -> suíte completa configurada + contratos + regressão + E2E crítico + build + mutação exigida

homologar-sistema
  -> confirmar provas do RC + operar sistema real + varredura visual
```

Regressão é transversal, não uma suíte separada. Mutation testing nunca roda por microtarefa, não usa score global como meta e só bloqueia quando um survivor prova falha de teste em comportamento aprovado de risco alto/crítico. O overlay Codex mantém esses limites explicitamente para não reabrir tarefas, revisões ou subagentes por camada.

Os fix rounds são retornados por `bm.py policy` e contados por `risk_seam`: renomear ou dividir a tarefa não zera o orçamento do mesmo seam. Finding de classe estrutural (crash window, partial commit, TOCTOU, retry após timeout, idempotência concorrente, recuperação após restart) ou dois pareceres consecutivos critical/important no mesmo seam disparam o breaker antecipado e exigem redesenho antes de novo patch. Não há quantidade mínima de tarefas ou agentes.

## Skills

- `design-projeto`: protótipo HTML estático, tokens, contrato e manifesto visual ligados ao escopo.
- `sdd-planning`: pesquisa atual da stack, spec, simplificação, planos, gates e aprovação única.
- `executar-plano`: execução v1 legado ou v2 isolada/adaptativa.
- `executar-direto`: entrega pequena e coesa com brief compacto, scratch ignorado, verificação obrigatória para conclusão e estados terminais; invocação exclusivamente manual por `/executar-direto`.
- `auditar-arquitetura`: relatório manual de hotspots e mudanças recentes; invocação exclusivamente manual.
- `status-projeto`: estado, gates, bloqueios e próximo passo, sem mutação.
- `corrigir-bug`: causa raiz, regressão adequada ao seam, fix mínimo e reteste.
- `homologar-sistema`: confirma unitários/integração/regressão/E2E/mutação do release, executa o RC real por perfil/plataforma, faz varredura visual e decide o aceite.
- `update-bm`: verifica a versão oficial e atualiza a instalação local com backup e rollback; invocação exclusivamente manual.

### Contratos internos de subagentes

`skills/_shared/agents/` contém contratos enxutos e agnósticos de stack para cartografia, implementação, revisão e segurança. A homologação mantém o passe real e a validação visual diretamente em sua própria skill, sem depender de prompt externo. `/executar-direto` não utiliza subagentes. Origem adaptada do projeto Agency Agents (MIT); ver [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

## Estado e ferramentas

- Schema: [`schemas/project-state.schema.json`](schemas/project-state.schema.json).
- Template: [`skills/_shared/STATE_TEMPLATE.md`](skills/_shared/STATE_TEMPLATE.md).
- CLI standalone: [`scripts/bm.py`](scripts/bm.py), empacotado também em `skills/_shared/scripts/bm.py`.

O CLI usa somente a biblioteca padrão Python e fornece:

```text
validate-state  route  legacy-transition  design-audit  planning-audit  planning-check
change-policy  cycle-close  snapshot  policy  workspace(create|check|locate|resume)
repo-hygiene(check|migrate)  task-brief  report  review-package
checkpoint  proof-map  spec-diff  mutation-evidence  update-bm  telemetry  status
```

Implementação v2 em `main`, `master`, detached HEAD ou worktree primária é bloqueada.

`workspace create` também exige repositório limpo e pacote aprovado integralmente commitado. A identidade inclui ciclo e plano (`bm/v1-p01`, `bm/v2-p01`), impedindo reuso acidental entre planejamentos.

Novos planejamentos incluem `STACK_RESEARCH.md` em modo `repo_only`, `targeted_web` ou `full`. `planning-audit --strict` retorna os limites vigentes, bloqueia evidência insuficiente, placeholders, comandos em prosa e planos dependentes de fontes legadas. Lean permanece tipicamente pequeno e sem mínimo; Standard e Full absorvem escopos/risco maiores sem retirar requisitos aprovados. Qualquer `deferred_scope` exige autorização explícita registrada do responsável. O snapshot reaplica o gate automaticamente.

`/.superpowers/` deve estar no `.gitignore` versionado e nunca pode conter arquivos rastreados. `repo-hygiene migrate` preserva relatórios legados rastreados em `docs/bianchini/legacy/root-superpowers/`; mudanças ativas ficam em `docs/bianchini/changes/<planning_version>/`; specs aceitas ficam em `docs/bianchini/current/specs/`.

## Eficiência de contexto

A v3.1 mantém as fontes completas e adiciona projeções determinísticas para reduzir leitura ativa:

- `planning-audit` exige `Change` e `Readiness refs` nas unidades quality v2;
- `task-brief --hydrate-context` reúne somente readiness, specs, gates e ledger aplicáveis;
- `spec-diff` deriva ADDED, MODIFIED e REMOVED entre specs completas;
- `mutation-evidence verify` vincula relatório, seam, plano e revisão do código sem usar score global.

Detalhes: [`skills/_shared/CONTEXT_EFFICIENCY.md`](skills/_shared/CONTEXT_EFFICIENCY.md).

## Homologação e manual

Homologação executa `verification.release` com unitários, integração/contratos, regressão, E2E crítico, build e mutação exigida, depois cria o mapa de provas como baseline. Depois abre e opera o RC real por plataforma e perfil, percorre fluxos críticos e ações primárias, verifica estados de erro/recuperação, console/rede e executa varredura visual em toda interface aplicável.

`manual_pdf: scope` é o padrão. Os valores são `none | quick_start | full | scope`; ausência de conversor não bloqueia projeto sem manual contratado.

Cada release candidate usa fingerprint obrigatório `id + revision + build + checksum`. Evidências de homologação só valem quando os quatro valores coincidem.

## Telemetria opt-in

Desabilitada por padrão. Quando habilitada no estado, registra localmente tokens informados pelo host, duração, fix rounds, falhas de gate e bugs de homologação. Não registra prompts, código, diffs ou dados pessoais.

`bm.py status <state> --root <repo> --format text` produz o painel humano; sem `--format text`, mantém JSON estável para automação.

## Instalação local

Copie o diretório `skills` inteiro para preservar recursos compartilhados:

```bash
cp -R skills/. ~/.codex/skills/
# Claude Code: troque ~/.codex por ~/.claude
```

Após esta instalação, verifique ou atualize explicitamente com:

```bash
python3 ~/.codex/skills/_shared/scripts/bm.py update-bm --check
python3 ~/.codex/skills/_shared/scripts/bm.py update-bm
```

No Claude Code, troque `~/.codex` por `~/.claude`. Também é possível usar `/update-bm`. Nenhuma sincronização ocorre sem invocação explícita.

## Uso

```text
/design-projeto
/sdd-planning
/executar-direto
/auditar-arquitetura
/executar-plano all
/status-projeto
/corrigir-bug <sintoma>
/homologar-sistema
/update-bm
```

## Overlay Codex

```bash
./codex/install.sh
```

```text
$executar-plano-codex all
```

## Validação do pacote

```bash
python3 scripts/run_test_shards.py
python3 scripts/bm.py --help
```

O runner recomendado executa cada classe em processo separado e libera recursos entre shards. A forma monolítica continua disponível para ambientes sem limitação:

```bash
python3 -m unittest discover -s tests -v
```

Os testes usam projetos-fixture v1 legado, v2 grouped e v2 strict, além de cenários temporários para design manifest, readiness, checker limitado, specs atuais/deltas, cycle-close, worktree, path traversal, fingerprints antigo/incorreto, telemetria opt-in, breaker, homologação com automação e execução real, bug visual, auditoria e manual fora do escopo.
