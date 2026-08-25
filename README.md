# Bianchini Method 0.4

Método spec-driven para planejar e executar mudanças com visão do sistema completo, coerência entre fases, documentação viva e verificação proporcional ao risco.

O salto do `0.4` é tratar o planejamento como um grafo de contratos:

```text
sistema atual
→ sistema após cada fase
→ sistema final esperado
```

## Arquitetura

```text
Bianchini Method
├── MethodWorkspace
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

## Workspace

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
pesquisa
→ arquitetura global
→ SYSTEM_MODEL final
→ roadmap completo
→ planos por contratos
→ validação estrutural
→ impact radius
→ revisão semântica conjunta
→ pacote pronto para aprovação
→ checkpoint humano do digest global
```

Cada plano declara `depends_on`, `provides`, `consumes`, ownership, interfaces, dados, migrações, efeitos, rollback, model delta, verificação e restrições futuras.

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
humano original. Uma nova auditoria gera o próximo digest aprovado.

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
- `3–6`: quick protegido;
- `7–10`: planejamento.

Overrides como múltiplos domínios, migração destrutiva, concorrência sem solução, ownership indefinido ou arquitetura nova sempre escalam.

Pagamento e webhook não escalam por palavra. Um fluxo coeso pode permanecer quick protegido quando documenta origem de verdade, idempotência, autenticidade, deduplicação, retry incerto, persistência, reconciliação, rollback e sandbox. Efeito financeiro/irreversível real exige checkpoint explícito.

Quicks ficam versionados em `.bianchini/quick/Qxxx-*` e atualizam a DocViva ao terminar.

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
python3 skills/_shared/scripts/bm.py migrate check --repo .
python3 skills/_shared/scripts/bm.py migrate apply --repo .
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

- `design-projeto`: referência visual aprovada antes do planejamento quando necessária.
- `sdd-planning`: pesquisa, ProjectModel, roadmap, planos e coerência global.
- `executar-plano`: execução isolada com verificação de contratos e impacto.
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
coherence check|approve
impact analyze --plan Pxx [--changed-contract ID]
plan complete --change Cxxx --plan Pxx --actual-delta <json>
direct classify|start|status|checkpoint|finish
debug start|list|status|resume|checkpoint|finish
migrate check|apply
workspace create|check|locate|resume
cycle-close --change Cxxx
task-brief  report  review-package  checkpoint
policy  proof-map  mutation-evidence  telemetry  status  update-bm
```

Erros públicos do fluxo 0.4 incluem `MODEL_MISMATCH`, `COHERENCE_ERROR`,
`WARNING_UNRESOLVED`, `IMPACT_STALE`, `MISSING_PROVIDER`,
`OWNERSHIP_CONFLICT`, `MIGRATION_ORDER_INVALID`, `MISSING_GUARD`,
`STALE_EVIDENCE`, `EXTERNAL_AUTHORITY_REQUIRED`, `DOCVIVA_INCOMPLETE` e
`MIGRATION_REQUIRED`.

Exemplos:

```bash
python3 skills/_shared/scripts/bm.py model init --repo .
python3 skills/_shared/scripts/bm.py model init --repo . --change checkout
python3 skills/_shared/scripts/bm.py model validate --repo . --change C001
python3 skills/_shared/scripts/bm.py coherence check --repo . --change C001 --structural-only
python3 skills/_shared/scripts/bm.py coherence check --repo . --change C001 --semantic-report semantic-review.json
python3 skills/_shared/scripts/bm.py coherence approve --repo . --change C001 --digest <digest> --approved-by "<responsável>"
python3 skills/_shared/scripts/bm.py impact analyze --repo . --change C001 --plan P02
python3 skills/_shared/scripts/bm.py workspace create --repo . --change C001 --plan P01
python3 skills/_shared/scripts/bm.py plan complete --repo . --change C001 --plan P01 --actual-delta actual-delta.json --result "<resultado>" --verification "<evidência>"
python3 skills/_shared/scripts/bm.py cycle-close --repo . --change C001
```

## Instalação local

Copie o diretório `skills` inteiro:

```bash
cp -R skills/. ~/.codex/skills/
# Claude Code: troque ~/.codex por ~/.claude
```

Atualização é sempre explícita:

```bash
python3 ~/.codex/skills/_shared/scripts/bm.py update-bm --check
python3 ~/.codex/skills/_shared/scripts/bm.py update-bm
```

A instalação `0.4.0` aceita uma única mudança oficial da linhagem numérica anterior; depois volta à comparação semântica normal.

Os antigos comandos `route`, `legacy-transition` e `repo-hygiene` não fazem parte da interface `0.4`. Artefatos anteriores reconhecidos entram somente por `/migrar-bianchini` ou `bm.py migrate`.

## Uso

```text
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
python3 scripts/bm.py --help
```

O CLI usa biblioteca padrão Python. Testes cobrem workspace, ProjectModel, coerência determinística, impacto seletivo, quick, debug, migração, aliases de caminho, transações e preservação de `.planning/`.
