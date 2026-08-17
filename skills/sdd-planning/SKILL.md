---
name: sdd-planning
description: Use somente com invocação explícita de /sdd-planning, ou para continuar um projeto cujo PROJECT_STATE declare method_version 2. Em estado v1, apenas roteia ao legado; não disputa ativação com skills gerais de planejamento.
---

# SDD Planning

**Anuncie:** "Planejando com Bianchini Method <v1 legado|v2 standalone>."

Leia [`../_shared/METHOD_CONTRACT.md`](../_shared/METHOD_CONTRACT.md), [`../_shared/STATE_TEMPLATE.md`](../_shared/STATE_TEMPLATE.md) e [`../_shared/ADAPTIVE_GATES.md`](../_shared/ADAPTIVE_GATES.md). Resolva [`../_shared/scripts/bm.py`](../_shared/scripts/bm.py) uma vez.

## 1. Rotear e preservar compatibilidade

1. Ler regras do repositório e `PROJECT_STATE.md`, quando existir.
2. Executar `bm.py route` com estado; sem estado, usar `--new-project`.
3. V1 exige Superpowers e permanece integralmente no legado. Sem ele, `BLOQUEADO`.
4. V2 `planning_status: idle` inicia o próximo ciclo standalone. Não chamar `writing-plans`, brainstorming ou outro fluxo legado.
5. Migração v1 somente com autorização explícita; preservar `docs/superpowers/` como histórico.
6. Novo ciclo usa `planning.quality_version: 2`. Ciclo v2 antigo já aprovado continua no contrato em que nasceu; não migrar durante execução.

Executar `bm.py repo-hygiene check`. Com migração autorizada, usar `repo-hygiene migrate`. Esta skill somente planeja; não cria código de produção.

## 2. Criar a raiz da mudança

Usar:

```text
docs/bianchini/current/specs/          # comportamento atual aceito
docs/bianchini/changes/<version>/      # mudança em planejamento
docs/bianchini/archive/<version>/      # ciclo encerrado
```

No primeiro ciclo, usar `v1`. Materializar o escopo em:

```text
docs/bianchini/changes/<version>/inputs/APPROVED_SCOPE.md
```

Preservar 100% dos resultados, invariantes e restrições aprovados. Planos nunca dependem de `inputs/`, `docs/superpowers/` ou “PLANO Task N” durante execução.

## 3. Resolver design antes do plano

Classificar a mudança visual:

- sem interface: `design_required: false`;
- pequena mudança que preserva tokens, componentes e interação existentes: `design_required: false` e seguir o padrão do repositório;
- delta visual com decisão nova, interface nova, redesign ou fluxo visual material: exigir `/design-projeto` antes de continuar.

Somente usar arquivo sob `docs/design` quando existir `DESIGN_MANIFEST.json` com `status: approved`, hashes válidos e o mesmo escopo:

```bash
python3 <bm.py> design-audit verify --root <repo> --scope <scope> --manifest <manifest>
```

Arquivos soltos, screenshots antigos e protótipos sem manifesto são ignorados. Design existente usa [`references/design-import.md`](references/design-import.md).

## 4. Ler e pesquisar uma vez

Ordem: decisão recente do responsável, escopo, specs atuais, design válido, documentação, código, testes e histórico.

Cartografia deixa de ser opcional quando o brownfield tiver múltiplas aplicações/linguagens, legado relevante ou mais de um contrato afetado. Nesses casos, usar [`../_shared/agents/repo-cartographer.md`](../_shared/agents/repo-cartographer.md). Não usar em projeto novo ou pequeno. Salvar em `.superpowers/bianchini/cartography/<hash-do-HEAD>-<digest-do-escopo>.md`; `HEAD` diferente invalida o cache e escopo diferente gera outro arquivo. Projeto novo ou leitura localizada não recebe cartografia artificial.

Ler [`references/stack-research.md`](references/stack-research.md) e criar `STACK_RESEARCH.md` com o menor modo suficiente:

- `repo_only`: stack local conhecida;
- `targeted_web`: API, biblioteca, pagamento, autenticação, mobile, infraestrutura ou versão sensível;
- `full`: auditoria/regulação ou várias decisões críticas.

Modos web usam fontes primárias oficiais. Pesquisa não autoriza upgrade, refatoração ou ampliação de escopo.

## 5. Gate de prontidão

Antes da spec e dos planos, criar:

```text
docs/bianchini/changes/<version>/READINESS.md
docs/bianchini/changes/<version>/USER_ACTIONS.md
```

`READINESS.md` contém um objeto JSON cercado por bloco `json` com:

```text
D-001  decisão travada
A-001  suposição confirmada ou limitada
P-001  pitfall com prevenção, recuperação e verificação
U-001  ação externa, plano limite e fallback
S-001  spike encerrado com evidência
DS-001 superfície visual ligada ao manifesto
SD-001 spec de domínio que será sincronizada
```

Também registrar `scope_digest`, `repository_revision` igual ao `HEAD` atual (`new-project` sem repositório), `design_required` e mapa de impacto: aplicações, módulos, contratos, dados e plataformas. Commit novo antes da aprovação invalida o readiness.

Regras:

