---
name: executar-plano-codex
description: Use somente com invocação explícita de $executar-plano-codex para executar planos aprovados com convergência limitada do Codex.
disable-model-invocation: true
---

# Executar Plano — Codex

**Anuncie:** "Executando <planos> pelo overlay Codex no modo <v1 legado|grouped|slice|strict>."

Argumentos: `all`, `N`, `N-M`. Sem argumento, mostrar o status do projeto. Executar `all` somente quando o pedido atual já for explícito.

## Contratos carregados

Leia integralmente, nesta ordem, somente:

1. [`references/EXECUTION_CORE_CODEX.md`](references/EXECUTION_CORE_CODEX.md);
2. [`references/CODEX_CONVERGENCE.md`](references/CODEX_CONVERGENCE.md);
3. [`references/plan-reviewer-codex.md`](references/plan-reviewer-codex.md).

Não carregue qualquer outro contrato. `EXECUTION_CORE_CODEX.md` contém somente núcleo de execução reutilizado. `CODEX_CONVERGENCE.md` é autoridade exclusiva para revisão, fix loop, breaker, redesign e regras de parada no Codex.

Não modificar `PROJECT_STATE`, schemas do método base ou `bm.py` para representar convergência. Usar um sidecar JSON por unidade:

```text
artifacts/bianchini/<planning_version>/codex/convergence/<plan_id>/<unit_id>.json
```

Resolver `scripts/review_guard.py` dentro desta skill. Operar o sidecar somente pelo guard. Ledger e checkpoint podem registrar o caminho do sidecar, sem copiar seus campos para estado principal.

## Fluxo

1. Cumprir preflight, rota e aprovação definidos no núcleo.
2. Manter o plano congelado, classificar divergências com `bm.py change-policy`, implementar cada unidade e criar commit atômico.
3. Executar evidências pelo comando `proof`; reviewers referenciam somente `proof_id`. Na primeira revisão, congelar no máximo três blockers consolidados por causa raiz e declarar gates pelo comando `freeze`, usando como `unit_identity` o SHA-256 da unidade emitido por `task-brief`.
4. Após qualquer implementação subsequente, fix ou redesign, usar `submit-delta`. Revisão seguinte só ocorre em `awaiting_review` e cobre blockers congelados abertos e regressões comprovadas do delta.
5. Seguir `next_action` determinístico do guard. Nunca inventar uma transição.
6. Registrar gates obrigatórios com proof do `HEAD` atual. Concluir somente sem blocker aberto e com todos os gates obrigatórios aprovados.
7. Continuar unidades independentes quando uma unidade ficar `parked` ou tiver bloqueio local; nunca encerrar enquanto houver trabalho executável.
8. Cumprir release, homologação, entrega e `cycle-close` definidos no núcleo.

Decisões técnicas internas são automáticas. Nenhuma ação, saída ou estado pode produzir `ask_user`. Somente as cinco categorias de parada e suas provas estruturadas, definidas no contrato de convergência, podem produzir `stopped`.

## Saída

Além da saída do núcleo, informar sidecars, fases finais, blockers resolvidos ou abertos, fix rounds, redesign, hardening adiado, gates e eventual categoria de parada. Unidade `parked` não está concluída. Unidade `completed` ou `stopped` nunca reabre.

Uso explícito:

```text
$executar-plano-codex all
```
