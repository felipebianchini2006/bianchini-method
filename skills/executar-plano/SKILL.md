---
name: executar-plano
description: Use para EXECUTAR os planos de implementação gerados pelo sdd-planning (ex. "/executar-plano all", "/executar-plano 1 a 3", "/executar-plano 1"). O melhor modelo disponível atua como orquestrador e revisor, classifica o peso de cada tarefa e delega a subagentes econômicos por nível. TDD por tarefa, revisão dupla, documentação viva atualizada, checkboxes marcados. Requer planos aprovados na versão ativa (docs/superpowers/vN/plans/).
---

# Bianchini Method — execução orquestrada de planos SDD

Executa os planos da **versão ativa** declarada em `docs/living/PROJECT_STATE.md` (`docs/superpowers/vN/plans/`; se não houver estrutura de versão, usar `docs/superpowers/plans/` como v1) com orquestração pelo melhor modelo e implementação por subagentes econômicos, calibrados pelo peso real de cada tarefa.

**Anuncie ao iniciar:** "Executando via bianchini-method: planos <intervalo>, orquestrador <modelo>."

## Argumentos

- `all` — executa todos os planos pendentes, em ordem, do primeiro não concluído até o último.
- `N a M` (ou `N-M`) — executa do plano N ao M, inclusive.
- `N` — executa apenas o plano N.
- Sem argumento — perguntar qual intervalo executar, mostrando o status atual de cada plano (tabela de fases do `PROJECT_STATE.md`).

Planos são identificados pelo prefixo numérico do arquivo (`...-01-`, `...-02-`, …). Um plano só pode iniciar se todos os anteriores estiverem concluídos (gate de saída aprovado) — se o usuário pedir um intervalo que viole isso, avisar e pedir confirmação explícita antes de prosseguir.

## Papéis e modelos

**O orquestrador/revisor é SEMPRE o melhor modelo disponível no ambiente; os subagentes são os modelos econômicos, escolhidos pelo peso da tarefa.**

| Ambiente | Orquestrador + Revisor | Tarefa CRÍTICA | Tarefa PESADA | Tarefa LEVE/mecânica |
|---|---|---|---|---|
| Claude Code | **Fable 5** (raciocínio alto) | Opus 5 | Sonnet 5 | Sonnet 5 |
| Codex | **GPT 5.6 Sol** (high ou xhigh) | GPT 5.6 Terra (extra alto) | GPT 5.6 Terra (alto) | GPT 5.6 Luna (max) |

O orquestrador NUNCA implementa tarefas ele mesmo (exceto correções triviais de 1-3 linhas durante revisão); seu trabalho é: classificar, delegar, revisar, decidir e manter a documentação viva íntegra.

## Classificação de peso (feita pelo orquestrador, por tarefa, antes de delegar)

- **CRÍTICA** — regra de domínio pura, idempotência/fila offline, validação geoespacial/temporal, segurança/autorização, migração de dados, reconciliação. Erro aqui corrompe dados ou abre falha de segurança.
- **PESADA** — integração entre módulos, telas com estados múltiplos, contratos consumidos por outros planos, testes de integração com infraestrutura real.
- **LEVE** — CRUD simples, configuração, documentação, ajustes visuais com golden/screenshot já definido, tarefas de atualização de docs vivas.

A classificação é registrada no início da execução de cada plano (lista tarefa → peso → modelo) e pode ser ajustada durante a execução com justificativa.

## Fluxo de execução

### Preparação (uma vez por sessão)
1. Ler `AGENTS.md`, `docs/living/PROJECT_STATE.md` e o(s) plano(s) do intervalo. Confirmar que specs e planos estão aprovados pelo responsável — se não estiverem, PARAR e pedir aprovação.
2. Invocar `superpowers:subagent-driven-development` e seguir seu processo como base; esta skill define a política de modelos e os gates por cima dele.
3. Criar/entrar em **worktree isolado** (`superpowers:using-git-worktrees`). Nunca implementar na branch principal.

