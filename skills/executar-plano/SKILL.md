---
name: executar-plano
description: Use somente com invocação explícita de /executar-plano ou quando PROJECT_STATE declarar method_version 2 e houver plano aprovado. Em estado v1, apenas roteia ao executor legado e não concorre com executores gerais.
---

# Executar Plano

**Anuncie:** "Executando <planos> no modo <v1 legado|grouped|slice|strict>."

Argumentos: `all`, `N`, `N-M`. Sem argumento, mostrar `status-projeto`; executar `all` somente quando o pedido atual já for explícito.

Leia [`../_shared/METHOD_CONTRACT.md`](../_shared/METHOD_CONTRACT.md) e resolva [`../_shared/scripts/bm.py`](../_shared/scripts/bm.py).

## 1. Preflight e rota

1. Executar `bm.py route`.
2. V1: exigir Superpowers e usar integralmente o executor legado. Depois do encerramento real, executar a transição da seção 9.
3. V2: executar `validate-state`, `snapshot verify` e `repo-hygiene check`.
4. Aprovação pending só muda por aprovação explícita do digest atual; o comando de execução não é aprovação.
5. Confirmar planos em `approved_plans`, checker `passed`, dependências concluídas e design válido quando presente.
6. Exigir `git status --porcelain` vazio. Mudança preexistente bloqueia a criação da worktree.

Snapshot divergente invalida aprovação. Ciclo `quality_version: 1` já aprovado continua no contrato antigo; não migrar durante execução.

## 2. Workspace isolado obrigatório

Criar ou retomar um workspace por plano:

```bash
<bm.py> workspace create --repo <repo> --planning-version v1 --plan P01 --state <PROJECT_STATE.md>
<bm.py> workspace resume --repo <repo> --planning-version v1 --plan P01
<bm.py> workspace check --repo <workspace>
```

Usar a versão real do estado, não o valor fixo do exemplo. Branch `bm/<planning_version>-<plan_id>`. Main, master, detached HEAD e worktree primária são proibidos. Não existe fallback para branch atual.

Aquecer dependências uma vez, respeitando `mise` ou configuração equivalente.

## 3. Retomada e contexto mínimo

No ledger registrar digest aprovado, base revision, workspace, branch, modo, perfil, readiness refs e máximo de fix rounds.

Gerar pelo CLI:

- `task-brief` por grupo, slice ou tarefa;
- `report` persistente do implementador;
- `review-package` determinístico;
- `checkpoint` após unidade, falha, bloqueio e antes de encerrar contexto.

Retomada começa com `workspace resume`, checkpoint e final do ledger. Não reler planos concluídos nem reconstruir estado pela conversa.

## 4. Autonomia e plano congelado

O plano aprovado é imutável. Antes de pedir decisão, seguir:

```text
decisão aprovada
-> padrão do repositório
-> stack/dependência existente
-> documentação oficial
-> opção reversível de menor risco
```

Registrar a decisão e continuar.

Quando surgir divergência, executar `bm.py change-policy` com os flags factuais:

- `implementation_detail`: decidir e continuar;
- `bounded_amendment`: registrar no ledger e continuar sem editar plano, spec ou snapshot;
- `material_change` com `plan_invalidating: true`: invalidar o pacote e replanejar somente a área afetada;
- `material_change` somente por custo ou ação irreversível: pausar para autorização e continuar no mesmo plano se o contrato permanecer igual.

Arquivo diferente, comando equivalente, ordem interna, nome ou implementação mais simples não autorizam redesign. `bounded_amendment` não abre tarefa, revisão, fix loop ou subagente.

Parar somente por credencial indispensável sem fallback, novo custo, ação destrutiva/irreversível, mudança material de escopo/contrato/design ou impossibilidade real comprovada. Ação `U-*` ainda não necessária não interrompe trabalho independente; usar o fallback aprovado até `needed_by`.

## 5. Executar pela política

Antes de cada unidade, executar `bm.py policy` com perfil, risco e `Change` do brief. Divergência pode aumentar garantia; redução exige novo pacote.

Quando o host suportar subagentes, usar [`../_shared/agents/implementation-worker.md`](../_shared/agents/implementation-worker.md). Passar apenas contrato, brief, relatório e contexto necessário. Sem subagentes, cumprir inline.

### Grouped

- Agrupar unidades baixas do mesmo seam e ownership compatível.
- Um brief, auto-revisão e revisão no gate do plano.
- `verification.fast` focada.
- Commit atômico por grupo.

