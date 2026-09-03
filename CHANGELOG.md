# Changelog

O histórico foi consolidado na linhagem pública `0.x`. Os detalhes operacionais anteriores permanecem abaixo, agrupados pelo marco em que passaram a formar uma capacidade estável do método.

## 0.6.0 — Conclusão baseada em evidência

- torna `bm verify task|plan|release|review|status` a autoridade de prova e revisão do backend Go;
- exige proofs verdes e reviews aprovadas do mesmo fingerprint para concluir tarefas e planos schema 2;
- executa comandos por `argv` sem shell, registra ambiente, digests, exit code e invalida evidência alterada ou obsoleta;
- persiste falhas e exige motivo para retry no mesmo estado, evitando loops automáticos;
- reabre tarefa/plano explicitamente e preserva auditoria da conclusão anterior;
- exige release final revisado e homologação aceita do RC exato antes do archive;
- usa checkout primário no trabalho solo e deixa worktree para isolamento real;
- adiciona limpeza segura de worktrees e branches já integradas;
- transforma o executor Codex em alias do executor canônico, sem segunda autoridade de `completed`;
- remove o limite arbitrário de três blockers do guard legado.

## 0.4.6 — Fases e tarefas tipadas

- adiciona `planning_contract: 2` para mudanças novas, preservando mudanças anteriores no contrato 1;
- estrutura cada fase `Pxx` com requisitos rastreáveis e tarefas `Txx` executáveis, verificáveis e fail-closed;
- valida cobertura `SCOPE → fase → tarefa`, dependências, ciclos, ordem, referências de modelo, paths e compatibilidade entre modo e revisão;
- deriva `ROADMAP.md` e ondas topológicas de fases/tarefas pelo CLI;
- vincula a revisão semântica ao manifesto completo dos artefatos;
- bloqueia aprovação, workspace, conclusão e fechamento quando o pacote aprovado sofre drift;
- exige comprovação explícita de todas as tarefas para concluir uma fase.

## 0.4.5 — Intake de escopo em PDF

- adiciona `/preparar-escopo` para converter PDF textual, escaneado ou misto em `SCOPE.md` estruturado;
- exige rastreabilidade por página, aceite testável e fechamento de ambiguidades antes do selo;
- adiciona `scope seal` e `scope verify` com digest da fonte, cobertura e escrita atômica;
- faz o `sdd-planning` reutilizar o escopo selado e bloquear alterações posteriores;
- preserva `.planning/` e mantém PDF, extrações e OCR fora do Git.

## 0.4.4 — Subagentes adaptativos na execução direta

- permite subagentes em quick normal e protegido quando existirem frentes independentes;
- preserva o executor principal como responsável por integração, evidência e conclusão;
- usa os padrões atuais do host sem fixar modelo, quantidade, hierarquia ou paralelismo;
- proíbe decomposição artificial por arquivo, camada de teste ou gate mecânico.

## 0.4.3 — Execução direta sem replanejamento automático

- torna a invocação explícita de `/executar-direto` uma decisão definitiva de roteamento;
- mantém scores `3–10` e sinais críticos no quick protegido, com guards e evidências proporcionais;
- remove a saída automática ou manual `escalated` dos quicks novos;
- usa planos, specs e decisões em `.bianchini/` como documentação e rastreio, sem exigir novo `/sdd-planning`;
- preserva bloqueios reais de autoridade, informação e efeitos externos, sem tratar complexidade como bloqueio.

## 0.4.2 — Aposentadoria dos adaptadores antigos

- remove da interface pública `route`, `legacy-transition` e `repo-hygiene`;
- torna `/migrar-bianchini` e `bm migrate` o único caminho de entrada para artefatos anteriores reconhecidos;
- substitui os cenários antigos de roteamento por regressões que exigem rejeição sem escrita parcial;
- mantém `.planning/` fora de qualquer leitura, conversão, cópia, movimento ou remoção.

