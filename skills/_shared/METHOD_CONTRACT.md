# Contrato do Bianchini Method 0.4

Referência normativa das skills públicas. Use [`scripts/bm.py`](scripts/bm.py) para operações determinísticas; não replique em prompt validação, score, grafo, digest, escrita atômica ou migração.

## Workspace canônico

Todo estado persistente novo vive em `.bianchini/`:

```text
.bianchini/
├── PROJECT.md
├── STATE.md
├── current/
│   ├── ARCHITECTURE.md
│   ├── SYSTEM_MODEL.md
│   └── specs/
├── changes/C001-slug/
│   ├── SCOPE.md
│   ├── RESEARCH.md
│   ├── ARCHITECTURE.md
│   ├── SYSTEM_MODEL.md
│   ├── ROADMAP.md
│   ├── COHERENCE.md
│   ├── plans/
│   ├── results/
│   └── SUMMARY.md
├── quick/Q001-slug/
├── debug/{active,resolved}/
├── debug/KNOWLEDGE.md
├── archive/
└── .runtime/
```

`.runtime/` é ignorado pelo Git e contém somente locks, staging e recuperação de escrita interrompida. O restante é legível, versionável e confinado ao repositório.

`.planning/` é namespace estrangeiro: nunca ler como fonte do método, copiar, converter, mover, apagar ou usar como fallback. Documentação anterior do Bianchini só entra pelo fluxo explícito de migração.

## MethodWorkspace e estado

`MethodWorkspace` é a única interface para resolver caminhos, alocar IDs, escrever atomicamente e atualizar DocViva. Skills não criam estado manualmente quando existir comando equivalente.

`.bianchini/STATE.md` é o índice canônico e compacto. Seu frontmatter JSON contém somente:

- `schema_version`;
- `method`;
- `status`;
- `active_work`;
- `current_unit`;
- `blockers`;
- `next_action`;
- `last_completed`;
- `pointers`;
- `digest`;
- `updated_at`.

O arquivo deve permanecer abaixo de 64 KiB. Histórico, ledger, eventos, hipóteses, evidências e resultados pertencem a `changes/`, `quick/`, `debug/` e `archive/`; nunca acumulá-los em `STATE.md`.

Fontes de verdade:

| Informação | Fonte |
|---|---|
| índice e próximo passo | `.bianchini/STATE.md` |
| decisões e trade-offs | `ARCHITECTURE.md` |
| sistema completo | `SYSTEM_MODEL.md` |
| comportamento aceito | `.bianchini/current/specs/` |
| pacote, digest e coerência | `.bianchini/changes/Cxxx-*` |
| quick | `.bianchini/quick/Qxxx-*` |
| debug | `.bianchini/debug/active|resolved/` |
| histórico encerrado | `.bianchini/archive/` |

## ProjectModel

`ProjectModel` é uma representação tipada derivada, não outra fonte de persistência. Ele compila `SYSTEM_MODEL.md`, arquitetura atual, specs, contratos e deltas dos planos nas seções:

```text
modules interfaces capabilities contracts ownership data
integrations journeys invariants effects
```

`ARCHITECTURE.md` explica decisões, alternativas e trade-offs. `SYSTEM_MODEL.md` descreve de forma compacta como o sistema inteiro funciona. Não duplicar a mesma narrativa nos dois.

O planejamento calcula:

```text
S0 = sistema atual
S1 = S0 + delta de P01
S2 = S1 + delta de P02
...
Sn = sistema final esperado
```

`Sn` deve ser equivalente ao `SYSTEM_MODEL.md` da mudança. No fechamento aceito, esse modelo substitui `.bianchini/current/SYSTEM_MODEL.md`.

```bash
bm.py model init --repo <repo> [--change <nome-curto>]
bm.py model validate --repo <repo> [--change C001]
```

## Coerência estrutural e semântica

O pacote inteiro é validado antes da aprovação. Dependência, referência, ordem e ownership nunca ficam a cargo da interpretação da LLM.

### StructuralValidator

Determinístico e bloqueante:

