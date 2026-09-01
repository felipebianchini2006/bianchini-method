# Relatório final — evolução sustentável 0.4.7 → 0.5

Data: 2026-09-01

Branch: `dev/evolucao-sustentavel-0.4.7-0.5`

Base e `origin/main`: `7c9fa23f524623f3360ebae579048e1765095220`

Head funcional auditado: `ed2841c478dcbda3da2563d62d12110a38558b84`

Head publicado: o commit administrativo deste relatório sucede o head funcional. Obtenha o valor exato com `git rev-parse origin/dev/evolucao-sustentavel-0.4.7-0.5`.

Veredito: **BLOCKED** para a aceitação final. Os gates executáveis da implementação passaram e a auditoria não manteve finding conhecido `CRITICAL` ou `IMPORTANT`, mas o plano normativo obrigatório não está disponível para provar os gates das seções 14 e 17.

Estado operacional local no macOS: **READY_TO_USE**. O pacote `0.5.0` foi instalado e validado no Codex; esse estado operacional não substitui o fechamento documental bloqueado acima.

Não há alegação de “zero regressão”. O veredito cobre somente os contratos, testes, builds e medições descritos aqui.

## 1. Resultado

O fluxo público foi preservado pelos contratos e testes disponíveis:

```text
/preparar-escopo
-> /design-projeto quando aplicável
-> /sdd-planning
-> /executar-plano all
-> /homologar-sistema
-> pronto para deploy explícito

/executar-direto para trabalho pequeno/coeso
/corrigir-bug para bugs
/status-projeto para leitura de estado
```

O backend oficial é Go `0.5.0`. O binário declara `engine=go`, `official=true`, `preview=false`, `contract_version=0.4` e 58 superfícies implementadas. As skills ativas apontam somente para `_shared/bin/bm`; não existe fallback Python silencioso. O Python permanece no repositório como oráculo de compatibilidade.

A instalação local ativa está em `~/.codex/skills`. O binário instalado foi construído de `999888d86132c5754a0bbbec40dfdcb486b36376`, passou 78/78 fixtures Go e as duas jornadas completas schema 1/schema 2. O overlay Codex foi reinstalado pelo instalador gerenciado e as skills de terceiros foram comparadas com o backup sem divergência.

O aprendizado continua opt-in, exige identidade humana para aprovação/desativação e não edita automaticamente kernel, schemas, `METHOD_CONTRACT` ou skills.

Não houve merge na main, release ou publicação de artifacts. Somente a branch de implementação deve ser publicada para restauração da prova normativa e nova auditoria. A branch não está liberada para merge enquanto o plano não for relido integralmente.

## 2. Preflight e isolamento

- `origin/main`, `main` local e merge-base permaneceram em `7c9fa23f524623f3360ebae579048e1765095220`.
- A suite da baseline foi reexecutada em worktree destacado de `origin/main`: `python3 scripts/run_test_shards.py` terminou com `22 shards aprovados`.
- A implementação ocorreu em worktree e branch dedicadas.
- O remoto não avançou durante a execução final.
- Changes antigas não foram migradas.
- O namespace proibido não foi usado como fonte, destino ou alvo de comandos de auditoria.
- Arquivos e mudanças de terceiros foram preservados.

O plano normativo não está presente no checkout final nem no attachment acessível à auditoria independente. O SHA-256 anteriormente registrado para o plano é `aa170b8054c48a07f2787f7434575731f0302b9328cbae7e83998bd10ea2eacc`. A auditoria final revalidou os contratos congelados, o registro público, os testes e as evidências versionadas, mas não pôde montar a matriz requisito → código → teste → evidência das seções 14 e 17. Essa ausência bloqueia a aceitação final.

A reexecução dos 22 shards confirma a suite existente no commit-base atual. Ela não substitui a leitura do plano nem prova, por si só, a completude do escopo evolutivo.

## 3. Commits por fase

