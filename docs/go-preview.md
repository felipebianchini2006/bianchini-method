# Backend Go preview

O backend oficial continua sendo o Python:

```text
python3 scripts/bm.py ...
```

O Go é experimental e precisa ser chamado de forma explícita:

```text
go build -trimpath -o bin/bm-preview ./cmd/bm-preview
./bin/bm-preview version --json
```

Não existe descoberta automática, subprocesso Python ou fallback entre backends.
O build de fonte usa `golang.org/x/text v0.23.0` para validar NFC como o oráculo Python.

## Paridade atual

O preview passa as 12 fixtures congeladas da Fase 0. Isso não representa paridade das 58 superfícies públicas atuais. As superfícies implementadas são informadas por `version --json`.

Os testes diferenciais adicionais cobrem paths de risco válidos, namespace proibido e Unicode não NFC. A ajuda CLI e todos os caminhos negativos das fatias experimentais ainda não possuem paridade exaustiva.

O harness pode ser executado assim:

```text
python3 scripts/run_cli_contract_fixtures.py --engine python
python3 scripts/run_cli_contract_fixtures.py --engine go --binary ./bin/bm-preview
```

## Cutover

O cutover não foi realizado. O Python permanece como oráculo e backend oficial até todos os gates da seção 14 do plano serem satisfeitos.

Não foram validados instalação limpa offline, update, rollback ou execução dos binários não nativos. Os cinco alvos foram apenas compilados; somente `darwin-arm64` recebeu smoke local.