## 0.4.1 — Entrada 0.4 sem fallback legado

- inicializa `.bianchini` automaticamente no primeiro quick ou debug de projeto novo;
- exige `/migrar-bianchini` quando qualquer fonte anterior reconhecida estiver presente;
- remove o fallback automático de `direct`, `workspace` e `cycle-close` para fluxos anteriores;
- remove argumentos públicos antigos desses comandos para impedir ativação acidental;
- adiciona regressões que proíbem escrita em `.superpowers`, `docs/living` e `.planning` pelos fluxos novos;
- valida o pacote instalado em cópia limpa, além do checkout de desenvolvimento.

## 0.4.0 — ProjectModel e coerência global

### Workspace e DocViva

- centraliza todo estado novo em `.bianchini/`;
- transforma `STATE.md` em índice compacto com limite de 64 KiB;
- separa estado atual, mudanças, quicks, debugs, resultados e arquivo histórico;
- adiciona `MethodWorkspace` para caminhos confinados, IDs, escrita atômica, digests e transações;
- mantém `.planning/` totalmente separado e byte a byte intocado;
- remove do fluxo novo roteamento por geração e contrato `quality_version`.

### Modelo do sistema

- adiciona `ProjectModel` tipado com módulos, interfaces, capabilities, contratos, ownership, dados, integrações, journeys, invariantes e efeitos;
- adiciona `SYSTEM_MODEL.md` como representação compacta do sistema completo;
- mantém decisões, alternativas e trade-offs em `ARCHITECTURE.md`;
- simula `S0 → S1 → ... → Sn` pelos deltas dos planos;
- bloqueia fechamento quando o modelo calculado diverge do modelo final esperado;
- promove o modelo aprovado para `.bianchini/current/SYSTEM_MODEL.md` no encerramento.

### Coerência entre fases

- separa `StructuralValidator` determinístico de `SemanticReviewer` interpretativo;
- valida IDs, referências, DAG, `provides/consumes`, ordem, ownership, migração, journeys e guards externos sem depender de LLM;
- revisa abstração especulativa, profundidade, complexidade, responsabilidade e aderência à stack na camada semântica;
- adiciona findings `ERROR`, `WARNING` e `INFO` com origem, evidência, correção e status;
- exige correção ou justificativa humana de `WARNING` antes da aprovação;
- registra prompt, entradas, fontes e digest do parecer sem armazenar raciocínio interno;
- separa os estados `structurally_valid`, `ready_for_approval` e `approved`;
- adiciona `coherence approve` como único checkpoint capaz de gravar responsável, horário e digest aprovado;
- impede que revisão semântica indisponível ou autoridade presumida produzam falso passe;
- executa auditoria depois da arquitetura, depois dos planos, antes/depois de cada plano e no fechamento.

### Impact radius

- adiciona grafo de consumidores diretos e transitivos;
- classifica mudanças em `local`, `direct`, `transitive` e `global`;
- relaciona contrato alterado, journeys, planos e gates a repetir;
- marca somente planos realmente atingidos como `stale`;
- preserva aprovação de planos independentes;
- usa prévia sem invalidação antes da aprovação e `approved_with_stale` depois;
- preserva o digest humano até uma nova auditoria e aprovação explícita;
- registra o resultado em `COHERENCE.md` sem criar nova fonte documental.

### Quick protegido

- substitui hazards por palavra por score `scope + external_effect + migration + concurrency + money`;
- roteia `0–2` para quick normal, `3–6` para protegido e `7–10` para planejamento;
- aplica overrides determinísticos para múltiplos domínios, migração destrutiva, concorrência sem solução, ownership indefinido, regra financeira ambígua e arquitetura nova;
- permite pagamento e webhook coesos como quick protegido;
- exige guards proporcionais de idempotência, autenticidade, deduplicação, replay, ordem, timeout incerto, persistência, reconciliação e rollback;
- mantém efeitos financeiros/irreversíveis reais atrás de checkpoint explícito;
- passa a versionar `BRIEF.md`, `PROGRESS.md` e `RESULT.md` em `.bianchini/quick/Qxxx-*`;
- atualiza DocViva e specs/modelo afetados ao finalizar.