| Fase | Commits principais | Resultado |
|---|---|---|
| 0 — contrato público | `c5a85f9`, `52cdb9e` | Interface congelada; todas as superfícies possuem fixture de comportamento. |
| 1 — specs e close | `1b1bc17`, `50f0226`, `38dabd2`, `bded063` | Schema 2 gerenciado, schema 1 preservado, close recuperável e jornadas integradas. |
| 2 — contexto e DocViva | `c32cc4d`, `1a50b6d`, `0694271` | Packs adotados após completude; métricas reproduzíveis; escrita idêntica preservada. |
| 3 — risco, ondas e adapters | `3c33650`, `2ea080a`, `2ad3299` | Piso derivado, ondas consumíveis e adapters sem decisão de host no kernel. |
| 4 — aprendizado governado | `98ae3e0`, `04e32d7`, `32000a5`, `3a6665d`, `257d22d` | Proposta opt-in, lock compartilhado, aprovação humana e retries duráveis. |
| 5 — Go vertical e cutover | `92898b6` até `1b851d7`; cutover isolado `15737ec`; hardening `685f139`, `9686fdd`, `82a209a`, `b56f906`, `7f3d29b`, `ed2841c` | 58 superfícies, paridade completa, updater/release nativos e publish durável. |

O cutover de linguagem ficou isolado em `15737ec`. As correções funcionais anteriores e posteriores possuem commits próprios.

Histórico completo e ordenado:

```bash
git log --reverse --format='%H %s' 7c9fa23f524623f3360ebae579048e1765095220..HEAD
```

## 4. Testes por fase

| Fase | Testes e gates |
|---|---|
| 0 | Registro canônico válido; help estático em 77 paths; 78/78 fixtures no Python. |
| 1 | `test_spec_package`, `test_close_recovery`, schema 1 e schema 2 nas jornadas completas. |
| 2 | `test_context_pack`, `test_context_cli`, `test_context_skill_adoption`, `test_docviva`, `test_phase2_metrics`. |
| 3 | `test_risk_floor`, `test_next_wave`, `test_host_adapters`, `test_phase3_cli`. |
| 4 | `tests.test_learning`: 17/17; fixtures de propose/list/approve/reject/deactivate e retries. |
| 5 | `go test ./...`, `go test -race ./...`, `go vet ./...`, `go mod verify`, 78/78 fixtures Go, jornadas Go schema 1 e 2. |

Gate agregado final:

```text
python3 scripts/run_test_shards.py
38 shards aprovados.
```

Baseline isolada:

```text
origin/main 7c9fa23f524623f3360ebae579048e1765095220
python3 scripts/run_test_shards.py
22 shards aprovados.
```

Resultados finais adicionais:

```text
go test ./...          PASS
go test -race ./...    PASS
go vet ./...           PASS
go mod verify          all modules verified
CLI help               77 paths reproduzíveis
Python fixtures        78 passed, 0 failed
Go fixtures            78 passed, 0 failed
Python full journeys   2 passed
Go full journeys       2 passed
```

## 5. Fixtures de compatibilidade

O diretório `tests/fixtures/cli_contract` contém 78 fixtures. O harness compara por backend:

- argv;
- exit code;
- stdout completo;
- stderr completo, inclusive `usage` do argparse;
- arquivos criados, alterados, removidos e preservados;
- bytes esperados quando aplicável.

As fixtures cobrem as 58 superfícies públicas e os negativos congelados. Incluem schema 1, schema 2, caminhos inseguros, symlinks, recuperação, update, aprendizado governado e a jornada completa.

## 6. Métricas de contexto e DocViva

Fonte versionada: `reports/evolution-0.4.7/phase2-context-docviva.json`.

| Skill | Antes | Depois | Redução em bytes |
|---|---:|---:|---:|
| `executar-plano` | 35.309 | 16.074 | 54,48% |
| `executar-direto` | 28.559 | 10.598 | 62,89% |
| `corrigir-bug` | 27.042 | 8.700 | 67,83% |
| `homologar-sistema` | 30.528 | 12.776 | 58,15% |
| `status-projeto` | 22.686 | 8.611 | 62,04% |

O “antes” é recalculado por `git show` em sete paths explícitos do commit-base, com bytes e SHA-256. O “depois” é medido pelo oráculo Python após o cutover, pois a compilação de contexto continua sendo um contrato de compatibilidade. Não há alegação de economia de tokens.

DocViva:

- runtime histórico reexecutado com três fluxos estruturais;
- 12/12 fixtures históricas da Fase 0 aprovadas contra o runtime-base;
- zero mutações em `.bianchini/current` nessas 12 fixtures;
- escrita com bytes idênticos preserva conteúdo e `mtime`;
- mudanças internas justificadas registram zero arquivos atuais alterados;
- mudança comportamental exige declaração correspondente.

