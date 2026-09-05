# Bianchini Method

Método spec-driven para planejar e executar mudanças com visão do sistema completo, coerência entre fases, documentação viva e verificação proporcional ao risco.

O Bianchini Method usa um CLI Go nativo como backend oficial. Consulte `bm version --json` para saber a versão instalada. O Python permanece no repositório somente como oráculo explícito de compatibilidade; não há fallback automático entre linguagens.

A versão 1.0 exige provas completas dos gates, valida o artefato de entrega e distingue decisão técnica de aprovação humana. Consulte [migração e reprodução](docs/workflow-v1.md).

O planejamento representa um grafo de contratos:

```text
sistema atual
→ sistema após cada fase
→ sistema final esperado
```

## Arquitetura

```text
Bianchini Method
├── MethodWorkspace
├── ScopeIntake
├── ProjectModel
├── CoherenceEngine
│   ├── StructuralValidator
│   ├── DependencyGraph
│   ├── ImpactAnalyzer
│   └── SemanticReviewer
├── Planning
├── Execution
├── Quick
├── Debug
└── Migration
```

- `MethodWorkspace`: caminhos, IDs, digests, transações e DocViva.
- `ProjectModel`: representação tipada e derivada do sistema; não é outra fonte de persistência.
- `StructuralValidator`: IDs, referências, ordem, providers, consumers, ownership, migrações e journeys.
- `ImpactAnalyzer`: consumidores e planos afetados por uma alteração.
- `SemanticReviewer`: simplicidade, responsabilidade arquitetural, stack e coerência interpretativa.

## Organização do repositório

- `cmd/`, `internal/` e `tools/`: CLI Go e empacotamento da release.
- `skills/`: instruções, recursos e oráculo de compatibilidade.
- `tests/`, `contracts/` e `schemas/`: testes e contratos executáveis.
- `scripts/` e `reports/evolution-0.4.7/`: validação, exemplos e baselines usados pelos testes.
- `docs/` e `codex/`: documentação e integração com o agente.

O estado de desenvolvimento deste repositório e os relatórios pontuais de validação foram retirados da árvore de arquivos. Permanecem no histórico Git, até o commit `e5bc8e6`. Binários e caches locais são ignorados.

## Workspace dos projetos

Nos projetos que usam o método, `.bianchini/` guarda o escopo, os planos, as provas e o estado de execução. Ela é criada pelo CLI e continua fazendo parte do projeto atendido; não precisa acompanhar o código-fonte da ferramenta.

A versão mostrada em status e entregas vem de `bm version --json`, campo `version`. O valor `method: "0.4"` encontrado em estados antigos é um identificador interno do formato dos dados, preservado por compatibilidade.

```text
.bianchini/
├── PROJECT.md
├── STATE.md
├── current/
│   ├── ARCHITECTURE.md
│   ├── SYSTEM_MODEL.md
│   └── specs/
├── changes/C001-slug/
│   ├── SCOPE.md
│   ├── RESEARCH.md
│   ├── ARCHITECTURE.md
│   ├── SYSTEM_MODEL.md
│   ├── ROADMAP.md
│   ├── COHERENCE.md
│   ├── plans/
│   ├── results/
│   └── SUMMARY.md
├── quick/Q001-slug/
├── debug/{active,resolved}/
├── debug/KNOWLEDGE.md
├── archive/
└── .runtime/
```

`STATE.md` é somente um índice: trabalho ativo, unidade atual, status, bloqueios, próxima ação, ponteiros e digest vigente. Aprovação detalhada, histórico e evidências ficam nos documentos específicos. O estado é limitado a 64 KiB.

`.planning/` não pertence ao Bianchini Method. Ele não é lido, importado, convertido, copiado ou apagado.

## Planejamento global

