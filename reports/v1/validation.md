# Validação do candidato 1.0

Continuação: [correção e verificação da compatibilidade no CI](ci-followup.md).

Data: 2026-09-05. Repositório: `felipebianchini2006/bianchini-method`.
Branch: `feat/v1.0-autonomous-verified-workflow`, criada a partir de `main`.
Commit inicial: `930ee8fd01ebba62bdd60c30cd8a2daab321effe`.
Versão inicial: `0.6.0`; executável preparado: `1.0.0`, sem tag definitiva. O commit final é o HEAD desta branch/PR.

## Preparação e baseline

As instruções do usuário foram aplicadas. Não havia AGENTS.md adicional nos diretórios consultados. A única entrada preexistente sem rastreio, `bin/`, foi preservada. Os três artefatos da auditoria anterior não foram encontrados; as falhas foram reproduzidas no código atual.

Baseline Go: `go test ./...` passou, núcleo em 21,551 s e ferramenta de release em 4,053 s. Baseline Python: 39 shards passaram em cópia isolada do commit inicial. Uma primeira execução simultânea ao desenvolvimento foi descartada como baseline; o resultado considerado veio da cópia intacta.

Não houve mudança de dependências para obter testes verdes. Ambiente local: macOS arm64, Go 1.24.13, Python 3.13.13. CI continua usando Go conforme `go.mod` e Python 3.13.

## Resultado final local

| Verificação | Resultado |
|---|---|
| `go test ./...` | Passou; núcleo 25,517 s, ferramenta de release 2,579 s |
| `go vet ./...` | Passou |
| Shards Python, CLI e jornada oficial Go | 39 grupos verdes; 357 testes executados, 1 repetição da suíte Go dispensada explicitamente |
| Jornada pública `FullJourneyScenarios` | Passou no backend Go, incluindo schema 1 e schema 2 |
| Imagem real Docker | Passou: imagem construída sem download, inspecionada, smoke pelo ID imutável, hash incorreto e imagem ausente rejeitados; imagem removida |
| Deployment local HTTP | Passou: versão observada aceita; versão alterada e alvo indisponível rejeitados |
| Revisão independente focal | Cinco regressões + cache + resolução de findings passaram; sem finding material pendente |
| Exemplo real com PDF e parecer independente | Passou; 44 chamadas públicas, 9 rejeições controladas |
| Exemplo reproduzível `--protocol-test` | Passou; parecer identificado explicitamente como fixture, sem alegação de independência |
| PDFs de entrada | Original e PDF gerado pelo script renderizados e inspecionados; texto legível, sem cortes |

Os shards foram retomados a partir dos grupos que falharam, sem repetir grupos já aprovados no mesmo estado. O registro por grupo está em [suite-results.json](suite-results.json). A execução completa reproduzível está em [workflow-v1.md](../../docs/workflow-v1.md).

Falhas introduzidas durante o trabalho e corrigidas: expectativas antigas de versão, fixtures narrativas incompatíveis com Go, referência documental ausente, contrato textual do revisor, fixture de decisão técnica na etapa incorreta, limite esperado antes da última rodada permitida e snapshot de métricas desatualizado. O relatório de métricas foi regenerado pelo script oficial; limites e baseline não foram relaxados. Nenhuma falha local conhecida permanece aberta.

## Falhas reproduzidas e proteções

O registro RED inicial está em [regressions.txt](regressions.txt). Os testes falharam antes da correção pelos comportamentos esperados: aceitação de gates omitidos, cache de passe após mudança externa, obrigação indevida de review individual em grouped, quick narrativo, RED narrativo, homologação incompleta e resolução fictícia.

| Risco | Cobertura final |
|---|---|
| Dois gates, um falha; apresentar só o passe | `TestMandatoryPlanGateCannotBeOmitted` e jornada real rejeitam fechamento |
| Gate nunca executado; revisão sem cobertura | Mesmo teste exige conjunto completo inclusive para revisão |
| Outro comando, unidade ou quick | `TestProofForDifferentCommandCannotCoverGate`, `TestQuickRejectsForeignAndStaleProofs` |
| Código mudou; revisão ou prova ficou obsoleta | `TestProofAndReviewBecomeStaleAfterCodeChanges`; jornada rejeita prova anterior à permissão alterada |
| Passe anterior a falha posterior | `TestReviewQuickRejectsLatestFailedRun` |
| Accepted com not_run, failed, N/A, falta de gate ou candidato errado | `TestTypedLifecycleRequiresProofReviewReleaseAndHomologation` |
| Critical/high ou blocking aberto, mesmo com blockers vazio | Lifecycle do release e jornada real |
| Resolução inventada ou evidência alterada | `TestHomologationRejectsFictitiousResolution` e sondagem independente de bytes, vazio e escapes |
| Artefato inexistente, hash arbitrário ou bytes modificados | Lifecycle de release; tipos file, container e deployment exercitados |
| Quick sem execução, comando inexistente ou falho | `TestQuickRejectsUnexecutedAndFailedCommands`; nenhum resultado terminal escrito |
| RED/GREEN narrativos ou falha de importação | `TestDebugRejectsNarrativeRed`, `TestDebugLifecycleMatchesFrozenSuccess`, `TestReviewRedRejectsMissingPythonDependency` |
| Estado externo mudou sem mudança de fonte | `TestExternalVerificationDoesNotReusePass`; cache determinístico continua testado separadamente |
| Grouped/strict/slice divergentes | Grouped conclui tarefa sem review individual, exige review no plano; strict/slice exigem review da tarefa vertical |
| Finding concreto sem RED artificial | `TestConcreteInspectionFindingDoesNotNeedArtificialRed`; finding vago rejeitado |
| Renomeação ou passe de outro gate reinicia orçamento | `TestFixLimitSurvivesRenamingUnitAndChangingCode`, `TestReviewFixLimitCannotBeBypassedByPassingOtherGate` |
| Segredo em saída JSON | `TestReviewSanitizeJSONSecret` |

