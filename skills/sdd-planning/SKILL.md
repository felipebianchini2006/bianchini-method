---
name: sdd-planning
description: Use quando o usuário pedir para planejar um sistema/projeto novo a partir de escopo comercial (PDF), plano mestre (.md) e referência visual (pasta design com HTML/ZIP). Gera especificações aprováveis e planos de implementação TDD via Spec-Driven Development do Superpowers, com revisão cruzada, convenções compartilhadas e documentação viva. Apenas planejamento — nunca implementa código de produção.
---

# SDD Planning — planejamento completo de sistema (specs + planos)

Fluxo de planejamento Spec-Driven Development calibrado por lições reais: convenções fixadas antes das specs, revisão adversarial como gate obrigatório, planos escritos em ondas, código completo só em tarefas críticas.

**Anuncie ao iniciar:** "Usando sdd-planning para gerar especificações e planos deste sistema."

## Regras absolutas da sessão

- **Somente planejamento.** Pode criar/alterar: documentação, inventário de design, ADRs, especificações, planos, manifests, arquivos de orientação de agente. NÃO pode: implementar funcionalidade, criar scaffolding de produção, instalar dependências do produto, escrever migrações reais, criar telas, marcar requisito como concluído, iniciar execução de plano.
- **Karpathy sempre:** declarar premissas e dúvidas; solução mínima que atende ao escopo (sem microserviços, Kubernetes, GraphQL, CQRS, event sourcing, Redis ou abstração genérica sem necessidade comprovada e registrada); alterações documentais cirúrgicas; toda exigência vira critério verificável.
- **Skills obrigatórias:** invocar `superpowers:brainstorming` antes de qualquer spec e `superpowers:writing-plans` antes de qualquer plano. Invocar `karpathy-guidelines` se disponível. Ler as skills atuais, não agir de memória.
- **Melhores práticas de linguagem:** para cada tecnologia da stack, consultar a documentação oficial atual (context7/`resolve-library-id`+`query-docs` ou WebFetch) antes de fixar versões, padrões e idiomas nas specs. Nunca fixar versão de memória.
- **Idioma:** documentos em português do Brasil; identificadores de código em inglês.
- **Data real do ambiente** nos nomes de arquivo (`YYYY-MM-DD-`).
- **Versionamento por ciclo de entrega:** todo o planejamento vive em `docs/superpowers/vN/` (specs/, plans/, PLANNING_REVIEW.md). Primeiro ciclo = `v1`. Se `docs/superpowers/v<N>/` já existir com planejamento aprovado/executado e o pedido for um NOVO ciclo (novo escopo, novas features), criar `v<N+1>/` — NUNCA editar nem misturar arquivos de uma versão anterior, que é registro histórico congelado. A nova versão referencia a anterior nas fontes, herda decisões/ADRs ainda válidos (por referência, não cópia) e ganha rastreabilidade própria dos requisitos novos/alterados. `PROJECT_STATE.md` (único, em docs/living/) declara a versão ativa. Se encontrar planejamento antigo SEM estrutura de versão (specs/plans direto em docs/superpowers/), tratá-lo como v1: perguntar ao usuário se deseja movê-lo para v1/ antes de criar v2/.

## Fase 0 — Localização das fontes (obrigatória, nesta ordem)

1. **Escopo comercial**: procurar `*.pdf` em `docs/`, raiz e anexos da sessão. Ler TODAS as páginas.
2. **Plano mestre**: procurar `*.md` com nome contendo `PLANO`/`MASTER`/`plano-mestre` em `docs/` e raiz. Ler integralmente (sem pular seções).
3. **Referência visual**: procurar pasta `design/` (também `design/reference/`, `docs/design/`) contendo HTML e/ou ZIP exportados do Cloud Design. 
4. **Instruções existentes**: AGENTS.md, CLAUDE.md, README.md.
5. **Estado real do repositório**: git (inicializar se não existir, com commit de baseline), estrutura, commits, código existente. Não presumir repositório vazio.

Se alguma fonte não existir, registrar a ausência e perguntar ao usuário apenas se ela for indispensável (escopo ou plano mestre). Design ausente não bloqueia specs de backend.

Produzir lista curta: fatos confirmados; premissas; **conflitos entre fontes** (nunca escolher silenciosamente — registrar trechos e resolver pela ordem de autoridade: decisão recente do responsável > escopo aceito > plano mestre > specs > ADRs > código); dados externos ausentes; decisões adiáveis.

## Fase 1 — Importação e inventário do design (se existir)