```text
PDF de escopo → SCOPE.md selado
→ pesquisa
→ arquitetura global
→ SYSTEM_MODEL final
→ planos por fases e tarefas tipadas
→ roadmap completo derivado
→ validação estrutural
→ impact radius
→ revisão semântica conjunta
→ pacote pronto para aprovação
→ decisão técnica registrada no digest global
```

Cada plano declara `depends_on`, `provides`, `consumes`, ownership, interfaces, dados, migrações, efeitos, rollback, model delta, verificação e restrições futuras. Cada tarefa `Txx` declara resultado, requisitos cobertos, dependências, arquivos, ação, prova, done condition e `risk_seam`.

O CLI valida cobertura `SCOPE → fase → tarefa`, gera `ROADMAP.md` a partir dos planos e calcula ondas topológicas de fases e tarefas. O manifesto aprovado vincula todos os artefatos e o parecer semântico ao mesmo digest.

O método simula:

```text
S0 + delta(P01) = S1
S1 + delta(P02) = S2
...
Sn = SYSTEM_MODEL final
```

Um plano é bloqueado quando funciona isoladamente, mas quebra o modelo ou uma fase posterior.

### Coerência

Validação estrutural é determinística e independente de LLM. A revisão semântica analisa abstração especulativa, complexidade, responsabilidade, aderência à stack e conflitos interpretativos.

Um check estrutural limpo retorna `structurally_valid`. O check completo retorna `ready_for_approval`. Somente `coherence approve`, com o digest retornado e o responsável pela decisão, transforma o pacote em `approved`.

| Severidade | Regra |
|---|---|
| `ERROR` | bloqueia |
| `WARNING` | exige correção ou justificativa aprovada no digest |
| `INFO` | observação |

Mudanças recalculam o raio de impacto:

```text
contrato
→ consumidores diretos
→ consumidores transitivos
→ journeys
→ planos
→ gates a repetir
```

Antes da aprovação, a análise é apenas uma prévia e não grava `stale`. Depois da
aprovação, planos atingidos ficam `stale`, o pacote entra em
`approved_with_stale` e planos independentes continuam executáveis com o digest
da decisão original. Uma nova auditoria gera o próximo digest aprovado.

O primeiro quick ou debug de um projeto novo inicializa `.bianchini`
automaticamente. Se houver documentação anterior reconhecida, a execução bloqueia
com `MIGRATION_REQUIRED`; não existe fallback para `.superpowers` ou `docs/living`.

## Quick previsível

`/executar-direto` classifica:

```text
risk = scope + external_effect + migration + concurrency + money
```

Cada dimensão vale `0..2`:

- `0–2`: quick normal;
- `3–10`: quick protegido.

Sinais como múltiplos domínios, migração destrutiva, concorrência sem solução, ownership indefinido ou arquitetura nova reforçam guards e evidências, mas não trocam o fluxo escolhido.

Pagamento e webhook não escalam por palavra. Um fluxo coeso pode permanecer quick protegido quando documenta origem de verdade, idempotência, autenticidade, deduplicação, retry incerto, persistência, reconciliação, rollback e sandbox. Efeito financeiro/irreversível real exige checkpoint explícito.

Quicks ficam versionados em `.bianchini/quick/Qxxx-*` e atualizam a DocViva ao terminar.

Quando `/executar-direto` é invocado, score e risco nunca redirecionam para `/sdd-planning`. O conteúdo de `.bianchini/` continua servindo como documentação e rastreio da execução.

Quick normal e protegido podem usar subagentes em frentes independentes para reduzir tempo ou aumentar qualidade. O executor principal mantém ownership da integração, evidência e conclusão; o método não fixa modelo, quantidade ou paralelismo e não cria agentes por camada de teste.

## Debug persistente

```text
intake → reproduced → diagnosed → red → fixing → green
→ regression_checked → documented → resolved | blocked | escalated
```

O debug preserva hipóteses, contraprovas, causa, RED/GREEN, regressões e risco residual. Uma referência opcional `Dxxx → Cxxx/Pxx` só é aceita com evidência.