A exigência de `--proof` em schema 2 já existia. Foi preservada; a jornada antiga foi corrigida para usar o contrato público em vez de enfraquecer o Go.

## Jornada do produto de exemplo

O planejamento escolheu Python, argparse e SQLite porque a demonstração pede CLI local persistente, sem autenticação de produção nem serviços. Go, TypeScript ou arquitetura distribuída não são regras do método. Pesquisa primária: documentação de [sqlite3](https://docs.python.org/3/library/sqlite3.html) e [argparse](https://docs.python.org/3/library/argparse.html). A decisão e as premissas são registradas em RESEARCH/ARCHITECTURE dentro do projeto descartável.

Foi usada uma entrega vertical proporcional: criar, listar como operador, atualizar, consultar como dono, rejeitar acesso alheio e entrada inválida. Cada comando roda em processo novo; SQLite preserva o registro. O exemplo não simula servidor ou autenticação real.

Etapas executadas: PDF de entrada → escopo canônico conferido → `scope seal/verify` → specs compactas → `roadmap sync` gerando manifesto/diff → coerência estrutural e parecer → decisão técnica com `--decided-by` → execução e provas focais → reconstrução do estado em processos CLI novos → gates integrados e revisão → candidato `.pyz` → testes sobre o artefato → homologação → `cycle-close`. O estado voltou a idle após quick e debug.

A revisão independente operou tanto o fonte quanto o `.pyz`, inclusive com o fonte desabilitado. Também injetou falha transacional SQLite e verificou preservação do registro. O mesmo parecer cobre o produto e o artefato; não houve campanha independente redundante a cada transição.

Candidato da execução real: `RC-a69ded4889a6`.
SHA-256: `a989d2cdafdd748c21375e621ee297fd2214c4dfe182d78a49102257d119112f`.
PDF original: `c12d3a30a7812727a9b18457dd5974bfc82eb4ec9a3e09b334549262043afd45`.

As nove rejeições públicas foram: prova obsoleta, teste de permissão falhando, estado externo falhando, prova faltante, revisão de plano ausente, homologação not_run, finding critical aberto, finding high aberto e candidato modificado. Após restaurar o contrato, a jornada concluiu. A alteração pequena passou pelo quick; o debug introduziu uma regressão de espaços na descrição, registrou RED real e GREEN do mesmo teste após restaurar a normalização.

Evidências: [chamadas públicas](service-journey.json), [parecer do produto](service-review.json), [revisão do núcleo](core-review-final.md). Caminhos locais foram substituídos por `<checkout>` e `<validation-temp>` nos relatórios; hashes foram preservados. PDF bruto, banco, binários e repositórios descartáveis não são versionados.

## Compatibilidade, limites e publicação

- Python continua como oráculo explícito; não é fallback do Go. As fixtures narrativas antigas de quick/debug são marcadas Python-only, com migração documentada e testes Go reais substitutos.
- A linhagem de estado `0.4` e schema 1 são preservados. Pacotes schema 2 antigos exigem novas provas e homologação conforme os campos atuais.
- A retomada foi demonstrada por processos CLI independentes reconstruindo estado persistido. Não foi simulada restauração de conversa em todos os hosts de agentes.
- Docker foi exercitado localmente. Deployment foi testado em endpoint HTTP local, não em provedor público. Não houve deploy em produção, pagamentos ou dados pessoais.
- A demonstração usa identidades sintéticas públicas. Não é um produto pronto para autenticação na internet; concorrência extrema e perda de energia não foram certificadas.
- Identidade e hash comprovam correspondência dos bytes; adequação semântica do teste e do finding continua sendo responsabilidade da revisão.
- Classificação de infraestrutura em RED e sanitização usam padrões conhecidos. Não há promessa de reconhecimento universal nem de ausência absoluta de bugs.
- CI remoto é distinto dos testes locais e deve ser consultado no PR. Publicação definitiva continua dependendo de autorização; nenhuma tag ou merge é parte desta tarefa.
