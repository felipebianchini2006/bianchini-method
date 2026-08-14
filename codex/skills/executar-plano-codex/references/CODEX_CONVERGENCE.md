# Convergência Codex

Este contrato substitui somente revisão, fix loop, breaker, redesign e paradas do executor base. Preflight, worktree, implementação, commits, checkpoints, gates, homologação e entrega permanecem no executor base.

## Sidecar por unidade

Cada unidade usa um sidecar independente em `artifacts/bianchini/<planning_version>/codex/convergence/<plan_id>/<unit_id>.json`. O arquivo não integra `PROJECT_STATE` nem seu schema.

`review_guard.py` deriva esse caminho de `root`, `planning_version`, `plan_id` e `unit_id`; não aceita um caminho livre na criação. Grava no mesmo diretório com arquivo temporário, `fsync` e troca atômica. Antes de substituir um sidecar válido, preserva `<unit_id>.json.bak`. Se o JSON principal estiver truncado ou inválido, carrega o backup válido e restaura o arquivo principal. IDs aceitam somente letras ASCII, números, ponto, sublinhado e hífen.

## Máquina de convergência

1. A primeira revisão classifica findings e congela blockers.
2. Blocker exige severidade `critical` ou `important`, requisito aprovado, reprodução, impacto material e cenário alcançável.
3. Findings `minor` ou `note` viram hardening adiado.
4. Revisões seguintes aceitam somente blockers congelados ou regressões comprovadas do delta encadeado pelo último head persistido.
5. Cada fix round trata um ou mais blockers abertos e é limitado a duas rodadas por unidade.
6. Cada seam aceita um redesign.
7. A unidade conclui somente sem blocker aberto.
8. Unidade concluída é terminal e nunca reabre.

Regressão do delta precisa começar exatamente no `last_review_head`, identificar o novo head revisado e cumprir o mesmo contrato de blocker. Uma nova opinião sobre código preexistente não é regressão.

## Decisões

Decisão interna produz `automatic_continue`. Bloqueio local produz `continue_independent`, preservando unidades sem dependência.

Somente credencial externa indispensável, ação destrutiva, custo novo ou impossibilidade real produzem `stop`. Nenhum comando produz `ask_user`.

## Recuperação

Na retomada, executar `status` para validar ou recuperar o sidecar. Continuar pelos blockers abertos, contadores e último evento persistidos. Não reconstruir estado pela conversa nem repetir revisão inicial.
