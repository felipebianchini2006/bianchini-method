---
name: executar-plano
description: Use para executar um ou mais planos aprovados gerados pelo sdd-planning. Aplica política enxuta de modelos e checkpoints sobre superpowers:subagent-driven-development, sem duplicar ledger, briefs, relatórios, revisão ou documentação operacional.
---

# Executar Plano Lean

**Anuncie ao iniciar:** "Executando planos <intervalo> via bianchini-method lean."

## Argumentos

- `all`: todos os planos pendentes em ordem;
- `N a M` ou `N-M`: intervalo;
- `N`: apenas um plano;
- sem argumento: mostrar o status por plano e pedir o intervalo.

Usar a versão ativa indicada em `docs/living/PROJECT_STATE.md`. Não iniciar um plano se uma dependência anterior estiver incompleta.

Executar somente planos com estado `approved` registrado em `docs/living/PROJECT_STATE.md`, incluindo data e lista de planos aprovados. Se houver aprovação explícita na conversa atual, registrá-la antes de iniciar; sem aprovação registrada ou explícita, parar.

## Regra principal

Invocar `superpowers:subagent-driven-development` e reutilizar integralmente:

- worktree;
- ledger por plano;
- `task-brief`;
- relatório do implementador;
- pacote de diff para revisão;
- revisão de conformidade e qualidade;
- fix loop;
- revisão final.

Esta skill só define política adicional. Não criar um segundo ledger, uma segunda revisão ou um segundo pacote de contexto.

Os mecanismos acima são reutilizados por tarefa. A finalização da branch e a revisão ampla são controladas pelo intervalo solicitado, não por cada plano isoladamente.

## Preparação

1. Ler `AGENTS.md`, `docs/living/PROJECT_STATE.md`, o spec central e os planos selecionados.
2. Confirmar a aprovação conforme a regra de argumentos. Sem aprovação registrada ou explícita na conversa atual, parar.
3. Usar `superpowers:using-git-worktrees` conforme exigido pela skill-base.
4. Aquecer dependências somente quando necessário e no máximo uma vez por sessão. Não executar builds descartáveis por plano sem motivo.
5. Fazer uma varredura curta de conflitos e bloqueios antes da primeira tarefa.

## Política de modelos

Escolher o menor modelo capaz de concluir em poucos turnos. Não registrar tabela de classificação em arquivo; registrar apenas exceções ou escalonamentos.

| Nível | Exemplos | Claude Code | Codex |
|---|---|---|---|
| Crítico | autorização, pagamentos, offline, migração, concorrência, geolocalização | Opus 5 | GPT 5.6 Terra extra alto |
| Padrão | integração entre módulos, tela com vários estados, infraestrutura real | Sonnet 5 | GPT 5.6 Terra alto |
| Mecânico | CRUD claro, ajuste visual isolado, configuração simples | Sonnet 5 | GPT 5.6 Luna max |

Orquestração e revisão final usam o melhor modelo disponível. Se um nome não existir no ambiente, usar o nível equivalente disponível.

## Decisões durante a execução

Quando surgirem duas ou mais opções técnicas compatíveis com o escopo aprovado, decidir autonomamente e continuar. Avaliar arquitetura vigente, padrões já usados no repositório, contratos, risco, simplicidade, testabilidade e custo de manutenção; escolher a opção que seria apresentada como recomendada.

Não interromper o desenvolvimento para pedir ao usuário que escolha entre a recomendação e alternativas inferiores. Resolver primeiro qualquer dúvida que possa ser eliminada lendo código, documentação, testes ou histórico. Registrar a escolha no relatório da tarefa e atualizar `docs/living/DECISIONS.md` somente se ela for difícil de reverter ou alterar arquitetura ou contrato.

Pedir decisão ao responsável somente quando nenhuma opção puder ser escolhida tecnicamente sem mudar escopo, regra de negócio ou contrato aprovado, ou quando a ação exigir autorização externa, custo novo relevante, operação destrutiva ou alteração de produção.

## Execução por tarefa

- Manter uma tarefa por dispatch, como exige o `subagent-driven-development`.
- Se tarefas consecutivas forem pequenas demais para justificar agentes separados, corrigir o plano fundindo-as antes da execução. Não criar lote improvisado que quebre o ledger da skill-base.
- Entregar contexto por **arquivos e caminhos**. Usar task brief, report file e review package. Não colar specs inteiras ou histórico acumulado no prompt.
- Incluir apenas decisões posteriores que não estejam registradas nos arquivos.
- O implementador segue TDD e registra comandos e resultados no relatório.
- O revisor usa o relatório e o diff. Não repetir testes já executados sem motivo concreto.
- Reexecutar independentemente apenas quando a evidência estiver incompleta, o teste for não determinístico ou a tarefa for crítica e o risco justificar.
- Builds pesados, E2E amplo e suítes globais ficam no gate do plano ou na tarefa que os altera diretamente.
- O fix loop e a escalada seguem a skill-base. Não criar limites concorrentes.

## Estado e documentação

O ledger do SDD é a fonte de verdade por tarefa.

Atualizar `docs/living/PROJECT_STATE.md` somente:

- ao iniciar ou concluir um plano;
- ao encontrar bloqueio;
- antes de encerrar a sessão.

Atualizar `docs/living/DECISIONS.md` apenas quando uma decisão de contrato ou arquitetura mudar. Atualizar `docs/living/KNOWN_ISSUES.md` apenas para problema realmente aberto. Não manter `DEVELOPMENT_LOG`, `TEST_EVIDENCE` ou checkboxes do plano como fontes paralelas por tarefa.

## Gates

Ao concluir cada plano, executar seus comandos de saída. Reexecutar somente o estágio que falhou e seus dependentes.

Quando o intervalo contém vários planos, adiar a revisão ampla de branch e `finishing-a-development-branch` até o último plano selecionado. Os gates de cada plano continuam obrigatórios. Fazer uma única revisão ampla no final do intervalo, além das revisões por tarefa, e não finalizar a branch separadamente após cada plano.

Se o intervalo incluir o último plano aprovado e `docs/living/PROJECT_STATE.md` registrar `final_gate: homologar-sistema`, invocar `homologar-sistema` automaticamente depois dos gates locais e antes da revisão ampla final. Manter as correções encontradas na mesma branch; somente após aceite executar a única revisão ampla e `superpowers:finishing-a-development-branch`.

Se ambiente ou integração externa impedir a homologação, não finalizar o projeto como entregue. Registrar `BLOQUEADO`, o que foi validado com fake ou sandbox e o requisito restante. Bugs da homologação são corrigidos exclusivamente por `corrigir-bug`.

## Paradas permitidas

Parar somente por bloqueio externo indispensável, contradição entre specs, decisão do responsável realmente necessária ou gate irrecuperável. Não pedir autorização entre tarefas ou planos do intervalo solicitado.

A existência de múltiplas opções técnicas não é uma parada permitida: aplicar a regra de decisão autônoma e seguir com a recomendada.

## Resposta final

Informar planos concluídos, gates executados, resultado da homologação, caminhos do resumo e manual PDF, commits principais, decisões alteradas e bloqueios abertos. Não repetir relatórios completos dos subagentes.