### Slice

- Cada slice entrega comportamento vertical.
- Teste comportamental; RED/GREEN somente quando prova regressão real.
- Revisão por slice.
- Commit atômico por slice.

### Strict

- Uma unidade crítica por execução.
- RED pela interface pública, GREEN mínimo e vizinhos de risco.
- Revisão independente quando disponível.
- Commit atômico por tarefa.

Nenhum modo implementa necessidade futura. Testes observam seams públicos.

## 6. Profundidade de testes

Na unidade, executar somente `verification.fast`:

- unitário focado quando lógica mudou;
- integração/contrato focada quando fronteira mudou;
- regressão diretamente relacionada;
- E2E focado apenas quando for a menor prova pública.

Na execução da unidade, não executar E2E completo ou mutação por unidade. Não criar tarefa/subagente por camada de teste.

No gate do plano, executar suítes afetadas, regressão do plano, E2E crítico e mutação seletiva exigida. No release, executar os comandos completos aprovados. Não perseguir cobertura ou mutation score global.

## 7. Revisão e convergência

Usar [`../_shared/agents/plan-reviewer.md`](../_shared/agents/plan-reviewer.md) na cadência do modo, nunca por microtarefa em `grouped`. Entregar apenas contrato, brief, relatório, review package e o caminho do arquivo de saída da revisão.

Em risco alto ou crítico sensível, usar passagem somente leitura por [`../_shared/agents/security-reviewer.md`](../_shared/agents/security-reviewer.md), incluindo o caminho do arquivo de saída do parecer. Não executá-la em tarefa comum.

Revisar Spec e Qualidade. `critical`/`important` abre fix round. Em cada rodada:

1. registrar `risk_seam`;
2. corrigir a causa mínima;
3. executar RED/GREEN e regressão focal;
4. revisar somente o delta;
5. recalcular policy com `--seam-round`, `--consecutive-seam-findings` e `--structural-finding` aplicáveis.

Fix round é hipótese, não entrega. Gates completos ficam no fechamento. Com breaker ou hipótese estrutural invalidada, parar patches e redesenhar o seam técnico, não o plano comercial inteiro. Nunca exceder o limite.

Revisor não pode transformar `implementation_detail` ou `bounded_amendment` em redesign por preferência.

## 8. Gate, release e homologação

Ao fechar um plano:

1. executar `verification.plan` no HEAD final;
2. registrar comandos, cwd, horário, resumo e exit code;
3. usar `corrigir-bug` para falha de produto;
4. repetir somente gates afetados e dependentes;
5. gerar checkpoint;
6. marcar `completed` somente com gates obrigatórios `passed`.

`not_run`, flake aberto ou dependência indispensável mantém `blocked`.

Quando o último plano concluir:

1. gerar RC com `id`, `revision`, `build`, `checksum`;
2. definir `candidate`;
3. executar `homologar-sistema`, começando por `verification.release`;
4. com homologação aceita, revisar o release completo uma vez;
5. criar `artifacts/delivery/DELIVERY.md` e definir `ready`.

Se o host não invocar skills, ler e cumprir `corrigir-bug` ou `homologar-sistema` diretamente. Manual/PDF somente quando contratado.

## 9. Encerrar ciclo

Após release `ready`, homologação aceita, revisão final aprovada, entrega pronta, commit final e árvore limpa:

```bash
<bm.py> cycle-close --state <PROJECT_STATE.md> --root <repo>
```

Confirmar:

- `spec-deltas` sincronizados em `docs/bianchini/current/specs/`;
- mudança arquivada em `docs/bianchini/archive/<version>/`;
- estado `idle` com versão seguinte;
- mudanças preparadas sem arquivos alheios.

Criar commit local atômico `chore: close <version> and sync current specs`. Não fazer push, merge, deploy ou publicação por inferência.

### Transição legado

Quando fase v1 concluir gates, entrega e commit, executar:

```bash
<bm.py> legacy-transition --repo <repo> --state <PROJECT_STATE.md> --completed
```

Após conclusão comprovada, não pedir nova aprovação de migração. Confirmar archive legado, estado v2 `idle`, higiene e árvore limpa. `--completed` exige marcador objetivo ou `--completion-proof` commitado.

## Saída

Informar rota, planos/modos, workspaces, decisões autônomas, mudanças classificadas, gates, homologação, commits, ledgers/checkpoints, sync/archive do ciclo, manual e bloqueios. Não perguntar por decisão técnica reversível já coberta pelo envelope.