### Debug persistente

- adiciona `debug start|list|status|resume|checkpoint|finish`;
- persiste `intake → reproduced → diagnosed → red → fixing → green → regression_checked → documented`;
- rejeita GREEN anterior ao RED e evidência anterior ao último patch;
- preserva hipóteses eliminadas, contraprovas, causa raiz e regressões;
- aceita reprodução manual determinística quando automação não for viável;
- permite referência comprovada `Dxxx → Cxxx/Pxx`;
- move casos resolvidos para `debug/resolved/`;
- mantém somente padrões causais reutilizáveis em `KNOWLEDGE.md`.

### Migração e numeração

- adiciona `/migrar-bianchini` e `migrate check|apply`;
- migra uma única vez documentação anterior reconhecida, sem adaptador permanente;
- exige projeto concluído/`idle`, Git limpo, mapa origem→destino e SHA-256;
- preserva histórico Git, usa staging transacional e executa rollback em falha;
- bloqueia formato desconhecido, colisão, symlink externo, path traversal e checksum divergente;
- cria manifesto em `.bianchini/archive/import-AAAA-MM-DD/`;
- reinicia a linhagem pública em `0.4.0`, reservando `1.0` para contrato estável;
- aceita uma única transição oficial da numeração anterior e depois restaura comparação semântica normal.

## 0.3 — Estabilidade, contexto e atualização

### Planejamento e design

- adicionou `/design-projeto` para produzir protótipo HTML estático, tokens, contrato e manifesto visual antes do planejamento;
- vinculou design aprovado ao digest do escopo e rejeitou screenshots/protótipos soltos;
- introduziu readiness com decisões, suposições, pitfalls, ações externas, spikes, superfícies visuais e specs de domínio;
- passou a exigir fontes primárias em pesquisa sensível a versão;
- limitou a revisão semântica a uma correção factual antes do bloqueio;
- congelou planos aprovados e separou detalhe interno, ajuste limitado e mudança material;
- ampliou autonomia para decisões reversíveis cobertas por stack, repositório e documentação oficial;
- introduziu specs atuais e deltas completos de domínio, sincronizados somente no fechamento.

### Economia de contexto

- adicionou `Change` e referências de readiness por unidade;
- criou `task-brief --hydrate-context` com somente specs, decisões, gates e ledger aplicáveis;
- criou `spec-diff` como projeção ADDED/MODIFIED/REMOVED ligada aos digests das specs completas;
- criou `mutation-evidence verify` ligado ao HEAD/fingerprint do RC;
- preservou fontes completas e evitou transformações derivadas como nova fonte de verdade;
- adicionou CI versionada e runner fragmentado por classe.

### Atualização segura

- adicionou `/update-bm` e `update-bm --check`;
- passou a consultar a versão oficial somente sob invocação explícita;
- preservou skills alheias ao substituir apenas diretórios gerenciados;
- criou backup persistente e rollback de substituição;
- bloqueou archive com path traversal, symlink, arquivo especial, entrada duplicada ou versão divergente;
- em checkout Git, exigiu origem oficial, branch principal limpa e fast-forward;
- impediu downgrade silencioso.

## 0.2 — Execução segura e gates adaptativos

### Planejamento enxuto

- tornou obrigatória a pesquisa proporcional da stack;
- introduziu modos `repo_only`, `targeted_web` e `full`;
- adicionou `planning-audit --strict` contra placeholders, comandos vagos e dependência de fontes transitórias;
- criou orçamentos de contexto como tetos, nunca metas ou motivo para retirar requisito;
- bloqueou `deferred_scope` sem autorização explícita, responsável e horário;
- consolidou setup, lint, docs e baseline na primeira entrega que os consome.

