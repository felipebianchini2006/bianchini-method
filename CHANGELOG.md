# Changelog

## 3.1.0 - Context Efficiency determinística

- exige `Change` e `Readiness refs` em cada unidade de novos planejamentos quality v2, validando existência, destino e cobertura no readiness;
- adiciona contexto hidratado opcional ao `task-brief`, limitado à unidade, specs referenciadas, readiness aplicável, gates rápidos e final do ledger;
- adiciona `spec-diff` como projeção ADDED/MODIFIED/REMOVED vinculada aos digests das specs completas;
- adiciona `mutation-evidence verify` para normalizar relatórios, classificar survivors e vincular a prova ao HEAD ou fingerprint do RC;
- preserva `quality_version: 1`, specs completas, aprovação única e ausência de score global de mutação;
- adiciona CI versionada para executar todos os shards e validar o CLI.

## 3.0.0 - Planning Stability e design independente

- adiciona `/design-projeto` para gerar protótipo HTML estático, tokens, contrato e manifesto visual antes do SDD, sem depender do Claude;
- aceita design somente por `DESIGN_MANIFEST.json` aprovado e ligado ao hash do escopo;
- adiciona `READINESS.md` e `USER_ACTIONS.md` com decisões, suposições, pitfalls, ações externas, spikes, superfícies e specs de domínio rastreáveis;
- limita o checker semântico a duas passagens e uma única correção;
- congela planos aprovados e classifica divergências como detalhe interno, ajuste limitado ou mudança material;
- amplia o envelope de autonomia e restringe interrupções a dependência externa, custo, ação irreversível, mudança material ou impossibilidade comprovada;
- cria specs atuais em `docs/bianchini/current/specs/`, mudanças em `changes/` e archive determinístico por `cycle-close`;
- preserva projetos v1 e ciclos `quality_version: 1` já aprovados sem migração no meio da execução;
- aplica as mesmas barreiras de redesign e autonomia ao overlay Codex.

## 2.8.0 - Testes adaptativos sem custo por microtarefa

- distribui unitários, integração/contrato, E2E, regressão e mutation testing entre `verification.fast`, `verification.plan` e `verification.release`;
- mantém regressão como estratégia transversal e impede tarefa, revisão ou subagente por camada de teste;
- limita o estágio `fast` a provas focadas, move E2E crítico e mutação seletiva para o gate do plano e reserva a regressão ampla para o release;
- adiciona `test_strategy` e `mutation_policy` ao resultado de `bm.py policy`, sem alterar schema ou estado do projeto;
- não usa score global de mutação e só bloqueia survivor que demonstre comportamento aprovado alto/crítico sem proteção;
- protege o executor Codex contra E2E completo, regressão completa, mutação e campanhas de cobertura por unidade;
- mantém `homologar-sistema` como consumidor das provas automatizadas e executor do passe real, sem recriar a campanha técnica.

## 2.7.0 - Homologação operacional no release candidate

- mantém regressão e E2E como baseline, mas impede que automação isolada encerre a homologação de produtos com interface;
- exige abrir e operar o RC real por plataforma e perfil, cobrindo fluxos críticos e ações primárias expostas;
- adiciona inventário da superfície executável, sucesso, validação/erro, cancelamento/recuperação, persistência e verificação de console/rede;
- torna a varredura visual básica obrigatória para toda interface, independentemente de design importado ou brand kit;
- concentra o contrato operacional e visual em `homologar-sistema/SKILL.md`, sem depender de prompt externo;
- atualiza a ordem executável para `automated_regression -> coded_e2e -> proof_map -> real_system_pass -> visual_sweep`.

## 2.6.0 — Breaker epistêmico por seam de risco

