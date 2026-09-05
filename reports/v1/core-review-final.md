# Revisão independente final do núcleo

Revisor: agent:critical_review.
Data UTC: 2026-09-05T11:45:42.622742+00:00.
Base Git: 930ee8fd01ebba62bdd60c30cd8a2daab321effe, com alterações locais de implementação.

## Resultado

As cinco falhas materiais anteriormente reproduzidas foram corrigidas nos cenários testados. As cinco regressões passaram. Dois testes focais adicionais de cache também passaram. Não encontrei nova brecha material concreta nesta revisão final concentrada.

- Quick rejeita fechamento após execução posterior falha do gate.
- Grouped rejeita tarefa com finding crítico aberto, mesmo sem revisão individual obrigatória.
- Sanitização remove os valores secretos da saída JSON exercitada.
- Passe de outro gate não elimina falha pendente nem permite exceder o limite de correções da seam.
- Falha de importação de dependência Python não é aceita como RED.

## Comandos e resultados

Executados no repositório, com TMPDIR apontando para diretório exclusivo criado por mktemp -d sob /Users/felipebianchini/Developer:

```sh
go test ./internal/gokernel -run '^TestReview(QuickRejectsLatestFailedRun|GroupedRejectsOpenTaskFinding|SanitizeJSONSecret|FixLimitCannotBeBypassedByPassingOtherGate|RedRejectsMissingPythonDependency)$' -count=1 -v
```

Resultado: cinco testes passaram; pacote em 1,514s.

```sh
go test ./internal/gokernel -run '^(TestExternalVerificationDoesNotReusePass|TestVerifyTaskExecutesStructuredCommandAndReusesPassingProof)$' -count=1 -v
```

Resultado: dois testes passaram; pacote em 0,812s. O estado externo modificado não reaproveitou passe; o caso determinístico preservou o cache.

## Inspeção focal

verificationAttemptPolicy mantém falhas por argv/cwd/kind e usa o maior contador registrado da seam. executeVerification considera somente a última prova equivalente no reaproveitamento determinístico; matchingVerificationProofs ordena por attempt. executeDebugProof rejeita marcadores de importação/carregamento/build/runner, além de timeout e spawn error. Quick/debug consultam falhas posteriores; fechamento consulta pendências de revisão separadamente da granularidade de review.

## Limites reais

- Não executei suíte global, teste de corrida, Docker ou deployment nesta revisão final.
- A rejeição de infraestrutura em RED usa marcadores conhecidos; não demonstra classificação universal de todos os runners e idiomas.
- A sanitização foi demonstrada para os casos exercitados; isso não prova ausência de todo formato possível de segredo em logs.
- A seleção de cache determinístico depende do contrato de entradas controladas declarado para a verificação.
- Esta revisão não certifica correção absoluta do núcleo nem substitui a jornada e as suítes finais do agente principal.
- Não alterei implementação nesta rodada. O arquivo review_regressions_test.go preserva os cinco cenários encontrados na revisão anterior.
- O diretório temporário desta rodada foi removido após os testes.

## Identidade dos arquivos lidos

- `internal/gokernel/verification_attempts.go`: `5ef12172f93968f74cad4d8b89cb26061968772016c5a7f68467045de54574d6`
- `internal/gokernel/verification.go`: `ea362746dd4fc67e84ef3a8a9e270df1522299dc06de2cb934fe6665db9f8f90`
- `internal/gokernel/verification_gates.go`: `85b3b9eae52551d672db34da04890971e79cc7f187d6d8fc5765ac247b98f306`
- `internal/gokernel/debug_proofs.go`: `c530685720dc9bb0ceb74d3aa45158bc5edf93a5b3b4a0f943528f20e759b051`
- `internal/gokernel/verification_output.go`: `d71b976e6bb1bc858205715ea455b6cac212985e8438f19d93a61e8fee6b7ba1`
- `internal/gokernel/plan.go`: `1ceb3c3766a58ff6310b2f74951772bb6271e958e1bba41af154df0029f91b9b`
- `internal/gokernel/workflow_proofs.go`: `5fa59f7194c98552f3d6cb3b92c7ec666f33cad1bbcfc03c745d325cc5bcc24d`
- `internal/gokernel/review_regressions_test.go`: `11a784b451aa98143c766ab7d7860df758968ab372751bbc1b07f3a45ddd46b5`

## Adendo: evidência real de resolução na homologação

Revisão em 2026-09-05T11:50:46.510241+00:00 por agent:critical_review, restrita ao delta de release_identity.go e sua chamada em verification.go.

validateHomologationGates recebe a raiz real do workspace. Finding resolved exige arquivo regular confinado ao repositório, conteúdo não vazio e SHA-256 dos bytes igual a resolution_sha256. A chamada ocorre no caminho de fechamento. Não encontrei bloqueio material nesse delta.

Executei somente:

```sh
go test -overlay=<temporário>/overlay.json ./internal/gokernel -run '^(TestHomologationRejectsFictitiousResolution|TestReviewResolutionEvidenceBytes)$' -count=1 -v
```

Resultado: dois testes passaram; pacote em 0,419s. O segundo teste foi uma sondagem temporária via overlay, sem edição do checkout. Verificou aceite de evidência real válida e rejeição de bytes alterados, arquivo vazio, caminho externo e symlink que escapa da raiz. O teste versionado rejeitou resolução fictícia. Temporários removidos.

Não repeti Docker nem suítes globais. A execução de TestRealContainerArtifactIdentity com Docker real foi informada pelo agente principal; não é evidência produzida por este revisor. O hash comprova integridade da evidência, enquanto a adequação semântica da resolução continua pertencendo à revisão do conteúdo.

Identidade do delta revisado:

- `internal/gokernel/release_identity.go`: `baed9ba72fd29fda96013192b9ec2f136857b7f5fd07ddbddd07be69d24fd441`
- `internal/gokernel/verification.go`: `d8dd9f59d0407a4be8cc9065c3882c18b9b7e14bcfb0899cba55bf24088fe613`
- `internal/gokernel/release_identity_test.go`: `d0f7ee81e04ec0ddd78ea7f2e3c7b5031c8abf7927b65402627f762ac30df6f1`