Limite: as 12 fixtures não existiam no commit-base. A evidência usa o runtime-base com o contrato congelado na Fase 0; não recria o instante histórico nem mede qualidade semântica.

## 7. Paridade Python/Go

```text
Superfícies registradas: 58
Fixtures Python:        78/78
Fixtures Go:            78/78
Jornada schema 1 Go:    PASS
Jornada schema 2 Go:    PASS
Backend oficial:        Go 0.5.0
Fallback runtime:       ausente
```

O Python segue como oráculo versionado. A execução oficial das skills usa o binário Go. Não existe seleção automática de backend.

## 8. Artifacts reproduzíveis e checksums

O builder foi executado duas vezes a partir de `ed2841c478dcbda3da2563d62d12110a38558b84`. Os cinco archives, `SHA256SUMS` e `release-manifest.json` foram comparados byte a byte. Nenhum artifact foi publicado.

```text
d2d03d08d2010d82984420793df60f7e78aa5f963383b5591e2ef8a32400c481  bianchini-method_0.5.0_darwin-amd64.tar.gz
87bdd0504919215f576fd93656c32fecb0bc959c7cb3822f163f8bca140e105b  bianchini-method_0.5.0_darwin-arm64.tar.gz
35af778d7f148ddb56a4f9a0767ca7c41c891134b02fbc8c6dfe60af866e3c0a  bianchini-method_0.5.0_linux-amd64.tar.gz
a6f200a191095b643c7a45e26dfc122a03bafebd0ca06844f8b4cfce13dee985  bianchini-method_0.5.0_linux-arm64.tar.gz
ac8a843fe6e1d25dd0792d91d5730d775effb50400e6f7b217dd1d25d41b2fea  bianchini-method_0.5.0_windows-amd64.tar.gz
```

O updater valida identidade, manifesto, tamanho, digest, paths e troca transacional. O teste de integração constrói um package real, instala, executa o binário instalado e prova rollback.

Para ativação local no Mac, foi gerado e verificado separadamente o package `darwin-arm64` do commit `999888d86132c5754a0bbbec40dfdcb486b36376`:

```text
c828f2049da0d757f199fc9b359fb6cda1ae2fca0e9e3fa1f3c2fac7a444da38  bianchini-method_0.5.0_darwin-arm64.tar.gz
```

O archive local foi removido após a instalação. Ele não foi publicado como release.

## 9. Hardening final

As correções da auditoria final incluem:

- rejeição de conteúdo extra e números fracionários nos journals tipados, além de chaves duplicadas no `MANIFEST.json` gerenciado;
- persistência com file sync, publish atômico e barreira de diretório no Unix;
- `MoveFileExW` com `MOVEFILE_WRITE_THROUGH` no Windows;
- tombstone imprevisível para remoção Windows, sem apagar colisões de terceiros;
- abertura gravável para `File.Sync` no Windows;
- help CLI completo e byte a byte compatível com argparse;
- parsing de `--flag=value`, abreviações únicas, intermixing e `--`;
- lock e retries duráveis no aprendizado para approve, reject e deactivate;
- validação de ID antes de qualquer path derivado;
- verificação do target já instalado na recuperação committed do updater;
- binding entre versão pedida, versão das skills e versão compilada.

O ambiente de uso e validação nativa desta entrega é macOS. As correções e o cross-build Windows acima são compatibilidade adicional; não constituem gate, risco ou bloqueio para o uso no Mac.

## 10. Riscos e limitações restantes

1. **Bloqueador de aceitação:** o plano normativo não pôde ser relido pela auditoria independente. O contrato congelado e as evidências versionadas sustentam os testes executados, mas não substituem a prova de completude das seções 14 e 17.
2. As métricas são bytes, não tokens.
3. As jornadas automatizadas provam os fluxos estruturais e públicos. Homologação humana de um produto real continua sendo responsabilidade do projeto consumidor.
4. Os artifacts foram produzidos somente em diretórios temporários e não foram publicados.

Nenhuma dessas limitações autoriza enfraquecer schema, digest, path safety, evidência ou gates.

## 11. Comandos exatos para auditoria independente

