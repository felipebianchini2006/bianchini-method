# Uso e migração para o Bianchini Method 1.0

O fluxo continua: preparar escopo, planejar, executar e homologar. O núcleo exige prova completa e atual antes de concluir. A versão do executável é `1.0.0`; a linhagem do contrato persistido continua `0.4`, com `planning_contract: 2`. Anúncios, status e entregas consultam `bm version --json` e usam o campo `version`; o identificador do formato não é a versão do produto.

## Decisões e planejamento

O escopo define comportamento e restrições contratadas. O agente escolhe stack, arquitetura, sequência e verificações conforme essas restrições. Organização de arquivos, biblioteca equivalente e correção local não exigem pergunta. Custo não autorizado, mudança material de produto, ação irreversível ou informação indispensável continuam sendo limites reais.

`coherence approve --decided-by agent:planner` registra uma decisão técnica sobre o digest revisado. `--approved-by` é reservado à aprovação humana que ocorreu. O estado `approved` habilita execução; não inventa aceite comercial.

A skill `sdd-planning` lista os artefatos operacionais, incluindo `specs/expected/*.md`, `specs/MANIFEST.json` e `specs/diff.md`. `roadmap sync` gera manifesto inicial e diff quando os IDs de spec correspondem aos IDs do escopo. Mapeamentos diferentes exigem autoria explícita, pois não podem ser inferidos com segurança. Specs pequenas podem ficar em um único arquivo. Não há quantidade fixa de planos nem stack obrigatória.

## Provas e revisão

- Tarefa: `verify task` executa seu comando tipado e retorna `proof_id`.
- Plano: `verify plan` executa todos os gates integrados declarados em `verifications`.
- Conclusão: `plan complete --proof <id>` exige cobertura integral, identidade do comando, contexto e versão atuais. Uma revisão não dispensa provas.
- `grouped`: tarefa tem prova focal; revisão ocorre no plano integrado.
- `strict`: cada tarefa exige sua revisão.
- `slice`: cada tarefa vertical `Txx` é a fronteira verificável da revisão, identificada por plano e tarefa. Agrupe sua implementação nessa unidade.

Histórico de tarefa é preservado. Fechamento integrado executa os gates do estágio; não repete automaticamente todos os testes históricos. O cache é `fresh` por padrão. Uma verificação de tarefa pode declarar `verify.cache: deterministic` somente com entradas controladas. A identidade inclui comando, diretório, alvo, ambiente, pacote e contexto. Não deduplicar só pelo texto do comando. Serviço vivo ou estado mutável exige execução fresca.

`changes_requested` aceita `--finding` JSON com `target`, `observed`, `requirement`, `severity`, `evidence` e `expected_fix`. `evidence` aponta para arquivo real; o núcleo calcula seu hash. Severidades: `critical`, `high`, `medium`, `low`. Inspeção concreta dispensa teste vermelho artificial. Sugestão opcional fica no relatório, sem bloquear. A resolução usa revisão aprovada com provas atuais e `--resolves-review <id>`.

Saída de execução fica em log sanitizado, limitado a 256 KiB por fluxo. A prova guarda `log_path`, `log_sha256`, `output_truncated`, resumo de até 4 KiB por fluxo e identidade da execução. Use variáveis de ambiente para credenciais; comandos também são registrados. Sanitização cobre padrões conhecidos e valores de ambiente sensíveis, sem prometer reconhecimento universal de segredos arbitrários.

O contador de correções persiste por `risk_seam`. Renomear unidade ou aprovar outro comando não apaga uma falha pendente. Reexecutar a mesma versão não é nova correção; repetir uma falha nesse estado exige `--retry-reason`. Ao atingir `FIX_LIMIT_REACHED`, registrar diagnóstico e replanejar tecnicamente. Não apagar provas nem trocar o nome do risco para reiniciar a contagem. Retry, concorrência ou reinício exigem análise do invariante; não determinam redesenho automaticamente.

## Quick e debug

No quick, declare o comando em `direct start --verification`. Depois execute `direct checkpoint --command` com o mesmo comando. `direct finish` verifica as provas; `--verification "passou"` é apenas resumo. Quick antigo com checkpoint narrativo precisa executar um checkpoint real antes de concluir. Não precisa migrar para um plano.

No debug, `checkpoint --event red` exige `--command`, `--test-file` e `--failure-pattern`. Deve haver falha real com exit 1 e assinatura do defeito. Falha de spawn, timeout ou carregamento conhecido não é RED. GREEN executa o mesmo comando com o mesmo arquivo de regressão, após corrigir a implementação. `regression_checked` também executa comando real. Se o código mudar depois do GREEN, repita GREEN e a regressão antes de documentar e finalizar.

Essas provas vêm do mesmo executor Go utilizado pelos planos. O teste ainda precisa representar o comportamento investigado; o núcleo não demonstra semântica arbitrária apenas lendo uma mensagem de erro.

## Candidato e homologação

`verify release --artifact-kind <tipo> --build <alvo> --delivery ready` observa a identidade real. `--checksum` é uma expectativa opcional, conferida contra o alvo:

