# Changelog

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
- aplica fix rounds Lean 2, Standard 3 e Full 5 com breaker determinístico;
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