- formato, IDs e referências;
- DAG e ordem topológica;
- `provides`, `consumes` e produtor ausente;
- consumidor anterior ao produtor;
- ownership incompatível;
- contrato removido antes da migração de consumidores;
- ordem e compatibilidade de migração;
- requisito sem fase, fase sem aceite ou plano sem verificação;
- journey incompleta;
- efeito externo sem guard obrigatório;
- divergência entre o modelo calculado e o modelo final.

### SemanticReviewer

Interpretativo e registrado: abstração especulativa, módulo raso, complexidade desnecessária, responsabilidade no lugar errado, incompatibilidade semântica, aderência à stack/documentação oficial e risco arquitetural omitido.

O revisor semântico normaliza um relatório; não grava raciocínio interno. Se um achado puder virar contrato ou invariante verificável, ele volta ao `StructuralValidator`. Caso contrário permanece `WARNING` ou `INFO`. Revisão indisponível nunca é declarada como executada.

```bash
bm.py coherence check --repo <repo> --change C001 --structural-only
bm.py coherence check --repo <repo> --change C001 --semantic-report <relatorio.json>
bm.py coherence approve --repo <repo> --change C001 \
  --digest <digest> --approved-by "<responsável>"
```

O check estrutural limpo retorna `structurally_valid`; ele não aprova. O check completo com revisão semântica disponível, sem `ERROR` ou `WARNING` aberto, retorna `ready_for_approval` e coloca `STATE.md` em `pending_approval`. Somente `coherence approve`, após autoridade humana explícita, pode gravar o checkpoint e mudar o estado para `approved`. O comando revalida o digest e registra responsável e horário; não executar em nome do responsável.

Cada finding contém código, severidade, origem, planos/contratos afetados, evidência, correção esperada e status.

| Severidade | Efeito |
|---|---|
| `ERROR` | bloqueia planejamento, snapshot ou execução |
| `WARNING` | exige correção ou justificativa humana incluída no digest |
| `INFO` | observação sem ação obrigatória |

Status válidos: `open`, `resolved`, `accepted_with_justification`. `WARNING` aberto impede aprovação.

## Planejamento global

Fluxo obrigatório:

```text
estado atual
→ pesquisa da stack e fontes oficiais proporcionais
→ arquitetura global
→ SYSTEM_MODEL final
→ roadmap de todas as fases
→ planos detalhados
→ validação estrutural
→ impact radius
→ revisão semântica conjunta
→ resolução dos findings
→ aprovação do digest global
```

Cada plano `Pxx` declara resultado, aceite, `depends_on`, `provides`, `consumes`, módulos/interfaces, ownership, delta do ProjectModel, dados/migrações, efeitos externos, rollback, verificações e restrições futuras.

O pacote aprovado é imutável. Detalhe interno reversível continua. Mudança em contrato, ownership, dado, migração, journey ou invariante recalcula o impacto e torna somente os planos afetados `stale`.

## Impact radius

```text
contrato alterado
→ consumidores diretos
→ consumidores transitivos
→ jornadas afetadas
→ planos afetados
→ verificações a repetir
```

Classificação:

- `local`: somente o plano atual;
- `direct`: plano e consumidores diretos;
- `transitive`: toda a cadeia de consumidores;
- `global`: modelo, invariante central ou ownership global.

O resultado fica na seção `Impact Radius` de `COHERENCE.md`. Antes da aprovação,
ele é somente uma prévia e não grava planos `stale`. Depois da aprovação, planos
atingidos ficam `stale`, o status passa a `approved_with_stale` e o digest humano
original é preservado. Planos independentes continuam executáveis. Nova auditoria
e nova aprovação produzem o próximo digest global.

```bash
bm.py impact analyze --repo <repo> --change C001 --plan P03 \
  [--changed-contract <id> ...]
```

## Execução de planos

Antes de editar código:

1. validar `STATE.md`, digest e modelo sem reexecutar uma auditoria mutável;
2. confirmar plano aprovado, não `stale` e dependências concluídas;
3. reconstruir o modelo atual e confirmar contratos consumidos;
4. exigir Git limpo e criar o workspace isolado pelo CLI:

