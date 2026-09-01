# Contrato do SCOPE.md vindo de PDF

O draft não contém frontmatter. `bm scope seal` adiciona identidade, fonte, cobertura, horário e digest.

## Ordem obrigatória

```text
# Escopo — nome objetivo
## Objetivo
## Resultados esperados
## Atores e perfis
## Fluxos
## Requisitos funcionais
## Requisitos não funcionais
## Regras de negócio
## Dados e estados
## Integrações e efeitos externos
## Critérios gerais de aceite
## Comportamentos de erro
## Riscos e casos para o planejamento
## Dentro do escopo
## Fora do escopo
## Decisões consolidadas
## Questões abertas
## Decisões bloqueantes
## Contradições
## Proveniência e cobertura
```

Cada seção deve conter informação útil. Quando uma categoria realmente não aparecer, registre `Não especificado no PDF.` ou `Não aplicável:` seguido da justificativa. Não use ausência genérica para esconder uma leitura incompleta.

`Questões abertas`, `Decisões bloqueantes` e `Contradições` devem conter exatamente `Nenhuma.` no documento selado.

## IDs e fontes

Use prefixos:

- `ACT`: ator;
- `FLW`: fluxo;
- `REQ`: requisito funcional;
- `NFR`: requisito não funcional;
- `BR`: regra de negócio;
- `DAT`: dado ou estado;
- `INT`: integração ou efeito externo;
- `ERR`: comportamento de erro;
- `RSK`: risco que o planejamento deve avaliar;
- `DEC`: decisão consolidada com o usuário.

Todo item `### ID-001 — título` exige uma linha `- Fonte:`. Fontes aceitas:

```text
- Fonte: PDF p. 4
- Fonte: PDF pp. 4-6
- Fonte: decisão do usuário
```

Um item explícito usa página. Uma decisão fora do PDF usa `decisão do usuário`. Uma inferência ainda não confirmada não entra no documento selado.

## Fluxo

```markdown
### FLW-001 — Registrar solicitação
- Ator: Cliente autenticado.
- Gatilho: envio do formulário.
- Pré-condições: sessão válida e campos obrigatórios disponíveis.
- Caminho principal: preencher, revisar e confirmar o envio.
- Resultado: solicitação criada com identificador público.
- Falhas: entrada inválida é recusada sem criar registro parcial.
- Fonte: PDF pp. 3-4
```

## Requisito

```markdown
### REQ-001 — Registrar solicitação
- Origem: explícito.
- Fonte: PDF p. 3
- Aceite:
  - GIVEN cliente autenticado e dados válidos.
  - WHEN confirmar o envio.
  - THEN criar uma solicitação e exibir o identificador.
```

O aceite deve fixar estado inicial, ação e resultado observável. Não usar "funciona", "adequado", "tratar erros" ou termos subjetivos.

## Risco sem expansão de escopo

```markdown
### RSK-001 — Atualização concorrente
- Avaliar: evitar perda de estado quando duas operações modificarem o mesmo registro.
- Efeito no escopo: risco para análise; não adiciona requisito funcional.
- Fonte: PDF p. 7
```

Risco pode orientar arquitetura, teste ou guard. Ele não cria funcionalidade que o PDF não contratou.

## Decisão consolidada

```markdown
### DEC-001 — Responsável pelo cancelamento
- Decisão: somente o criador pode cancelar antes do atendimento.
- Impacto: fecha permissão e transição do fluxo FLW-002.
- Fonte: decisão do usuário
```

## Proveniência

O draft informa as páginas processadas. O CLI substitui a seção por contagens calculadas:

```markdown
- Páginas processadas: 1-12 de 12.
- Itens estruturados: 18
- Itens sem fonte: 0
- Questões abertas: 0
- Decisões bloqueantes: 0
- Contradições abertas: 0
```

## Gate semântico

Antes do selo, confirme:

- cada página foi lida;
- cada comportamento do PDF aparece em um item rastreável;
- cada requisito tem aceite verificável;
- limites positivos e negativos são compatíveis;
- falha requerida está em `ERR`; risco sugerido está em `RSK`;
- nenhuma escolha de arquitetura foi apresentada como requisito;
- nenhuma informação foi adiada silenciosamente;
- outra LLM não precisa adivinhar ator, ação, estado, resultado ou limite.