1. Extrair ZIP com segurança para `design/reference/source/` (verificar path traversal e symlinks; nunca sobrescrever o original).
2. Gerar `design/reference/MANIFEST.sha256` de todos os arquivos-fonte.
3. Servir o HTML em servidor local temporário; capturar screenshots de TODAS as telas/estados navegáveis (playwright-cli com `--browser=chromium`), em viewports desktop e mobile, salvando em `design/reference/screenshots/`. Extrair texto integral das telas para JSON.
4. Criar `design/reference/DESIGN_INVENTORY.md` com: arquivos+hashes, páginas, telas, componentes, variantes, estados (loading/vazio/erro/sucesso — presentes E ausentes), cores, tipografia (pesos realmente usados, não só carregados), espaçamentos, bordas/raios/sombras, ícones, imagens, fontes+licenças, breakpoints, interações, partes ausentes, diferenças HTML×nativo, viewports de referência para comparação visual.
5. Regra de fidelidade 1:1: mesmos tokens, hierarquia, espaçamentos, tipografia, estados; estados ausentes derivados com os tokens existentes e registrados; proibido "melhorar" o design.
6. Encerrar o servidor temporário ao final. Commitar a importação.

## Fase 2 — Especificação central COM Apêndice de Convenções Compartilhadas

Criar `docs/superpowers/vN/specs/YYYY-MM-DD-<sistema>-system-design.md` cobrindo: visão e limites; não objetivos/fora do escopo; interpretação operacional vinculante; valores provisórios configuráveis (nunca hardcoded); arquitetura e stack (verificada nas docs oficiais; a mais simples que atende); **conflitos resolvidos entre fontes** (tabela: fonte A × fonte B × decisão × motivo × registro); perfis e permissões; estados e transições de todas as entidades; regras exatas de validação; modelo de dados; contratos; segurança/privacidade/auditoria; observabilidade; estratégia de testes (TDD obrigatório; integração real de banco — mock de extensões como PostGIS proibido); jornadas finais de usuário; responsabilidades do cliente; rastreabilidade ID→spec complementar de TODOS os requisitos; riscos; ADRs a criar; perguntas bloqueadoras.

**Apêndice de Convenções Compartilhadas (obrigatório, ANTES das specs complementares):** envelope de erro único (JSON exato); envelope de paginação único e lista fechada de endpoints paginados; mapeamento código de erro → HTTP status; nomes de arquivos, tipos e tokens de injeção dos artefatos compartilhados (tipos do banco, identidade autenticada/decorator de sessão, requestId, clock injetável); catálogo fechado de enums e flags com ordem canônica; convenções de nomenclatura (JSON camelCase, banco snake_case, UTC timestamptz). **Toda spec e todo plano copiam deste apêndice; proibido redefinir localmente.**

## Fase 3 — Specs complementares (paralelo) + revisão adversarial (gate)

- Decompor por subsistema (referência: fundação/design, identidade/configuração, motor de domínio, app offline, mídia, painel/relatórios, deploy/operações, qualidade/homologação — ajustar ao sistema real).
- Delegar a subagentes em paralelo (Opus nas complexas, Sonnet nas demais), cada prompt: ler central (vinculante) + seções do plano mestre + inventário; seções obrigatórias (objetivo, não objetivos, requisitos por ID, fluxos, estados, modelo de dados, contratos, erros, segurança, observabilidade, acessibilidade, offline, design, testes, critérios de aceite verificáveis, dependências, riscos, decisões explícitas D-NN-XX, perguntas bloqueadoras); zero TBD/TODO; self-review inline. Subagentes NÃO executam git (evita corrida de índice); o orquestrador commita após revisar.
- **Gate obrigatório:** agente de revisão adversarial cruzada (Opus) verificando: consistência de nomes entre specs, contradições de valores/semântica, tensões com o plano mestre sem decisão registrada, lacunas de cobertura por ID, placeholders, interfaces entre specs campo a campo. Corrigir TODOS os achados críticos/importantes (agente de correção com resoluções decididas pelo orquestrador) antes dos planos. Confirmar por grep.

## Fase 4 — Documentação viva + ADRs

A documentação viva é a **memória operacional do projeto durante a execução**: resume estado e evolução, criada A PARTIR das specs e planos gerados, **sem duplicar conteúdo técnico** (referenciar por caminho/seção, nunca copiar integralmente). A estrutura completa deve estar pronta ANTES da fase de implementação.

Criar `AGENTS.md` (ordem de leitura, Superpowers, Karpathy, TDD, worktree para implementação, atualização da documentação viva ao concluir CADA tarefa, proibições: não inventar requisito, não alterar design de referência, não declarar conclusão sem evidência nova) e, em `docs/living/`:

- **`PROJECT_STATE.md`** — estado atual do projeto (estritamente factual — nada não implementado descrito como pronto); **fases planejadas** (tabela: fase/plano → objetivo em 1 linha → status pendente/em andamento/concluída, referenciando os planos por caminho); **progresso real** (plano ativo, última tarefa concluída, próxima tarefa); bloqueios; próximos passos; comandos de verificação atuais.
- **`DEVELOPMENT_LOG.md`** — histórico cronológico das principais alterações durante a execução (data, plano/tarefa, o que mudou em 1-2 linhas, commit); decisões tomadas durante execução; mudanças de escopo aprovadas pelo responsável. Inicia com uma única entrada: a sessão de planejamento.
- **`DECISIONS_LOG.md`** — decisões arquiteturais e técnicas importantes: contexto, alternativas avaliadas, decisão tomada, impacto, referência ao ADR quando existir.
- **`REQUIREMENTS_TRACEABILITY.md`** — rastreamento requisito → spec → plano → tarefa → código → teste → evidência (colunas Requirement ID | Spec | Plan | Task | Code | Test | Evidence | Status; status NOT_PLANNED/PLANNED/IN_PROGRESS/VERIFIED/BLOCKED; nenhum VERIFIED no planejamento).
- **`KNOWN_ISSUES.md`** — problemas conhecidos, limitações e riscos abertos (severidade, impacto, reprodução, decisão; crítico/importante não pode ser escondido para viabilizar entrega).
- **`TEST_EVIDENCE.md`** — só evidência real (data/commit, ambiente, comando exato, resultado); nunca registrar comando não executado como se tivesse passado.
- **`DESIGN_IMPLEMENTATION_MAP.md`** — tela da referência → viewport → arquivo implementado → estado → screenshots esperado/atual → diferença aceita → teste visual.