```bash
bm.py workspace create --repo <repo> --change C001 --plan P01
```

O gate exige `COHERENCE.md` em `approved` ou `approved_with_stale`, artefatos do pacote idênticos ao `HEAD` e o plano solicitado fora da lista `stale`. O segundo
status autoriza somente planos independentes que preservaram aprovação.
`coherence check` e `impact analyze` atualizam `COHERENCE.md`; não usá-los como
consultas de preflight. O workspace fica fora de `main`, `master`, detached HEAD e
worktree primária.

O plano aprovado continua congelado. A ordem autônoma é:

```text
decisão aprovada
→ padrão do repositório
→ stack/dependência existente
→ documentação oficial
→ opção reversível de menor risco
```

Detalhe interno ou ajuste limitado é registrado. Mudança material recalcula o impacto e replaneja somente o fechamento afetado. Custo ou efeito irreversível pausa para autoridade; não implica redesign por si só.

Após cada plano, registrar o delta real, comparar `provides/consumes`, aplicar ao modelo, recalcular impacto, repetir integrações afetadas e atualizar `STATE.md`. Existência isolada de endpoint, tabela ou tela não prova integração.

```bash
bm.py plan complete --repo <repo> --change C001 --plan P01 \
  --actual-delta <delta-real.json> \
  --result "<resultado entregue>" \
  --verification "<evidência vigente>"
```

O comando exige dependências concluídas, contratos consumidos presentes, delta real equivalente ao aprovado e evidência. Drift material retorna `IMPACT_STALE` para replanejamento; não altera silenciosamente o pacote.

## Gates adaptativos

| Risco | Execução | Revisão | Testes |
|---|---|---|---|
| baixo | `grouped` | gate do plano | unitário/contrato/regressão focados |
| médio | `slice` | por slice | comportamento vertical + gate afetado |
| alto/crítico | `strict` | por tarefa | RED/GREEN e revisão independente |

- `verification.fast`: prova focal da unidade;
- `verification.plan`: suítes afetadas, regressão do plano, E2E crítico e mutação seletiva exigida;
- `verification.release`: comandos completos aprovados, contratos, regressão, E2E, build e evidência de mutação vigente.

Regressão é transversal. Não criar tarefa ou agente por camada de teste. Não perseguir coverage ou mutation score global. Finding estrutural, crash window, partial commit, TOCTOU, retry ambíguo, idempotência concorrente ou recuperação após restart invalida a hipótese e exige redesenho do seam antes de novo patch.

O breaker epistêmico é contado por `risk_seam`, não pelo nome da tarefa: renomear, dividir ou reordenar a tarefa não zera a contagem do mesmo seam. Dois findings estruturais consecutivos no mesmo seam exigem parar o fix loop e redesenhar o contrato. Para concorrência, persistência ou integração externa, revise explicitamente máquina de estados, matriz de falhas e a janela entre inspeção e ação. Um patch menor que mantém crash window, TOCTOU ou perda silenciosa não é mudança mínima aceitável.

### Contratos internos

- `repo-cartographer` é somente leitura e só entra em brownfield grande/desconhecido; não usar em projeto novo ou pequeno. O cache combina hash do `HEAD` e digest do escopo.
- `implementation-worker` recebe contrato, brief, modelo necessário e caminho do relatório; não propõe refatoração fora do plano.
- `plan-reviewer`: uma revisão no gate em `grouped`, uma por slice em `slice` e independente por tarefa em `strict`. Retorna contagem por severidade e caminho do arquivo de saída da revisão.
- `security-reviewer` roda somente em risco alto ou crítico sensível, em passagem somente leitura. Não roda em tarefa comum e devolve findings ao fix loop existente.
- Quick usa zero subagentes e não carrega esse catálogo.

## Quick

`/executar-direto` classifica uma entrega coesa antes de editar:

```text
risk = scope + external_effect + migration + concurrency + money
```

Cada dimensão vale `0..2`:

- `0–2`: quick normal;
- `3–6`: quick protegido;
- `7–10`: planejamento.

