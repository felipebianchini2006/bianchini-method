# Contexto eficiente no método 0.4

Contexto derivado nunca substitui `.bianchini/STATE.md`, o `SYSTEM_MODEL.md`, as specs, o plano aprovado, os resultados ou as evidências atuais.

## Planejamento

O pacote global contém o sistema completo, mas cada plano deve ser rejeitável isoladamente. Use IDs e contratos para carregar somente:

- plano ativo;
- providers e dependências concluídas;
- consumers que podem ser afetados;
- módulos, interfaces, dados, journeys e invariantes tocados;
- specs e decisões explicitamente referenciadas.

O `ProjectModel` recompõe `S0 → Sn` de forma determinística. Não copie a narrativa inteira da arquitetura para cada plano.

## Execução

`workspace create` valida o digest aprovado, dependências, contratos consumidos e status `stale` antes de criar a branch `bm/cxxx-pxx`. Dentro do workspace, carregue o plano, o modelo efetivo e o último resultado necessário; não releia toda a mudança por padrão.

Mapas de repositório e relatórios temporários ficam em `.bianchini/.runtime/`, vinculados ao hash do `HEAD` e ao digest do escopo. Mudança em qualquer um invalida o cache.

## Resultados e fechamento

Cada plano grava somente seu delta real, verificações e impacto em `results/Pxx.md`. `STATE.md` mantém apenas o índice atual. O fechamento recompõe o modelo pelos resultados, exige equivalência com o `SYSTEM_MODEL.md` final e arquiva o ciclo.

## Regras

- `.planning/` não é contexto, fallback nem destino.
- Histórico detalhado fica em `changes/`, `quick/`, `debug/` e `archive/`.
- Evidência anterior ao fingerprint vigente é obsoleta.
- Resumos nunca podem transformar `not_run`, sandbox ou leitura de código em prova de produção.
- Compressão de contexto não remove requisito, guard, finding ou bloqueio.