### Por plano
1. **Tarefa 0 — revalidação + aquecimento (obrigatória, pelo orquestrador):** (a) conferir cada item de "Consumes" do plano contra o código real existente; emendar o plano onde divergiu (registrando a emenda no `DEVELOPMENT_LOG.md`); (b) **aquecer o ambiente** antes da primeira tarefa: pull das imagens Docker usadas pelo plano, `pnpm install`/`flutter precache`/build Gradle descartável conforme a stack do plano — para que nenhum custo frio caia no meio de uma tarefa; só então iniciar.
2. **Classificar** todas as tarefas do plano (peso → modelo) e registrar a tabela.
3. **Por tarefa (ou lote):**
   - **Lote de leves:** 3 a 5 tarefas LEVES consecutivas do mesmo módulo podem ir num único subagente (Sonnet), com revisão de diff conjunta ao final do lote. Tarefas CRÍTICAS e PESADAS: sempre subagente próprio.
   - Despachar subagente novo (modelo conforme peso) com **digest de contexto**: a(s) tarefa(s) completa(s) do plano (Files, Interfaces, steps), as Global Constraints específicas do plano + caminho do Apêndice de Convenções da central (consulta pontual, não releitura) e os trechos de spec citados pela tarefa — NÃO mandar o subagente reler specs inteiras; a spec fica como referência para consulta pontual. Instrução de seguir TDD à risca (RED observado → mínimo → GREEN → refatorar) e retornar diff + saída dos comandos executados.
   - **Revisão dupla pelo orquestrador, proporcional ao peso:** (a) conformidade — o diff faz exatamente o que a tarefa pede, sem escopo extra, tipos idênticos aos declarados em Produces; (b) qualidade — código limpo, testes reais (não testam mock), sem regra de negócio em controller/componente/widget. **Profundidade da verificação:** tarefa CRÍTICA ou PESADA → re-execução independente dos testes pelo revisor (infra real); tarefa LEVE → revisão de diff + re-execução apenas do comando de verificação da própria tarefa (sem re-subir suítes/infra completas). Reprovou → ciclo de correção com o MESMO subagente (máx. 2 ciclos; no 3º, escalar o modelo um nível e refazer).
   - Aprovada → marcar os checkboxes `- [ ]` → `- [x]` no arquivo do plano e commitar (se o subagente ainda não commitou) — **isso é a fonte de verdade, sempre por tarefa, nunca em lote**. `PROJECT_STATE.md` (ponteiro de progresso) também atualiza por tarefa.
   - **Demais docs vivas em lote com flush obrigatório:** `REQUIREMENTS_TRACEABILITY.md`, `TEST_EVIDENCE.md`, `DESIGN_IMPLEMENTATION_MAP.md` e `DEVELOPMENT_LOG.md` acumulam e são gravadas: a cada 5 tarefas aprovadas, no gate do plano, em QUALQUER bloqueio/parada, e antes de encerrar a sessão. **Recuperação:** se uma sessão cair entre flushes, a sessão seguinte reconstrói as docs a partir dos checkboxes marcados e do `git log` ANTES de continuar — defasagem máxima de 4 tarefas, nunca perda.
4. **Gate de saída do plano:** executar os critérios de saída definidos no próprio plano (comandos com Expected). **Builds pesados (APK/AAB, imagens de produção, E2E completo) rodam aqui e nas tarefas que os alteram diretamente — nunca em cada revisão de tarefa.** Se um estágio do gate falhar e for corrigido, re-executar apenas o estágio vermelho (e os que dependem dele), não a suíte inteira desde o início. Todos verdes → marcar o plano como concluído na tabela de fases do `PROJECT_STATE.md` + entrada no `DEVELOPMENT_LOG.md`. Algum vermelho → tratar como tarefa crítica de correção antes de prosseguir.
5. Próximo plano do intervalo.

### Encerramento do intervalo
- Rodar a suíte global aplicável (lint, typecheck, testes dos módulos tocados).
- Resumo final: planos concluídos, tarefas por modelo, desvios/emendas, requisitos que mudaram de status, bloqueios abertos.
- Se o intervalo incluiu o último plano: seguir `superpowers:finishing-a-development-branch` para integração.

## Regras invioláveis

- **Nenhum requisito vira `VERIFIED` sem evidência nova registrada** em `TEST_EVIDENCE.md` no momento da mudança.
- **Nenhuma tarefa é marcada concluída com teste falhando, lint quebrado ou revisão reprovada.** "Deve funcionar" não é evidência.
- **Specs vencem planos; planos vencem improviso.** Divergência encontrada na execução: emendar o plano citando a spec, nunca contorná-la silenciosamente. Contradição entre specs → PARAR a parte afetada e pedir decisão ao responsável.
- **Karpathy:** alterações cirúrgicas (todo diff rastreável à tarefa), simplicidade primeiro, nenhuma abstração especulativa.
- **Falha de subagente no meio da tarefa:** retomar do transcript pedindo verificação do que já existe em disco; nunca refazer às cegas por cima de trabalho parcial.
- **Execução contínua:** não perguntar "posso continuar?" entre tarefas ou planos do intervalo pedido. Parar somente por: bloqueio real, contradição de spec, credencial externa indispensável, ou gate vermelho irrecuperável.
- **Problema crítico ou importante nunca vai para `KNOWN_ISSUES.md` para viabilizar entrega** — é corrigido ou escalado.
