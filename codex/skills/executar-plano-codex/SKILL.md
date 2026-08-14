---
name: executar-plano-codex
description: Use somente com invocação explícita de $executar-plano-codex para executar planos aprovados com convergência limitada do Codex.
disable-model-invocation: true
---

# Executar Plano — Codex

**Anuncie:** "Executando <planos> pelo overlay Codex no modo <v1 legado|grouped|slice|strict>."

Argumentos: `all`, `N`, `N-M`. Sem argumento, mostrar `status-projeto`; executar `all` somente quando o pedido atual já for explícito.

## Executor reutilizado

Leia integralmente o executor base em [`../../../skills/executar-plano/SKILL.md`](../../../skills/executar-plano/SKILL.md). Em uma instalação Codex, use o caminho irmão `../executar-plano/SKILL.md`. Reutilize sem alteração suas regras de:

- preflight, rota v1/v2 e aprovação;
- worktree, branch e workspace check;
- implementação grouped, slice ou strict;
- commits atômicos e checkpoints;
- gates do plano;
- release, homologação e entrega.

Também leia [`references/CODEX_CONVERGENCE.md`](references/CODEX_CONVERGENCE.md) e [`references/plan-reviewer-codex.md`](references/plan-reviewer-codex.md). As regras abaixo substituem somente as seções do executor base sobre revisão, fix loop, breaker, redesign e paradas. Nenhuma outra regra do executor base é substituída.

De `bm.py policy`, manter modo, cadência e garantia; ignorar somente `max_fix_rounds` e `breaker`. Quando `corrigir-bug` ou `homologar-sistema` forem usados dentro deste overlay, seus loops e vereditos de bloqueio ficam subordinados a este guard. A revisão final do release também usa o revisor Codex e a mesma política de convergência.

Não modificar `PROJECT_STATE`, schema ou `bm.py` para representar a convergência Codex. Usar um sidecar JSON por unidade:

```text
artifacts/bianchini/<planning_version>/codex/convergence/<plan_id>/<unit_id>.json
```

Resolver o caminho de `scripts/review_guard.py` dentro desta skill e operar o sidecar somente com esse script. Ledger e checkpoint podem registrar o caminho do sidecar, sem copiar seus campos para o estado principal.

## Revisão substituta

Antes da primeira revisão da unidade, gerar o `review-package` base normalmente. Executar o revisor com [`references/plan-reviewer-codex.md`](references/plan-reviewer-codex.md), salvar os findings em JSON e congelar a revisão:

```bash
python3 <review_guard.py> freeze \
  --root <workspace> \
  --planning-version <planning_version> \
  --plan <plan_id> \
  --unit <unit_id> \
  --seam <seam> \
  --review-head <head_da_primeira_revisão> \
  --findings <findings.json>
```

Um blocker só é aceito quando contém requisito aprovado identificável, reprodução determinística, impacto material e cenário alcançável. Findings `minor` e `note` são registrados como hardening adiado. Findings `critical` ou `important` sem contrato completo invalidam a revisão; não viram blocker por opinião.

Revisões seguintes usam somente blockers congelados ainda abertos e regressões causadas pelo delta desde a rodada anterior. Passar `--delta-base` igual ao `last_review_head` do sidecar e `--delta-head` igual ao head revisado; o guard rejeita cadeia descontínua. Não reavaliar código inalterado, não ampliar escopo e não reabrir unidade ou tarefa concluída.

## Fix loop, redesign e conclusão

Cada unidade aceita no máximo dois fix rounds. Uma rodada pode cobrir vários blockers; repetir `--blocker` na mesma chamada. Registrar a rodada antes do patch:

```bash
python3 <review_guard.py> fix --sidecar <sidecar.json> --blocker <id> --summary "<causa mínima>"
```

Cada seam aceita no máximo um redesign. Redesign só ocorre após evidência estrutural concreta e é registrado antes da mudança:

```bash
python3 <review_guard.py> redesign --sidecar <sidecar.json> --seam <seam> --summary "<motivo estrutural>"
```

Resolver blockers com evidência reproduzível. Depois, executar gates base aplicáveis e concluir o sidecar. Findings não críticos restantes permanecem em `deferred_hardening` e não impedem conclusão.

```bash
python3 <review_guard.py> resolve --sidecar <sidecar.json> --blocker <id> --evidence "<teste ou prova>"
python3 <review_guard.py> complete --sidecar <sidecar.json>
```

Sidecar `completed` é terminal. Nunca reabrir a tarefa. Ao atingir duas rodadas com blocker aberto, o guard retorna `redesign_required` enquanto o seam ainda aceitar redesign. Depois do redesign, validar e resolver diretamente. Se a prova continuar falhando, registrar `real_impossibility` somente quando for factual; sem essa prova, manter o bloqueio local e continuar unidades independentes. Não herdar limites Lean, Standard ou Full do executor base.

## Decisões e paradas substitutas

Decisões técnicas internas são automáticas. Escolher a opção reversível de menor risco, registrar a decisão no sidecar e continuar.

Bloqueio local mantém trabalho independente em andamento. Registrar `local_block`; nunca propagar o bloqueio para outra unidade sem dependência comprovada.

Somente estas categorias permitem parada:

- `essential_external_credential`;
- `destructive_action`;
- `new_cost`;
- `real_impossibility`.

Estado inválido, snapshot divergente, worktree insegura, gate falho e defeito bloqueante continuam sendo corrigidos ou isolados pelas regras base; só viram parada quando provarem uma das quatro categorias acima. Superpowers ausente em rota v1 é `real_impossibility` somente após confirmar que o executor legado indispensável não está disponível.

Registrar decisões com:

```bash
python3 <review_guard.py> decision --sidecar <sidecar.json> --kind <categoria> --summary "<fato>"
```

Nenhuma ação, saída ou estado pode resultar em `ask_user`. Quando uma das quatro paradas for comprovada, registrar `stop`; fora delas, continuar automaticamente.

## Saída

Além da saída exigida pelo executor base, informar sidecars, blockers congelados resolvidos, fix rounds, redesigns, hardening adiado e eventual categoria de parada. Usar a sintaxe `$executar-plano-codex all` na orientação de uso.