- suposição alta/crítica exige evidência e fallback quando limitada;
- pitfall alto/crítico exige prevenção, recuperação e verificação;
- spike pendente ou falho bloqueia;
- ação externa deve dizer quando é necessária e se existe fallback;
- cada item declara `destinations`; o ID deve aparecer nesses arquivos;
- decisões e superfícies visuais aparecem na spec e em ao menos um plano;
- `USER_ACTIONS.md` é uma visão humana das entradas `U-*`, não nova fonte de verdade.

Não criar uma tarefa por pitfall. O pitfall restringe a entrega e seus gates.

## 6. Criar spec da mudança e próximas specs atuais

Criar uma spec central autocontida:

```text
docs/bianchini/changes/<version>/specs/<sistema>-change.md
```

Incluir objetivo, limites, arquitetura, contratos públicos, entidades, estados, invariantes, permissões, jornadas, segurança, dados, concorrência, integrações, plataformas, seams e referências `D/A/P/U/DS/SD`.

Para cada domínio alterado, criar o contrato completo esperado após a entrega:

```text
docs/bianchini/changes/<version>/spec-deltas/<dominio>.md
```

Cada `SD-*` aponta `source` para esse arquivo e `target` para `docs/bianchini/current/specs/<dominio>.md`. Se o target já existir, incluí-lo no pacote para congelar a base. Não editar `current/specs` durante planejamento ou execução.

## 7. Criar planos por entregas reais

Caminho:

```text
docs/bianchini/changes/<version>/plans/P<NN>-<entrega>.md
```

Não há mínimo ou alvo de tarefas. Separar somente entregas rejeitáveis ou verificáveis de forma independente.

Cada unidade declara:

```markdown
### Tarefa N — <resultado observável>

**Execution:** grouped | slice | strict
**Review:** plan_gate | per_slice | per_task
**Change:** <categoria factual para bm.py policy>
**Readiness refs:** D-001, P-001, U-001, SD-001
**Test seams:** <interfaces públicas>
**Spec refs:** <seções exatas>
**Files:** <caminhos>
**Contract:** <entradas, saídas e invariantes>
**Verification:** <comando e resultado>
**Done when:** <evidência objetiva>
```

Política:

- `grouped`: mudanças baixas no mesmo seam, uma revisão no gate;
- `slice`: entrega vertical e revisão por slice;
- `strict`: unidade crítica, RED/GREEN e revisão independente;
- setup/config/docs entram na primeira entrega que os usa;
- não criar tarefa por camada de teste, arquivo, ferramenta, decisão ou documento;
- não usar `TBD`, “tratar erros” ou abstração futura.

## 8. Definir garantia e verificação

Escolher `lean`, `standard` ou `full` pelo maior risco/capacidade. Unidade crítica isolada usa `strict` sem promover todo o projeto a Full. Auditoria arquitetural é manual e report-only; não a executar automaticamente.

Executar `bm.py policy` para cada plano. Distribuir testes:

- `verification.fast`: unitários, integração/contrato e regressão focados;
- `verification.plan`: suítes afetadas, regressão do plano, E2E crítico e mutação seletiva;
- `verification.release`: suítes completas configuradas, contratos, E2E crítico, regressão, mutação exigida e build.

Não usar cobertura ou mutation score global. Gate indispensável indisponível é bloqueio.

## 9. Checker semântico com uma correção máxima

Criar `PLANNING_REVIEW.md` com objeto JSON:

```json
{"verdict":"passed|changes_requested|blocked","findings":[]}
```

Cada finding possui `id`, `severity`, `summary` e `evidence`. O CLI liga a passagem aos digests do pacote e do próprio relatório; uma segunda passagem exige mudança factual e um relatório novo.

Fluxo fechado:

```text
checker 1
  -> passed: congelar
  -> changes_requested: uma correção
  -> blocked: parar
checker 2
  -> passed ou blocked
```

Registrar pelo CLI:

```bash
python3 <bm.py> planning-check record --state <state> --root <repo> --report <review>
```

Terceira revisão é proibida. Não usar o checker para redesenhar por preferência, reabrir decisão aprovada ou criar trabalho futuro.

## 10. Estado, auditoria e aprovação única

Criar o estado conforme [`../_shared/STATE_TEMPLATE.md`](../_shared/STATE_TEMPLATE.md), com:

- `quality_version: 2`;
- `readiness`, `user_actions`, `checker`, `change_root`, `current_specs` e design válido quando aplicável;
- `complexity_review` proporcional;
- pacote contendo escopo, pesquisa, readiness, ações, spec, spec-deltas quando aplicáveis, planos, revisão, specs atuais existentes e todos os arquivos de design.

Nunca usar `deferred_scope` para caber no orçamento. `split` exige `scope_split_approved: true`, responsável e horário.

Executar:

```bash
python3 <bm.py> validate-state <state>
python3 <bm.py> planning-audit <state> --root <repo> --strict
python3 <bm.py> snapshot create <state> --root <repo>
python3 <bm.py> snapshot verify <state> --root <repo>
```

Depois pedir uma única aprovação do digest e de todos os planos. Não aprovar em nome do responsável.

Na aprovação, atualizar estado, verificar novamente, adicionar somente pacote/estado/manifesto e criar commit local atômico. Confirmar `git status --porcelain` vazio. Não fazer push nem iniciar implementação.

## Saída

Informar rota, versão da mudança, design, readiness, suposições/pitfalls, ações externas, specs atuais/deltas, perfil, planos, duas passagens máximas do checker, digest e bloqueios.
