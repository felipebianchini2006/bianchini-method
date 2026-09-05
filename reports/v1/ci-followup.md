# Correção da compatibilidade no CI

Data: 2026-09-05. Caso: D004. Continuação da validação do candidato 1.0.

## Causa confirmada

O [CI original](https://github.com/felipebianchini2006/bianchini-method/actions/runs/33964635081)
falhou no contrato Python antes de executar o exemplo público. O teste ocultava
o relatório JSON porque só mostrava stderr. O commit diagnóstico `a1bdc7d`
passou a incluir stdout na falha. O [CI diagnóstico](https://github.com/felipebianchini2006/bianchini-method/actions/runs/33965647402)
confirmou 84 fixtures aprovadas e uma falha: `success-migration`.

O oráculo Python preservava a ordem de `os.walk`. No runner, o manifesto de
design apareceu antes do protótipo. O contrato congelado e o Go colocam o
manifesto por último. A correção ordena os caminhos e mantém cada manifesto
após seus arquivos. Conteúdo, hashes, destinos e validações de symlink permanecem.

Uma regressão nova força duas ordens de enumeração. As duas falharam antes do
patch; depois, ambas passam. O teste executa check e apply, verifica hashes,
remoção das fontes migradas e preservação de `.planning`.

## Isolamento adicional do harness

A reprodução Linux também encontrou um problema independente: uma fixture sem
Git podia descobrir um repositório pai ou produzir erro dependente da fronteira
do filesystem. `GIT_CEILING_DIRECTORIES` agora limita a busca à raiz temporária.
Uma regressão real falhou antes e passou depois; seu contrato RED/GREEN e as
provas executadas estão no caso D004. Isso não foi a causa da falha remota.

Python 3.13.15 foi exercitado em Linux arm64 com a imagem oficial
`python:3.13.15-bookworm`, digest
`sha256:933b46a028fd786c9c3d426ebabc237e29a15912231ea8de576e95f0e4f41a4c`.
Esse ambiente não equivale ao runner Ubuntu x64. A diferença de patch do Python
não explica a falha observada; o log remoto identifica a ordem dos arquivos.

Nenhuma expectativa de fixture foi relaxada e nenhum teste foi desativado.
O relatório continua comparando saída, erros e mutações exatamente.

## Verificação reproduzível

```sh
go test ./...
go vet ./...
go build -trimpath -o /tmp/bm ./cmd/bm
BM_FULL_JOURNEY_BACKEND=go BM_FULL_JOURNEY_GO_BINARY=/tmp/bm BM_GO_SUITE_ALREADY_RUN=1 python3 scripts/run_test_shards.py
python3 scripts/run_service_example.py --binary /tmp/bm --protocol-test
```

As provas locais finais de regressão estão no caso D004. A confirmação remota
deve corresponder ao HEAD do [PR #4](https://github.com/felipebianchini2006/bianchini-method/pull/4),
incluindo os passos do exemplo e dos entrypoints. Não inferir sucesso remoto
a partir de resultados locais ou de uma revisão automática separada do CI.
