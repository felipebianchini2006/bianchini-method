# Escopo — Solicitações de serviço

## Objetivo
Criar e acompanhar solicitações em uma CLI local de demonstração.

## Resultados esperados
Solicitações persistentes, isoladas por usuário e atualizadas por operador.

## Atores e perfis
### ACT-001 — Usuário
- Responsabilidade: criar e consultar suas solicitações.
- Fonte: PDF p. 1
### ACT-002 — Operador
- Responsabilidade: consultar e atualizar solicitações.
- Fonte: PDF p. 1

## Fluxos
### FLW-001 — Solicitação completa
- Ator: usuário e operador autenticados com identidades sintéticas.
- Gatilho: comando de criação.
- Pré-condições: identidade válida e descrição entre 1 e 200 caracteres.
- Caminho principal: criar, listar como operador, atualizar estado e consultar como dono.
- Resultado: identificador e estado persistidos após reinício.
- Falhas: identidade, descrição ou permissão inválida rejeitada.
- Fonte: PDF p. 1

## Requisitos funcionais
### REQ-001 — Criar solicitação
- Origem: explícito.
- Fonte: PDF p. 1
- Aceite:
  - GIVEN usuário autenticado e descrição válida.
  - WHEN executar create.
  - THEN retornar identificador e estado open.
### REQ-002 — Operar solicitação
- Origem: explícito.
- Fonte: PDF p. 1
- Aceite:
  - GIVEN operador autenticado e solicitação existente.
  - WHEN listar e atualizar para done.
  - THEN exibir a solicitação e persistir o estado consultável pelo dono.
### REQ-003 — Acompanhar solicitação
- Origem: explícito.
- Fonte: PDF p. 1
- Aceite:
  - GIVEN usuário dono de uma solicitação.
  - WHEN executar get depois de reiniciar a aplicação.
  - THEN retornar descrição e estado gravados.

## Requisitos não funcionais
### NFR-001 — Persistência
- Regra: encerrar o processo não apaga registros já confirmados.
- Aceite:
  - GIVEN solicitação confirmada.
  - WHEN encerrar o processo e consultar em nova execução.
  - THEN retornar o registro com descrição e estado gravados.
- Fonte: PDF p. 1

## Regras de negócio
### BR-001 — Isolamento
- Regra: usuário acessa somente suas solicitações; somente operador lista todas e altera estado.
- Fonte: PDF p. 1

## Dados e estados
### DAT-001 — Solicitação
- Campos: identificador, dono, descrição e estado atual.
- Estados: open, in_progress e done.
- Fonte: PDF p. 1

## Integrações e efeitos externos
Não aplicável: demonstração local sem serviços externos obrigatórios.

## Critérios gerais de aceite
- Criar, operar e acompanhar pela CLI real em processos distintos.
- Rejeitar acesso alheio sem revelar o registro.
- Persistir dados e rejeitar entrada inválida.

## Comportamentos de erro
### ERR-001 — Entradas e identidades inválidas
- Condição: descrição vazia ou acima de 200 caracteres, identidade desconhecida, atualização sem estado ou permissão insuficiente.
- Resposta: código de saída não zero e mensagem JSON sem criar ou alterar a solicitação.
- Fonte: PDF p. 1

## Riscos e casos para o planejamento
### RSK-001 — Falha de gravação
- Avaliar: preservar registro quando a gravação falhar.
- Efeito no escopo: risco para análise, sem funcionalidade adicional.
- Fonte: PDF p. 1

## Dentro do escopo
- CLI local com identidades sintéticas, validação, autorização e persistência.

## Fora do escopo
- Contas reais, pagamentos, mensagens, serviços pagos, histórico de estados e interface visual.

## Decisões consolidadas
Não aplicável: o escopo de demonstração já fixa seus limites.

## Questões abertas
Nenhuma.

## Decisões bloqueantes
Nenhuma.

## Contradições
Nenhuma.

## Proveniência e cobertura
- Páginas processadas: 1 de 1.