- `bm.py policy` passa a contar o orçamento de fix rounds por `risk_seam` (`--risk-seam`, `--seam-round`): renomear, dividir ou reabrir a tarefa não zera a contagem do mesmo seam;
- finding de classe estrutural (`--structural-finding`: crash window, partial commit, TOCTOU, efeito externo antes de persistência, retry após timeout, idempotência concorrente, recuperação após restart) invalida a hipótese imediatamente e retorna `hypothesis_invalidated`/`redesign_required`;
- dois pareceres consecutivos com critical/important no mesmo seam (`--consecutive-seam-findings`) disparam breaker antecipado; antes de novo patch, o contrato exige máquina de estados, limites transacionais, pontos de crash, estado durável de retomada e matriz de falhas;
- fix round formalizado como hipótese, não entrega: somente RED/GREEN focal, regressão relacionada e revisão do delta; gates completos, documentação e mudança de status ficam no gate do plano, após zero critical/important;
- `plan-reviewer` ganha o eixo de espaço negativo (operação irreversível, morte do processo antes/depois, estado durável de retomada, evidência ambígua, objeto alterado entre inspeção e ação) e registra `risk_seam` em findings critical/important;
- "mudança mínima" subordinada explicitamente ao invariante: preservar coreografia comprovadamente insegura não é mudança mínima.

## 2.5.3 — Evidência vinculada ao brief e ao estado final do código

- cada evidência registrada em checkpoint é carimbada com o digest do brief atual e um fingerprint da árvore de trabalho (`HEAD` + diff + conteúdo de arquivos não rastreados);
- `finish --status completed` bloqueia evidência obsoleta: brief atualizado ou código alterado depois do registro exige reexecutar as verificações e registrar novo checkpoint;
- `--update-brief` invalida explicitamente `verification` e `evidence`, registrando o fato nos resultados;
- evidências visuais/manuais aceitam `check_id`: nova tentativa do mesmo check substitui a anterior em vez de manter uma falha antiga bloqueando.

## 2.5.2 — Evidência estruturada na execução direta

- substitui o parsing textual de evidência por registros estruturados em `checkpoint --evidence` (JSON com `kind`, `status`, `summary`, `command`/`exit_code` ou `evidence`), eliminando falsos positivos como "Found 0 errors" e falsos negativos como "exit code 1";
- `status: passed` em evidência de comando exige `exit_code: 0`; inconsistência é rejeitada na entrada;
- `checkpoint --verification passed` sem evidência aprovada registrada é bloqueado;
- `finish --status completed` usa somente a evidência estruturada salva: cada comando planejado no brief precisa da evidência mais recente aprovada ou de dispensa explícita `--waive-verification "comando: justificativa"` registrada nas limitações; evidência atual `failed`/`blocked`/`not_run` bloqueia;
- resumos das evidências atuais entram automaticamente no `RESULT.md`;
- `executar-plano` passa a entregar explicitamente o caminho do arquivo de saída ao `plan-reviewer` e ao `security-reviewer`, mantendo o relatório completo fora do contexto.

## 2.5.1 — Correções adversariais da execução direta

- evidência que relata falha (`falhou`, `failed`, `erro`, `não passou`, `timeout`, `cancelado`) não sustenta mais `--status completed`, mesmo contendo palavra de ferramenta;
- conclusão compara o `git status` com `changed_files` e bloqueia alterações não registradas; aceite explícito exige `--accept-unrecorded "caminho: justificativa"` e fica registrado nas limitações e no `RESULT.md`;
- `--blocker` passa a ser aplicado no `direct finish`; `blocked` e `escalated` exigem motivo registrado via `--blocker` ou `--limitation`;
- contratos internos passam a exigir relatório completo em arquivo e retorno curto ao orquestrador (veredito, contagem por severidade e caminho);
- cache do `repo-cartographer` ganha chave composta `<hash-do-HEAD>-<digest-do-escopo>`, evitando reutilizar cartografia de outro escopo no mesmo commit.

## 2.5.0 — Execução direta endurecida e contratos internos de subagentes

