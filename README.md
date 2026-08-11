# Bianchini Method v2 — Standalone Adaptive

Sistema de seis skills para planejar, executar, auditar, corrigir, homologar e acompanhar projetos em diferentes stacks.

## Fluxo v2

```text
escopo aprovado
  -> sdd-planning
  -> aprovação única
  -> executar-plano
  -> gates por plano
  -> homologar-sistema (automação primeiro)
  -> revisão final
  -> entrega
```

`status-projeto` é somente leitura. `corrigir-bug` é usado dentro da execução e homologação.
`auditar-arquitetura` é manual, report-only e executada apenas sob pedido explícito.

## Compatibilidade

### Projetos v1

```yaml
method_version: 1 # ou estado legado existente sem method_version
```

Continuam integralmente no fluxo legado Superpowers. A v2 preserva caminhos, ledger, dispatch, revisão e retomada existentes. Se Superpowers não estiver disponível, a execução v1 bloqueia claramente; nunca usa o executor standalone nem migra automaticamente.

### Projetos v2

```json
{
  "method_version": 2,
  "method_mode": "standalone-adaptive"
}
```

Não dependem do Superpowers. Usam estado validado, worktree obrigatória, artefatos persistentes e gates nativos do projeto.

## Política adaptativa

| Risco | Execução | Revisão | Testes |
|---|---|---|---|
| baixo | `grouped` | gate do plano | por seam do grupo |
| médio | `slice` | por slice vertical | por seam do slice |
| alto/crítico | `strict` | por tarefa | RED/GREEN por tarefa |

Fix rounds: Lean 2, Standard 3, Full 5. Não há quantidade mínima de tarefas ou agentes.

## Skills

- `sdd-planning`: spec, planos, política, gates e aprovação única.
- `executar-plano`: execução v1 legado ou v2 isolada/adaptativa.
- `auditar-arquitetura`: relatório manual de hotspots e mudanças recentes.
- `status-projeto`: estado, gates, bloqueios e próximo passo, sem mutação.
- `corrigir-bug`: causa raiz, regressão adequada ao seam, fix mínimo e reteste.
- `homologar-sistema`: regressão/E2E primeiro, exploração manual das lacunas e aceite.

## Estado e ferramentas

- Schema: [`schemas/project-state.schema.json`](schemas/project-state.schema.json).
- Template: [`skills/_shared/STATE_TEMPLATE.md`](skills/_shared/STATE_TEMPLATE.md).
- CLI standalone: [`scripts/bm.py`](scripts/bm.py), empacotado também em `skills/_shared/scripts/bm.py`.

O CLI usa somente a biblioteca padrão Python e fornece:

```text
validate-state  route  snapshot  policy  workspace(create|check|locate|resume)
task-brief  report  review-package  checkpoint  proof-map  telemetry  status
```

Implementação v2 em `main`, `master`, detached HEAD ou worktree primária é bloqueada.

`workspace create` também exige repositório limpo e pacote aprovado integralmente commitado. A identidade inclui ciclo e plano (`bm/v1-p01`, `bm/v2-p01`), impedindo reuso acidental entre planejamentos.

## Homologação e manual

Homologação executa `verification.release`, E2E codificado e cria mapa de provas antes de interação manual. A exploração cobre somente lacunas, comportamento visual, acessibilidade, plataforma e integrações não provadas.

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

Nenhuma instalação ou sincronização é executada automaticamente.

## Uso

```text
/sdd-planning
/auditar-arquitetura
/executar-plano all
/status-projeto
/corrigir-bug <sintoma>
/homologar-sistema
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

Os testes usam projetos-fixture v1 legado, v2 grouped e v2 strict, além de cenários temporários para worktree, path traversal, fingerprints antigo/incorreto, telemetria opt-in, breaker, homologação automation-first, bug visual, auditoria e manual fora do escopo.
