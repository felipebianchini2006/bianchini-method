---
name: status-projeto
description: Use com invocação explícita de /status-projeto ou pedido de status em projeto cujo PROJECT_STATE declare method_version 2. Para v1, somente informa a rota legado sem assumir execução standalone.
---

# Status do Projeto

**Anuncie:** "Lendo o estado verificável do projeto."

Leia [`../_shared/METHOD_CONTRACT.md`](../_shared/METHOD_CONTRACT.md) e resolva `bm.py`. Esta skill é somente leitura: não corrige estado, não executa plano e não cria artefato.

## Fluxo

1. Executar `bm.py direct status --repo <repo>` antes de exigir `PROJECT_STATE.md`.
2. Se houver execução ativa, mostrar `Modo: direto`, objetivo, branch, checkpoint, verificação, bloqueios e próxima ação. Para detalhe, abrir apenas `PROGRESS.md`.
3. Sem execução direta ativa, localizar `docs/living/PROJECT_STATE.md`.
4. Executar `bm.py route` com caminho do Superpowers quando detectado.
5. V1 com Superpowers: ler estado/status legado e informar que o executor continua legado.
6. V1 sem Superpowers: informar `BLOQUEADO` e a dependência ausente; não sugerir execução v2 automática.
7. V2: executar `bm.py validate-state` e `bm.py status <state> --root <repo> --format text`. Usar o JSON padrão somente para automação.
8. Se estado v2 for inválido, reportar erros do schema e parar; não inferir valores.

## Resposta compacta

Mostrar:

- método/rota e `planning_version`;
- `planning_status`, digest e aprovação;
- planos por status e unidade atual;
- política `grouped|slice|strict` de cada plano ativo;
- plano/unidade/gate atuais e próximo plano executável com seu modo;
- `verification.fast`, `plan` e `release`;
- auditoria arquitetural;
- RC, homologação, revisão final e entrega;
- bloqueios abertos;
- telemetria local resumida, somente quando habilitada;
- uma única `next_action`.

Não ler spec, planos completos ou ledgers quando o estado basta. Abrir apenas o checkpoint/ledger do plano ativo se o usuário pedir detalhe operacional.

## Saída

Responder com fatos do estado validado, caminhos relevantes e próximo passo. Distinguir claramente `planejado`, `implementado`, `gate aprovado`, `homologado` e `entregue`.