- `direct start` registra `/.superpowers/` em `.git/info/exclude` sem alterar o `.gitignore` do projeto e confirma que o scratch não aparece no `git status`;
- `direct finish --status completed` exige estado `active`, verificação `passed`, evidência reconhecida, comportamento entregue e ausência de bloqueio aberto;
- `completed`, `blocked` e `escalated` tornam-se estados terminais; escalado nunca vira concluído; `direct reopen` reabre somente `blocked` preservando o resultado anterior;
- o brief ganha digest de identidade completo; retomada com digest divergente bloqueia e pede novo slug ou `--update-brief` explícito;
- `--current-state` passa a ser obrigatório e rejeita texto genérico;
- `executar-direto` e `auditar-arquitetura` ficam restritos a invocação manual (`disable-model-invocation` e `allow_implicit_invocation: false`);
- adiciona cinco contratos internos em `skills/_shared/agents/` (repo-cartographer, implementation-worker, plan-reviewer, security-reviewer, ui-finish-reviewer), referenciados por caminho pelas skills do método completo e adaptados do Agency Agents (MIT, `THIRD_PARTY_NOTICES.md`);
- `/executar-direto` permanece com zero subagentes e sem o catálogo de contratos.

## 2.4.3 — Hardening cirúrgico de estado e planejamento

- bloqueia estado corrompido ou ambíguo sem evidência legado;
- exige prova objetiva para encerrar v1 e torna a higiene transacional;
- adapta pesquisa, risco agregado e orçamento ao contexto realmente carregado;
- centraliza os limites operacionais no resultado de `planning-audit`.

## 2.4.2 — Lean volta a ser realmente pequeno

- define uma faixa típica enxuta e teto estrito controlado pelo audit;
- reduz os demais tetos Lean proporcionalmente;
- registra warning acima da faixa típica para evitar usar o teto como meta;
- mantém escalada para Standard/Full e preservação integral do escopo.

## 2.4.1 — Preservação obrigatória do escopo aprovado

- corrige o orçamento fixo que podia incentivar adiamento automático de requisitos;
- escala capacidade de planejamento por perfil Lean, Standard e Full;
- exige preservar 100% do escopo ao escalar o perfil ou justificar pacote Full amplo;
- bloqueia `deferred_scope` sem autorização explícita do responsável, autor e horário;
- esclarece que simplicidade e economia reduzem decomposição/contexto, nunca o produto contratado.

## 2.4.0 — Pesquisa de stack e planejamento enxuto verificável

- torna obrigatória em novos ciclos a pesquisa atual da stack com fontes primárias e impacto no design;
- inclui `STACK_RESEARCH.md` no pacote de aprovação única;
- adiciona passagem explícita de simplificação que trata planos legados como fontes, não como decomposição normativa;
- introduz orçamento operacional de planos, unidades, plataformas e contexto ativo, com split ou exceção justificada;
- adiciona `planning-audit --strict` para bloquear placeholders, comandos vagos, referências legadas e unidades incompletas;
- preserva leitura e execução de estados v2 anteriores sem o novo contrato de qualidade.

## 2.3.3 — Encerramento legado com transição automática

- mantém toda fase v1 no Superpowers até gates, verificação, entrega e commit finais;
- adiciona `legacy-transition --completed` com preflight de árvore limpa e estado commitado;
- preserva o estado v1 byte a byte e cria estado v2 `idle` para o próximo escopo;
- inicia o primeiro ciclo standalone como `planning_version: v1`, sem chamada a skills Superpowers;
- mantém migração de ciclo legado ainda ativo dependente de autorização explícita.

## 2.3.2 — Migração explícita e higiene da raiz

- adiciona rota explícita e auditável de projetos v1 para v2;
- permite estado bootstrap sem planos somente durante `planning_status: in_progress`;
- proíbe arquivos rastreados sob `.superpowers/` na raiz;
- migra artefatos históricos para `docs/bianchini/legacy/root-superpowers/` preservando bytes;
- exige `/.superpowers/` no `.gitignore` versionado antes da execução v2.

## 2.3.1 — Worktree baseada no pacote aprovado