| Tipo | Identidade e alvo |
|---|---|
| `file` (padrão) | Arquivo regular dentro do repositório; SHA-256 calculado dos bytes |
| `container` | Imagem local inspecionada por `docker image inspect`; ID SHA-256 |
| `deployment` | Endpoint HTTP de saúde/versão do alvo em execução; status 200 e JSON `{"version":"<sha256>"}`, sem redirecionamento |

Os gates recebem `BM_CANDIDATE_BUILD` e `BM_CANDIDATE_CHECKSUM`. Devem testar esse alvo. A identidade é conferida antes e depois das execuções e novamente no fechamento. Um nome textual de build ou checksum arbitrário não basta. O exemplo demonstra testes no arquivo `.pyz`, inclusive com o fonte desabilitado na revisão independente.

A revisão final vincula os mesmos proofs do release. A homologação existente, em `results/HOMOLOGATION.md`, usa o candidato exato em `rc` e seu `fingerprint`. Não existe uma segunda homologação:

```json
{
  "schema_version": 1,
  "change": "C001-exemplo",
  "rc": {"copiar": "candidate completo retornado pelo release"},
  "fingerprint": "fingerprint retornado pelo release",
  "status": "accepted",
  "gates": [{"proof_id": "proof retornado pelo release", "result": "passed"}],
  "blockers": [],
  "findings": [],
  "manual_proofs": []
}
```

`gates` deve conter todos os proofs do release. `not_run`, `failed`, prova ausente ou de outro candidato bloqueiam. N/A pertence à matriz explicativa quando algo está fora do escopo; não substitui gate obrigatório. Finding `critical`, `high` ou `blocking: true` só deixa de bloquear quando resolvido. Resolução exige arquivo real em `resolution_evidence` e hash atual em `resolution_sha256`. `blockers: []` não anula finding aberto. Procedimentos manuais mantêm o contrato de `manual_proofs` da skill de homologação.

## Compatibilidade

O Python permanece como oráculo legado, explicitamente selecionado. Não é fallback do executável oficial. Fixtures antigas de quick/debug narrativos são exclusivas do Python e têm nota de migração; o Go possui regressões positivas e negativas com execução real. Schema 1 permanece coberto. Schema 2 usa `--proof`, não `--verification` como comprovação.

Pacotes e artefatos antigos sem os campos novos precisam de nova verificação/homologação para obter evidência atual. Não reescreva proofs antigos. Ajuda gerada contém extensões nativas; `task-brief`, `report`, `review-package` e `checkpoint` genéricos continuam apenas como compatibilidade. Fluxo atual usa `context pack`, `verify`, `direct` e `debug`.

## Reprodução

Requisitos declarados: Git, Go conforme `go.mod`, Python 3.13 no CI. Para a integração opcional real de imagem, execute `BM_TEST_DOCKER=1 go test ./internal/gokernel -run TestRealContainerArtifactIdentity -count=1 -v` com Docker disponível; a imagem temporária é removida pelo teste. O exemplo usa somente a biblioteca padrão Python e SQLite. Não exige npm, banco externo, pagamento ou imagem Docker.

Na raiz do checkout:

```bash
TASK_TMP=$(mktemp -d "${PWD}/../bm-v1-check.XXXXXX")
export TMPDIR="$TASK_TMP"
go test ./...
go vet ./...
go build -trimpath -o "$TASK_TMP/bm" ./cmd/bm
BM_FULL_JOURNEY_BACKEND=go \
BM_FULL_JOURNEY_GO_BINARY="$TASK_TMP/bm" \
BM_GO_SUITE_ALREADY_RUN=1 \
python3 scripts/run_test_shards.py
python3 scripts/run_service_example.py --binary "$TASK_TMP/bm" --protocol-test
rm -rf "$TASK_TMP"
```

`BM_GO_SUITE_ALREADY_RUN=1` evita repetir a suíte Go dentro do teste Python, após ela ter sido executada acima. O CI usa o mesmo encadeamento. A suíte sharded distingue núcleo, CLI, jornada oficial Go e compatibilidade.

`--protocol-test` usa revisões declaradas como fixture de teste. Não afirma independência. Para um aceite real, um revisor deve conferir o PDF, o escopo canônico, o produto e os testes, produzindo JSON com `reviewer`, `sources`, `findings`, `fixture_sha256` de `app.py`, `test_service.py` e `scope.md`, e `scope_pdf_sha256`. Depois:

```bash
python3 scripts/run_service_example.py --binary "$TASK_TMP/bm" \
  --scope-pdf /caminho/escopo.pdf --review-report /caminho/revisao.json
```

O runner usa comandos públicos para selar escopo, sincronizar specs, revisar coerência, executar, verificar, homologar e fechar. Cada chamada reconstrói estado em um novo processo CLI. A retomada é verificada por leitura do workspace persistido; isso não equivale a certificar a restauração da conversa de todos os hosts de agentes.

A demonstração cobre criação, operador, isolamento, persistência em novos processos e entradas inválidas. Inclui quick de texto de ajuda, debug com regressão real e falhas controladas. O projeto é descartável; `--directory` permite reter suas evidências em diretório vazio criado com `mktemp -d`. O PDF padrão é gerado de `tests/fixtures/service_requests/scope_input.txt`.

Os registros da validação inicial estão no histórico Git, em `e5bc8e6:reports/v1/validation.md`. Para validar a versão atual, execute a suíte e o exemplo acima.