### Execução direta

- adicionou `/executar-direto` como fluxo manual para entrega coesa;
- criou brief, progresso e resultado com digest de identidade;
- exigiu estado atual factual, aceite e comandos planejados;
- tornou `completed`, `blocked` e `escalated` estados terminais;
- permitiu reabrir somente trabalho bloqueado, preservando resultado anterior;
- passou a registrar evidência estruturada de comando, browser, screenshot ou procedimento manual;
- vinculou evidência ao digest do brief e ao fingerprint final da árvore;
- invalidou evidência após mudança de brief ou código;
- exigiu `exit_code: 0` para comando aprovado;
- bloqueou alterações fora dos arquivos registrados;
- endureceu mensagens que continham termos de sucesso, mas relatavam falha real;
- manteve branch isolada e proibiu scratch rastreado.

### Testes e homologação

- distribuiu unitários, integração/contrato, E2E, regressão e mutação entre gates `fast`, `plan` e `release`;
- tornou regressão uma estratégia transversal, sem tarefa ou agente por camada;
- reservou E2E crítico e mutação seletiva para gates proporcionais;
- rejeitou mutation score global como meta;
- passou a bloquear survivor somente quando ele demonstra comportamento material desprotegido;
- exigiu operar o RC real por plataforma/perfil depois da automação;
- adicionou inventário de superfícies, sucesso, erro, cancelamento, recuperação e persistência;
- tornou a varredura visual básica obrigatória quando houver interface;
- amarrou provas ao fingerprint `id + revision + build + checksum`.

### Breaker e correção

- passou a contar fix rounds por `risk_seam`, sem reset por renomear tarefa;
- antecipou breaker após findings críticos/importantes consecutivos no mesmo seam;
- classificou crash window, partial commit, TOCTOU, efeito externo antes de persistência, retry ambíguo, idempotência concorrente e recuperação após restart como achados estruturais;
- exigiu máquina de estados, limites transacionais, estado durável e matriz de falhas antes de novo patch;
- manteve fix round como hipótese RED/GREEN, não como entrega completa;
- subordinou mudança mínima ao invariante correto.

## 0.1 — Fundação standalone

### Estado, aprovação e execução

- removeu dependência obrigatória de metodologia externa no fluxo principal;
- criou contrato de estado validável e máquina de estados de release;
- introduziu snapshot de aprovação única com manifesto SHA-256 ordenado e não autorreferente;
- bloqueou aprovação parcial e invalidou pacote alterado após aprovação;
- criou worktree obrigatória por ciclo/plano, fora da branch principal e da worktree primária;
- exigiu estado, plano, snapshot e manifesto commitados antes da implementação;
- adicionou briefs, relatórios, review packages e checkpoints determinísticos;
- implementou políticas `grouped`, `slice` e `strict` sem quantidade mínima de tarefas;
- adicionou revisão de contrato e qualidade proporcional ao risco;
- integrou correção por causa raiz, regressão e reteste ao fluxo;
- criou encerramento com specs sincronizadas, archive e estado ocioso.

### Segurança e confiabilidade

- confinou caminhos, manifestos e artefatos à raiz do projeto, inclusive contra symlink;
- normalizou erros de entrada e IO sem traceback desnecessário;
- bloqueou dependências ausentes/cíclicas e estados de aprovação incoerentes;
- sanitizou diffs entregues a revisores;
- criou fingerprint obrigatório do release candidate;
- tornou telemetria local opt-in e limitada a métricas numéricas;
- proibiu prompts, código, diffs, segredos e dados pessoais na telemetria;
- adicionou auditoria arquitetural manual orientada a hotspots e sem mutação;
- introduziu contratos internos enxutos para cartografia, implementação, revisão e segurança;
- manteve homologação real e validação visual como responsabilidade explícita do método.
