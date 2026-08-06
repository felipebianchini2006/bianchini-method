---
name: sdd-planning
description: Use para planejar um sistema a partir de escopo, plano mestre, design e estado real do repositório. Gera a menor quantidade de especificações e planos necessária, usando Superpowers, TDD e arquitetura mínima. Somente planejamento, nunca implementação.
---

# SDD Planning Lean

**Anuncie ao iniciar:** "Usando sdd-planning no perfil <Lean|Standard|Full>."

## Objetivo

Produzir documentação suficiente para um agente implementar corretamente, sem transformar documentação, revisão e rastreabilidade em um segundo produto.

## Regras absolutas

- Somente planejamento. Não criar código de produção, scaffolding, dependências, migrações ou telas.
- Usar `superpowers:brainstorming` para validar o desenho e `superpowers:writing-plans` para os planos. Ler as versões atuais das skills.
- Reutilizar o documento gerado pelo brainstorming como **spec central**. Nunca escrever uma segunda especificação com o mesmo conteúdo.
- Escolher a arquitetura mais simples que atende o escopo atual. Proibidas abstrações e infraestrutura especulativas.
- Referenciar arquivos e seções em vez de copiar conteúdo entre documentos.
- Não fixar versões ou bibliotecas sem necessidade. Consultar documentação atual apenas para APIs instáveis, decisões não óbvias ou versões que precisem ser fixadas.
- Documentos em português do Brasil; identificadores de código em inglês.

## Perfil de garantia

O padrão é **Lean**. Registrar em uma linha o perfil escolhido e o motivo.

### Lean

Usar na maioria dos MVPs e sistemas comerciais:

- um spec central;
- zero specs complementares por padrão;
- auto-revisão do orquestrador;
- validação das jornadas críticas;
- documentação viva mínima.

### Standard

Usar quando houver pelo menos dois fatores relevantes: sincronização offline, geolocalização, pagamentos ou comissões complexas, dados sensíveis, mais de quatro perfis com permissões distintas, múltiplos aplicativos, jobs críticos ou várias integrações externas dependentes entre si.

Pode adicionar até três specs complementares. Revisão cruzada somente dos contratos compartilhados e regras críticas.

### Full

Usar apenas por solicitação explícita ou necessidade de auditoria, regulação, segurança elevada ou risco operacional grave. Ao escolher Full, ler `references/full-assurance.md`.

## Fluxo

### 1. Ler as fontes uma vez

Localizar e ler, nesta ordem:

1. escopo aceito, incluindo PDF;
2. plano mestre;
3. design de referência, se existir;
4. `AGENTS.md`, `CLAUDE.md` e `README.md`;
5. estrutura, código e histórico Git existentes.

Criar uma síntese curta com fatos confirmados, premissas, conflitos e bloqueios reais. Resolver conflitos pela ordem: decisão recente do responsável, escopo aceito, plano mestre, spec aprovada, ADR e código.

Se o design existir, ler `references/design-import.md`. Não carregar essa referência quando não houver design.

### 2. Criar o spec central

Invocar `superpowers:brainstorming`. Quando o escopo e o plano mestre já estiverem aprovados, usar o brainstorming como validação de lacunas e decisões, sem reabrir requisitos definidos.

Salvar diretamente em:

`docs/superpowers/vN/specs/YYYY-MM-DD-<sistema>-system-design.md`

O spec central deve conter somente o necessário:

- objetivo, limites e não objetivos;
- arquitetura e componentes;
- perfis e permissões;
- entidades, estados e regras de domínio;
- contratos compartilhados realmente usados;
- segurança e tratamento de dados aplicáveis;
- estratégia de testes por risco;
- jornadas críticas;
- responsabilidades externas;
- premissas, decisões e bloqueios.

Convenções como paginação, erros, nomes, datas e enums entram apenas se o projeto as utiliza. Não criar catálogos preventivos.

### 3. Decidir se precisa de specs complementares

Criar uma spec complementar somente quando o subsistema:

- possui regras críticas próprias;
- será implementado por agente independente;
- tem contrato compartilhado difícil de manter no spec central; ou
- não cabe com clareza no contexto do spec central.

No perfil Lean, preferir seções no spec central. No Standard, limitar a três specs. Cada complementar deve referenciar o central e conter apenas o delta do subsistema.

### 4. Criar documentação viva mínima

Criar ou atualizar:

- `docs/living/PROJECT_STATE.md`: versão ativa, planos, status por plano, bloqueios e próximo passo;
- `docs/living/DECISIONS.md`: somente decisões difíceis de reverter ou que mudam contratos;
- `docs/living/KNOWN_ISSUES.md`: somente problemas realmente abertos.

Não criar por padrão `DEVELOPMENT_LOG`, `TEST_EVIDENCE`, `REQUIREMENTS_TRACEABILITY` ou `DESIGN_IMPLEMENTATION_MAP`. O Git, o ledger do SDD, os relatórios dos agentes e os gates de teste já cobrem essas funções. Criá-los somente quando o perfil Full ou uma exigência contratual justificar.

### 5. Criar os planos

Invocar `superpowers:writing-plans`.

- Um plano deve entregar software executável e testável de forma independente.
- Preferir poucos planos. Separar apenas por dependência real ou entrega independente.
- Alvo de **6 a 12 tarefas por plano**; máximo de 15 sem justificativa.
- Uma tarefa é a menor entrega que um revisor pode rejeitar separadamente.
- Incorporar setup, configuração e documentação à tarefa que depende deles.
- Código completo no plano somente para regras críticas, contratos ambíguos ou algoritmos difíceis. Para trabalho mecânico, informar arquivos, comportamento, interfaces, teste e comando esperado. Esta calibração substitui a repetição de código da skill-base quando ela não agrega decisão.
- Cada tarefa deve apontar apenas para as seções de spec que consome.
- Não criar tarefas separadas apenas para atualizar documentação operacional.

### 6. Revisar proporcionalmente

Sempre executar auto-revisão de cobertura, placeholders, consistência de tipos e escopo.

Despachar revisão cruzada somente quando houver contratos entre specs ou planos, regras de autorização, pagamentos, sincronização, geolocalização ou outra área crítica. Revisar apenas esses pontos, não todos os documentos integralmente.

Criar `docs/superpowers/vN/PLANNING_REVIEW.md` com no máximo:

- fontes lidas;
- perfil usado e motivo;
- arquivos criados;
- requisitos ou decisões bloqueadas;
- riscos críticos;
- resultado da revisão.

## Encerramento

Responder apenas com os caminhos do spec, planos, documentação viva alterada, bloqueios reais e pedido de aprovação. A implementação começa por `/executar-plano`, nunca diretamente por improviso.