```bash
git fetch origin
git switch --detach origin/dev/evolucao-sustentavel-0.4.7-0.5
git rev-parse HEAD
git rev-parse origin/main
git merge-base origin/main HEAD
git status --short --branch
git diff --check origin/main...HEAD

python3 scripts/generate_cli_help.py --check
python3 scripts/measure_phase2_context_docviva.py --check
python3 scripts/run_cli_contract_fixtures.py --engine python

go test ./...
go test -race ./...
go vet ./...
go mod verify

python3 scripts/run_test_shards.py
```

Reprodução isolada da baseline:

```bash
audit_baseline_root=$(mktemp -d)
git worktree add --detach "$audit_baseline_root/checkout" origin/main
(
  cd "$audit_baseline_root/checkout"
  python3 scripts/run_test_shards.py
)
git worktree remove "$audit_baseline_root/checkout"
rmdir "$audit_baseline_root"
```

Paridade Go e jornadas com backend explícito:

```bash
audit_tmp_dir=$(mktemp -d)
go build -trimpath -o "$audit_tmp_dir/bm" ./cmd/bm
python3 scripts/run_cli_contract_fixtures.py --engine go --binary "$audit_tmp_dir/bm"
PYTHONPATH=tests BM_FULL_JOURNEY_BACKEND=go BM_FULL_JOURNEY_GO_BINARY="$audit_tmp_dir/bm" PYTHONDONTWRITEBYTECODE=1 python3 -m unittest test_full_journey.FullJourneyScenarios -v
"$audit_tmp_dir/bm" version --json
unlink "$audit_tmp_dir/bm"
rmdir "$audit_tmp_dir"
```

Compatibilidade adicional opcional — cross-build Windows, fora dos gates do ambiente macOS:

```bash
audit_windows_dir=$(mktemp -d)
GOOS=windows GOARCH=amd64 go test -c -o "$audit_windows_dir/gokernel.test.exe" ./internal/gokernel
GOOS=windows GOARCH=amd64 go build -o "$audit_windows_dir/bm.exe" ./cmd/bm
unlink "$audit_windows_dir/gokernel.test.exe"
unlink "$audit_windows_dir/bm.exe"
rmdir "$audit_windows_dir"
```

Reprodução dos artifacts a partir do head funcional, sem publicar release:

```bash
audit_release_root=$(mktemp -d)
mkdir "$audit_release_root/output"
git worktree add --detach "$audit_release_root/checkout" ed2841c478dcbda3da2563d62d12110a38558b84
(
  cd "$audit_release_root/checkout"
  go run ./tools/bm-release --repo . --output "$audit_release_root/output" --commit HEAD
)
shasum -a 256 "$audit_release_root/output"/*.tar.gz
git worktree remove "$audit_release_root/checkout"
unlink \
  "$audit_release_root/output/bianchini-method_0.5.0_darwin-amd64.tar.gz" \
  "$audit_release_root/output/bianchini-method_0.5.0_darwin-arm64.tar.gz" \
  "$audit_release_root/output/bianchini-method_0.5.0_linux-amd64.tar.gz" \
  "$audit_release_root/output/bianchini-method_0.5.0_linux-arm64.tar.gz" \
  "$audit_release_root/output/bianchini-method_0.5.0_windows-amd64.tar.gz" \
  "$audit_release_root/output/SHA256SUMS" \
  "$audit_release_root/output/release-manifest.json"
rmdir "$audit_release_root/output"
rmdir "$audit_release_root"
```

## 12. Estado de entrega

- Main intacta.
- Branch dedicada publicada para continuação da auditoria, mas ainda não apta para merge.
- Ambiente macOS validado nativamente.
- Bianchini Method `0.5.0` instalado em `~/.codex/skills` e pronto para uso local.
- Instalação anterior `0.4.5` preservada em `~/.codex/.bianchini-method-backups/20260901T211225Z-v0.4.5-skills`.
- Binário instalado: Go oficial, 58 superfícies, 78/78 fixtures e 2/2 jornadas completas.
- Cutover Go explícito e observável.
- Release não publicada.
- Deploy continua exigindo ação explícita no projeto consumidor.
- Aceitação final bloqueada até restaurar o plano exato, confirmar seu SHA-256, relê-lo integralmente e refazer a matriz das seções 14 e 17.
