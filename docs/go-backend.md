# Backend Go oficial

O pacote `0.5.0` usa o backend Go oficial:

```text
go build -trimpath -o bin/bm ./cmd/bm
./bin/bm version --json
```

`version --json` informa `engine: go`, `official: true`, `preview: false`, contrato público `0.4` e as 58 superfícies congeladas. Não existe descoberta automática, subprocesso Python ou fallback entre backends.

O Python continua disponível somente como oráculo explícito durante a janela de compatibilidade:

```text
python3 scripts/run_cli_contract_fixtures.py --engine python
python3 scripts/run_cli_contract_fixtures.py --engine go --binary ./bin/bm
```

As 78 fixtures congeladas incluem cenários positivos, negativos e jornadas multioperação. O gate integrado adicional executa os fluxos schema 1 e schema 2 nos dois backends.

## Distribuição

O builder gera archives reproduzíveis para cinco alvos, `release-manifest.json` e `SHA256SUMS`. Cada archive contém as skills, o binário nativo, `LICENSE` e `THIRD_PARTY_NOTICES.md`. O updater valida identidade, tamanho e SHA-256 antes de extrair, rejeita paths inseguros e usa lock, journal, backup e recuperação transacional.

Builds cruzados provam compilação. Execução local prova somente a plataforma nativa; os outros binários precisam de auditoria de runtime em seus sistemas antes de uma publicação de release.
