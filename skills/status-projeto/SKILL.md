---
name: status-projeto
description: Use para ler `.bianchini/STATE.md` e resumir trabalho atual, coerência, impacto, gates, bloqueios e próximo passo sem mutar o projeto.
---

# Status do Projeto

**Anuncie:** "Lendo o estado verificável do projeto."

Resolva o binário empacotado `../_shared/bin/bm` no Unix ou `../_shared/bin/bm.exe` no Windows. Ausência bloqueia; não use fallback Python. Esta skill não corrige estado nem executa trabalho; o único write permitido é o cache efêmero do pack em `.bianchini/.runtime/context/`.

## Fluxo

1. Localizar `.bianchini/STATE.md`.
2. Sem ele, informar `MIGRATION_REQUIRED` quando houver documentação anterior do Bianchini; caso contrário, informar que o método ainda não foi iniciado. Não ler `.planning/`.
3. Validar o estado com `bm model validate --repo <repo>`. Estado inválido é reportado como erro; não inferir valores.
4. Ler somente o frontmatter e os ponteiros necessários.
5. Se `active_work.kind` for `quick`, usar `bm direct status --repo <repo>` e abrir apenas `PROGRESS.md` quando necessário.
6. Se for `debug`, usar `bm debug status --repo <repo> --id <Dxxx-do-estado>` e não abrir o caso completo sem pedido de detalhe.
7. Se for `change`, executar `bm verify status --repo <repo> --change <Cxxx>` e consultar `COHERENCE.md` e o resultado do plano ativo somente para contar findings, impacto, proofs e gates.
8. Quando houver unidade ativa, compilar `bm context pack --repo <repo> --unit <identidade>` e resumir somente o pack. `PACK_INCOMPLETE`, `PACK_TOO_LARGE` ou `STALE_EVIDENCE` é reportado sem fallback para leitura integral.

## Resposta compacta

Mostrar:

- método `0.4` e tipo/ID do trabalho ativo;
- status, fase, plano/unidade/gate atuais;
- arquitetura e `SYSTEM_MODEL.md` apontados;
- digest e aprovação;
- findings `ERROR`, `WARNING` e `INFO` abertos;
- impact radius e planos `stale`;
- verificações atuais e próxima executável;
- último trabalho concluído;
- bloqueios abertos;
- uma única `next_action`.

Não listar histórico, planos completos, hipóteses, logs ou todas as evidências. Abrir detalhes somente se o usuário pedir.

Separe claramente:

```text
planejado
implementado/commitado
testado
sandbox
deployado
efeito confirmado em produção/provedor
homologado por humano/dispositivo
```

Um limite não comprova o seguinte.

## Saída

Responder com fatos do estado validado, caminhos úteis e próximo passo. Se o estado estiver stale ou contraditório, informar o erro exato sem repará-lo.