- bloqueia `workspace create` quando o repositório possui alteração não commitada;
- exige estado, snapshot, pacote e manifesto aprovados e presentes no `HEAD`;
- usa `planning_version + plan_id` na identidade de branch/worktree;
- garante por regressão que estado, plano e manifesto chegam à worktree;
- adiciona runner fragmentado por classe para ambientes com limite de subprocessos.

## 2.3.0 — Behavioral fixtures e telemetria opt-in

- transforma briefs grouped em pacotes determinísticos com ID/hash e validação do modo de cada unidade;
- adiciona telemetria local opcional para tokens, duração, fix rounds, gates e bugs de homologação;
- completa o status com gate atual e resumo da telemetria;
- adiciona fixtures completas v1, v2 grouped e v2 strict;
- executa cenários ponta a ponta de snapshot, grouped, status, telemetria e fingerprint do RC.

## 2.2.0 — Hardening standalone final

- reconhece estados v1 sem `method_version` e mantém a exigência do Superpowers legado;
- confina manifesto e arquivos do snapshot à raiz, inclusive contra symlinks de escape;
- exige fingerprint completo do RC e correspondência exata das evidências;
- adiciona briefs grouped por lista, intervalo ou heading com hashes por unidade;
- torna auditoria arquitetural manual, orientada a hotspots e report-only;
- restaura enums `architecture_audit: disabled` e `manual_pdf: none|quick_start|full|scope`;
- adiciona locate/resume de worktree, checkpoint absoluto e status estruturado completo;
- valida dependências inexistentes/cíclicas e estados de aprovação incoerentes;
- sanitiza diffs de revisão e normaliza erros de entrada/IO sem traceback;
- amplia a suíte adversarial de 28 para 42 cenários.

## 2.1.0 — Correções da auditoria externa

- restaura compatibilidade v1 estrita: Superpowers obrigatório e bloqueio quando ausente;
- adiciona `auditar-arquitetura` e `status-projeto`;
- adiciona JSON Schema e estado v2 com planning, execução, auditoria, manual e três níveis de verificação;
- implementa CLI stdlib para rota, schema, snapshot, worktree, política, briefs, relatórios, revisão e checkpoint;
- proíbe implementação v2 na branch principal ou worktree primária;
- implementa políticas `grouped`, `slice` e `strict` com revisão/testes proporcionais;
- aplica fix rounds proporcionais ao perfil com breaker determinístico;
- remove qualquer mínimo indireto de tarefas;
- torna homologação automation-first e manual/PDF dependente do escopo;
- substitui testes de strings por fixtures e cenários comportamentais executáveis.

## 2.0.1 — Auditoria adversarial

- torna o snapshot de aprovação determinístico e não autorreferente com `sha256-manifest-v1`;
- define quem registra a aprovação quando planejamento e execução ocorrem em sessões diferentes;
- elimina aprovação parcial e invalida qualquer pacote aprovado cujo manifesto mudou;
- unifica estados de release em `pending -> candidate -> homologated -> ready`;
- adiciona mapa explícito dos estados legados v1 sem reescrever projetos antigos;
- materializa escopo aprovado apenas em conversa para permitir reprodução posterior;
- reduz leitura de contexto por ponteiros e carrega referências somente na fase necessária;
- adiciona fallback inline para hosts sem invocação entre skills e evita agentes em tarefas mecânicas;
- amplia a suíte de contrato de 12 para 23 testes adversariais.

## 2.0.0 — Standalone Adaptive

- remove dependência obrigatória do Superpowers nas quatro skills;
- adiciona roteamento explícito e compatibilidade entre projetos v1 e v2;
- introduz contrato de estado v2, snapshot de aprovação única e máquina de estados de release;
- adiciona execução standalone com ledger por plano, topologia adaptativa, TDD/validation-first e revisão Spec/Qualidade;
- define gates por stack e risco com fallbacks verificáveis;
- integra correção por causa raiz ao fluxo de planos e homologação;
- completa homologação com runners por plataforma, pacote de aceite e manual PDF;
- adiciona validação automatizada do próprio pacote sem dependências de terceiros.