GREEN antes de RED e evidência anterior ao último patch são rejeitados. Casos resolvidos ficam em `.bianchini/debug/resolved/`; apenas padrões reutilizáveis entram em `KNOWLEDGE.md`.

## Migração única

Não existe adaptador permanente. Projetos anteriores terminam seu ciclo e usam:

```bash
skills/_shared/bin/bm migrate check --repo .
skills/_shared/bin/bm migrate apply --repo .
```

`check` é somente leitura. `apply` exige Git limpo e projeto concluído/`idle`, preserva histórico, usa checksums e rollback, e produz manifesto em `.bianchini/archive/import-AAAA-MM-DD/`.

## Política adaptativa

| Risco | Execução | Revisão | Testes |
|---|---|---|---|
| baixo | `grouped` | gate do plano | foco no seam |
| médio | `slice` | por slice | comportamento vertical |
| alto/crítico | `strict` | por tarefa | RED/GREEN + revisão independente |

As camadas são distribuídas por estágio:

```text
verification.fast
  → prova focal da unidade

verification.plan
  → suítes afetadas + regressão + E2E crítico + mutação seletiva

verification.release
  → comandos completos aprovados + contratos + regressão + build

homologar-sistema
  → operar o RC real e confirmar jornadas/visual
```

Regressão é transversal. Não existe tarefa ou agente por camada de teste, meta global de coverage ou mutation score.

## Skills

- `preparar-escopo`: converte um PDF textual, escaneado ou misto em `SCOPE.md` rastreável, fechado e pronto para o SDD.
- `design-projeto`: referência visual aprovada antes do planejamento quando necessária.
- `sdd-planning`: pesquisa, ProjectModel, roadmap, planos e coerência global.
- `executar-plano`: execução canônica com prova fresca, revisão vinculada e isolamento somente quando necessário.
- `executar-direto`: quick normal/protegido por score; invocação manual.
- `corrigir-bug`: debug persistente, causa raiz, RED/GREEN e regressão.
- `status-projeto`: leitura compacta do estado e próximo passo.
- `migrar-bianchini`: migração explícita e transacional para `.bianchini`; invocação manual.
- `homologar-sistema`: automação, operação real do RC e varredura visual.
- `auditar-arquitetura`: auditoria manual report-only.
- `update-bm`: atualização manual com backup e rollback.

## CLI

```text
model init|validate
scope seal|verify
roadmap sync
coherence check|approve
impact analyze --plan Pxx [--changed-contract ID]
plan complete --change Cxxx --plan Pxx --actual-delta <json>
plan reopen --change Cxxx --plan Pxx [--task Txx] --reason <motivo>
verify task|plan|release|review|status
direct classify|start|status|checkpoint|finish
debug start|list|status|resume|checkpoint|finish
migrate check|apply
workspace create|check|locate|resume|finish
cycle-close --change Cxxx
policy  proof-map  mutation-evidence  telemetry  status  update-bm
```

Os comandos `task-brief`, `report`, `review-package` e `checkpoint` são compatibilidade legada; o fluxo atual usa `context pack` e `verify`.

Erros públicos do fluxo atual incluem `MODEL_MISMATCH`, `COHERENCE_ERROR`,
`WARNING_UNRESOLVED`, `IMPACT_STALE`, `MISSING_PROVIDER`,
`OWNERSHIP_CONFLICT`, `MIGRATION_ORDER_INVALID`, `MISSING_GUARD`,
`STALE_EVIDENCE`, `EXTERNAL_AUTHORITY_REQUIRED`, `DOCVIVA_INCOMPLETE` e
`MIGRATION_REQUIRED`.

Exemplos:

```bash
skills/_shared/bin/bm model init --repo .
skills/_shared/bin/bm model init --repo . --change checkout
skills/_shared/bin/bm scope seal --repo . --change C001-checkout --source escopo.pdf --draft /tmp/scope-draft.md --pages 12 --extraction native
skills/_shared/bin/bm scope verify --repo . --change C001-checkout --source escopo.pdf
skills/_shared/bin/bm roadmap sync --repo . --change C001
skills/_shared/bin/bm model validate --repo . --change C001
skills/_shared/bin/bm coherence check --repo . --change C001 --structural-only
skills/_shared/bin/bm coherence check --repo . --change C001 --semantic-report semantic-review.json
skills/_shared/bin/bm coherence approve --repo . --change C001 --digest <digest> --decided-by "agent:planner"
skills/_shared/bin/bm impact analyze --repo . --change C001 --plan P02
skills/_shared/bin/bm verify task --repo . --change C001 --plan P01 --task T01 --context-pack .bianchini/.runtime/context/C001-P01-T01.json
skills/_shared/bin/bm verify review --repo . --change C001 --scope task --plan P01 --task T01 --reviewer reviewer --verdict approved --proof <proof-id>
skills/_shared/bin/bm plan complete --repo . --change C001 --plan P01 --task T01 --context-pack .bianchini/.runtime/context/C001-P01-T01.json --result "<resultado>" --proof <proof-id> --review <review-id>
skills/_shared/bin/bm verify release --repo . --change C001 --artifact-kind file --build dist/app --checksum <sha256> --delivery ready
skills/_shared/bin/bm cycle-close --repo . --change C001
```

## Instalação local

Baixe o archive da [release atual](https://github.com/felipebianchini2006/bianchini-method/releases/latest) correspondente a `darwin-arm64`, `darwin-amd64`, `linux-arm64`, `linux-amd64` ou `windows-amd64`. Verifique o arquivo com `SHA256SUMS`, extraia e copie o diretório `skills` inteiro:

```bash
shasum -a 256 -c SHA256SUMS
cp -R bianchini-method_<versão>_<plataforma>/skills/. ~/.codex/skills/
# Claude Code: troque ~/.codex por ~/.claude
```

O binário fica em `_shared/bin/bm` no Unix ou `_shared/bin/bm.exe` no Windows. A instalação é inválida se ele estiver ausente; as skills não usam Python como fallback.

Atualização é sempre explícita:

```bash
~/.codex/skills/_shared/bin/bm update-bm --check
~/.codex/skills/_shared/bin/bm update-bm
```

A instalação `0.4.0` aceita uma única mudança oficial da linhagem numérica anterior; depois volta à comparação semântica normal. O updater valida identidade, manifesto, `SHA256SUMS`, tamanho e digest do archive antes da troca transacional com lock, journal e backup.

Os antigos comandos `route`, `legacy-transition` e `repo-hygiene` não fazem parte da interface atual. Artefatos anteriores reconhecidos entram somente por `/migrar-bianchini` ou `bm migrate`.

## Uso

```text
/preparar-escopo escopo.pdf
/design-projeto
/sdd-planning
/executar-direto
/executar-plano all
/status-projeto
/corrigir-bug <sintoma>
/homologar-sistema
/auditar-arquitetura
/migrar-bianchini
/update-bm
```

## Validação do pacote

```bash
python3 scripts/run_test_shards.py
go test ./...
go test -race ./...
go vet ./...
go build -trimpath -o bin/bm ./cmd/bm
python3 scripts/run_cli_contract_fixtures.py --engine go --binary ./bin/bm
```

O backend oficial é Go. `python3 scripts/bm.py` executa somente `bin/bm` e falha com `BM_INSTALLATION_INVALID` quando o binário não existe; não há fallback. O legado permanece acessível apenas pelo nome explícito `python3 scripts/bm_python_oracle.py` durante a janela de paridade. Testes cobrem intake de PDF, selo e rastreabilidade do `SCOPE.md`, fases/tarefas tipadas, roadmap derivado, manifesto aprovado, workspace, ProjectModel, coerência determinística, impacto seletivo, quick, debug, migração, aliases de caminho, transações e preservação de `.planning/`.
