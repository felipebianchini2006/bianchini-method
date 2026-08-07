---
name: sdd-planning
description: Use para planejar um sistema a partir de escopo, plano mestre, design e estado real do repositório. Gera a menor quantidade de especificações e planos necessária, usando Superpowers, TDD e arquitetura mínima. Somente planejamento, nunca implementação.
---

# SDD Planning Lean

## Argumentos

- sem argumento: equivalente a `auto`;
- `auto`: selecionar o perfil após uma análise curta dos riscos;
- `lean`: forçar Lean;
- `standard`: forçar Standard;
- `full`: forçar Full.

Comandos suportados:

```text
/sdd-planning
/sdd-planning auto
/sdd-planning lean
/sdd-planning standard
/sdd-planning full
```

No modo `auto`, anunciar inicialmente: "Analisando o perfil de garantia via sdd-planning." Depois da leitura inicial, informar o perfil selecionado e o motivo.

Em perfil manual, anunciar desde o início: "Usando sdd-planning no perfil <Lean|Standard|Full> informado pelo usuário."

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

No modo `auto`, selecionar o perfil após a leitura inicial e registrar em uma linha o perfil escolhido e o motivo.

Quando o perfil for forçado manualmente, respeitar a escolha e não promover automaticamente o projeto. Registrar os riscos relevantes encontrados e aplicar controles adicionais somente às áreas críticas indispensáveis, sem transformar o projeto inteiro em Standard ou Full.

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

### 0. Definir a versão de planejamento

- O primeiro ciclo usa `docs/superpowers/v1/`.
- Planejamento ainda não aprovado pode ser atualizado na versão atual.
- Um novo ciclo iniciado após aprovação ou execução usa o próximo número disponível.
- Nunca sobrescrever planejamento histórico aprovado ou executado.
- Registrar a versão ativa em `docs/living/PROJECT_STATE.md`.

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

Invocar `superpowers:brainstorming` com esta adaptação:

- quando não existir escopo aprovado, seguir o fluxo interativo normal;
- quando escopo e plano mestre já estiverem aprovados, usar brainstorming em modo de validação;
- considerar o escopo aceito como entrada já aprovada pelo responsável;
- não reabrir requisitos definidos;
- não fazer perguntas sem uma ambiguidade que realmente bloqueie uma decisão;
- usar um único gate final para aprovação do spec e dos planos.

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

- `docs/living/PROJECT_STATE.md`: versão ativa, planos, status por plano, bloqueios, próximo passo e o gate final abaixo;
- `docs/living/DECISIONS.md`: somente decisões difíceis de reverter ou que mudam contratos;
- `docs/living/KNOWN_ISSUES.md`: somente problemas realmente abertos.

Registrar no `PROJECT_STATE.md`:

```yaml
final_gate: homologar-sistema
release_platforms: [plataformas previstas]
release_profiles: [perfis previstos]
manual_pdf: required
```

O manual PDF é obrigatório por padrão. Uma exceção precisa estar explicitamente aprovada no estado do projeto.

Todo planejamento novo começa em `docs/living/PROJECT_STATE.md` como `pending_approval`. Após aprovação explícita do usuário, atualizar o estado para `approved`, registrando a data e os planos aprovados. Uma aprovação explícita na conversa atual pode ser registrada antes da execução.

Não criar por padrão `DEVELOPMENT_LOG`, `TEST_EVIDENCE`, `REQUIREMENTS_TRACEABILITY` ou `DESIGN_IMPLEMENTATION_MAP`. O Git, o ledger do SDD, os relatórios dos agentes e os gates de teste já cobrem essas funções. Criá-los somente quando o perfil Full ou uma exigência contratual justificar.

### 5. Criar os planos

Invocar `superpowers:writing-plans` com esta adaptação:

- Um plano deve entregar software executável e testável de forma independente.
- Preferir poucos planos. Separar apenas por dependência real ou entrega independente.
- Manter arquivos exatos, interfaces, TDD, comandos e critérios verificáveis.
- Usar de **6 a 12 tarefas revisáveis por plano**; máximo de 15 sem justificativa. Não exigir microetapas artificiais de 2 a 5 minutos.
- Não criar um plano extenso de jornadas finais. Cada plano mantém somente seu gate local e os requisitos técnicos de release que realmente implementa; `homologar-sistema` monta a matriz final a partir do escopo concluído.
- Uma tarefa é a menor entrega que um revisor pode rejeitar separadamente.
- Incorporar setup, configuração e documentação à tarefa que depende deles.
- Código completo no plano somente para regras críticas, algoritmos difíceis e contratos ambíguos. Não repetir código completo em tarefas mecânicas; informar arquivos, comportamento, interfaces, teste e comando esperado.
- Cada tarefa deve apontar apenas para as seções de spec que consome.
- Não criar tarefas separadas apenas para atualizar documentação operacional.
- Ao terminar, não oferecer execução inline nem escolha de modo. Devolver o controle ao `sdd-planning`; a execução começa exclusivamente por `/executar-plano`.

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