Overrides obrigatórios para planejamento: `scope=2`, migração destrutiva, concorrência não controlada, ownership indefinido, regra financeira ambígua, arquitetura material nova ou várias entregas independentes.

```bash
bm.py direct classify --repo <repo> \
  --scope-score <0..2> \
  --external-effect-score <0..2> \
  --migration-score <0..2> \
  --concurrency-score <0..2> \
  --money-score <0..2> \
  [--multiple-objectives | --destructive-migration | --uncontrolled-concurrency] \
  [--undefined-ownership | --ambiguous-financial-rule | --new-material-architecture]
```

Pagamento e webhook não escalam pela palavra. Quick protegido exige guards aplicáveis: documentação oficial, origem de verdade, idempotência, autenticidade, deduplicação, replay/ordem, timeout incerto, persistência, reconciliação, rollback, sandbox e checkpoint de produção. Cobrança real, refund, operação paga, ativação externa ou efeito irreversível exige autoridade explícita no momento do efeito.

`direct start` persiste `BRIEF.md`, `PROGRESS.md` e `RESULT.md` em `.bianchini/quick/Qxxx-*`; score, overrides e digest fazem parte do brief. Evidência fica vinculada ao digest e ao fingerprint final. Conclusão atualiza `STATE.md` e a spec/modelo afetados.

## Debug persistente

```text
intake → reproduced → diagnosed → red → fixing → green
→ regression_checked → documented → resolved | blocked | escalated
```

```bash
bm.py debug start|list|status|resume|checkpoint|finish --repo <repo> ...
```

Cada `Dxxx` registra esperado/real, ambiente, reprodução, hipóteses e contraprovas, causa, RED, GREEN, regressões vizinhas, risco residual e referência opcional comprovada a `Cxxx/Pxx` com relação `caused_by`, `detected_in` ou `regression_of`.

GREEN antes de RED é inválido. Quando automação não for possível, usar procedimento manual determinístico. Evidência anterior ao último patch fica obsoleta. Debug resolvido vai para `debug/resolved/`; somente padrões causais reutilizáveis vão para `KNOWLEDGE.md`.

Bug que restaura contrato aceito não muda spec. Contrato errado exige decisão e impact radius.

## Migração explícita

Não existe adaptador permanente. Projetos anteriores terminam no fluxo em que estão e depois executam:

```bash
bm.py migrate check --repo <repo>
bm.py migrate apply --repo <repo>
```

`check` é somente leitura. `apply` exige projeto `idle`/concluído e Git limpo, usa mapa origem→destino, SHA-256, staging transacional e rollback. Reconhece somente documentação anterior do Bianchini em `docs/living`, `docs/bianchini`, `artifacts/bianchini`, documentos Bianchini identificáveis em `docs/design` e resultados em `.superpowers/bianchini/direct`.

Colisão, formato desconhecido, symlink externo, path traversal, checksum divergente ou ciclo ativo bloqueiam. A origem só é removida após verificar o destino. O manifesto fica em `.bianchini/archive/import-AAAA-MM-DD/`. `.planning/` permanece byte a byte intocado.

## Encerramento e DocViva

Toda tarefa terminal atualiza `STATE.md` atomicamente. O fechamento exige modelo final equivalente, jornadas ponta a ponta, gates de release, homologação e revisão final aplicáveis. Então sincroniza specs/modelo atuais e move a mudança para `archive/`.

```bash
bm.py cycle-close --repo <repo> --change C001
```

Relatar separadamente: código/commit, testes, sandbox, deploy, efeito em produção/provedor e homologação humana. Um limite não comprova o seguinte.

## Atualização e segurança

`/update-bm` permanece manual. A transição para `0.4.0` usa o manifesto oficial de mudança de linhagem uma única vez; depois retorna à comparação semântica normal.

Sem autorização explícita, não cobrar, publicar, enviar mensagem real, apagar dados, executar migração destrutiva, alterar produção de forma arriscada ou expor segredo/dado pessoal. Nunca versionar credenciais, payloads sensíveis, logs grandes ou artefatos temporários.