Regras vinculantes (repetir no AGENTS.md): toda execução futura atualiza a documentação viva ao concluir tarefas; nenhum item é marcado como concluído sem evidência real; a documentação viva resume — o detalhe técnico vive nas specs/planos.

ADRs (`docs/architecture/decisions/`) somente para decisões difíceis de reverter.

## Fase 5 — Planos em ondas (writing-plans)

Invocar `superpowers:writing-plans` e delegar a subagentes seguindo o formato da skill (cabeçalho "For agentic workers", Goal/Architecture/Tech Stack, Global Constraints verbatim, Estrutura de arquivos, tarefas `### Task N` uniformes com Files/Interfaces Consumes-Produces e steps checkbox de 2-5 min).

**Ondas obrigatórias** (nenhum plano lê outro parcialmente gerado): onda 1 = plano de fundação sozinho; onda 2 = planos que consomem só a fundação; ondas seguintes = planos que consomem os anteriores COMPLETOS. Cada plano declara na abertura os artefatos que consome, com citação de tarefa e assinatura exata.

**Calibração de código:** ciclo TDD com código completo (teste RED real + implementação mínima) obrigatório apenas nas tarefas CRÍTICAS (regras de domínio, offline/idempotência, validação geoespacial/temporal, segurança) — a spec marca quais são. Demais tarefas: comportamento a verificar + assinatura exata + comando + Expected, sem corpo de código.

**Proibições nos planos:** TBD/TODO/"implementar depois"/"igual à tarefa anterior"/caminho inexistente sem tarefa criadora/tipos divergentes entre tarefas/teste que só verifica mock. Cada plano inclui tarefas de: atualizar PROJECT_STATE, rastreabilidade, evidência, mapa de design (se UI), revisão de diff, revisão de conformidade+qualidade como gate de saída.

**Plano final obrigatório — validação dirigida por agente:** o agente abre o sistema como usuário real e executa todas as jornadas e edge cases, com screenshot+log por passo, nos alvos: web (Playwright, build de produção, viewports desktop e mobile) e mobile (emulador Android; simulador iOS como verificação de robustez quando o projeto for Flutter — registrar que iOS não é entrega, salvo decisão contrária). Primeira tarefa de CADA plano na execução: **revalidação** dos Consumes contra o código real, emendando o plano onde divergiu.

**Gate pós-planos:** revisão cruzada de interfaces ENTRE planos (mesmo protocolo da Fase 3). Emendas feitas preferencialmente pelo agente autor (contexto intacto, via SendMessage); se um agente falhar no meio, retomá-lo do transcript pedindo verificação do que já existe em disco. Confirmar toda emenda por grep.

## Fase 6 — Matriz de cobertura e relatório

1. Script verificando TODOS os IDs em: central, specs complementares, planos, rastreabilidade. Corrigir lacunas.
2. Varredura global de placeholders e de abstrações proibidas (grep).
3. Criar `docs/superpowers/vN/PLANNING_REVIEW.md`: fontes lidas; specs e planos criados (com métricas); cobertura N/N; conflitos resolvidos; decisões pendentes de ratificação (todas as D-NN-XX novas em bloco único); bloqueios externos reais; riscos; resultado dos scans; revisão final de 20 pontos (escopo exato, regras numéricas consistentes, servidor autoridade, offline idempotente, reconciliação, geo real, sem rastreamento contínuo, mídia privada, RBAC no backend, alertas persistidos, fallback de tempo real, design 1:1, estados de erro, testes nos alvos, jornada clica-tudo, homologação separada da simulação, docs vivas por tarefa, sem abstração especulativa, sem placeholder, tipos consistentes — adaptar ao domínio); confirmação de que nenhuma implementação foi iniciada.
4. Commitar tudo em commits temáticos.

## Resposta final (somente isto)

1. Caminho da especificação central; 2. caminhos das complementares; 3. caminhos dos planos; 4. caminho do inventário de design; 5. caminho do PLANNING_REVIEW.md; 6. bloqueios externos reais; 7. pedido de aprovação do responsável (specs, planos e ratificação em bloco das decisões D-NN-XX novas). A execução só começa após aprovação explícita, pelo plano 1, em worktree isolado, via `superpowers:subagent-driven-development`.
