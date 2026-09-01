# Auditoria independente — evolução sustentável 0.4.7 → 0.5

Data: 2026-09-01

Branch auditada: `dev/evolucao-sustentavel-0.4.7-0.5`

Base aprovada e `origin/main`: `7c9fa23f524623f3360ebae579048e1765095220`

Head de código auditado: `b9b0b7cbb42d41ac3132c1c76df5e790b0a53379`

Plano lido integralmente: SHA-256 `aa170b8054c48a07f2787f7434575731f0302b9328cbae7e83998bd10ea2eacc`
Veredito: **NEEDS_WORK**

> O commit deste relatório é administrativo e sucede o head de código auditado. O head publicado exato deve ser obtido com `git rev-parse HEAD` após o checkout da branch remota.

## 1. Resultado executivo

A implementação preserva o Python como backend oficial, mantém o Go como preview explícito e não realiza cutover inseguro. A suíte completa da branch terminou com `35 shards aprovados`. A baseline destacada em `origin/main` repetiu os `22 shards aprovados`. Os testes Go, race detector, vet, matriz de compilação e as 12 fixtures congeladas passam nas duas engines.

O plano completo ainda não está concluído. Há três findings IMPORTANT abertos:

1. a cobertura golden da interface pública não abrange todas as 58 superfícies registradas;
2. o Go implementa somente 6 fatias declaradas de preview e não possui paridade integral;
3. a jornada integrada obrigatória da seção 15 não está demonstrada de ponta a ponta em uma única execução controlada.

Não foi encontrado finding CRITICAL. Os findings IMPORTANT locais que admitiam correção compatível e delimitada foram corrigidos com RED/GREEN e commits próprios. Os três restantes exigem completar trabalho material previsto no plano; eles impedem `PASS`, cutover e release.

Não há alegação de “zero regressão”. A evidência se limita aos testes e medições registrados neste relatório.

## 2. Preflight e isolamento

- `origin/main`, base e merge-base coincidiam em `7c9fa23f524623f3360ebae579048e1765095220`.
- A implementação ocorreu em worktree e branch dedicadas.
- `main` não recebeu merge nem commit desta auditoria.
- A branch não contém diff em `.planning/` contra `origin/main`.
- Changes antigas não foram migradas.
- Não houve release, publicação de binário ou cutover.
- A comparação de baseline foi feita em worktree temporária destacada de `origin/main`.

Comandos de confirmação:

```bash
git fetch origin --prune
git rev-parse origin/main
git merge-base origin/main HEAD
git status --short --branch
git diff --name-only origin/main...HEAD -- .planning
```

## 3. Matriz fase → commits → testes

| Fase | Commits de implementação | Correções desta auditoria | Evidência de teste |
|---|---|---|---|
| 0 — contrato e baseline | `c5a85f9` | — | baseline destacada: `22 shards aprovados`; verificador do contrato válido; 12 fixtures Python verdes |
| 1 — specs gerenciadas e close | `1b1bc17` | `50f0226` | `test_spec_package`, `test_close_recovery`, `test_method_v04_cli`; suíte final verde |
| 2 — packs e DocViva | `c32cc4d` | `50f0226` também protege promoção seletiva | `test_context_pack`, `test_context_cli`, `test_context_skill_adoption`, `test_context_efficiency`, `test_docviva`; suíte final verde |
| 3 — risco, ondas e adapters | `3c33650` | `2ea080a`, `2ad3299` | `test_risk_floor`, `test_next_wave`, `test_host_adapters`, `test_phase3_cli`; suíte final verde |
| 4 — aprendizado governado | `98ae3e0` | `04e32d7` | `test_learning` e seleção de lições em `test_context_pack`; suíte final verde |
| 5 — Go preview | `92898b6`, `d2e7394`, `e4fe380` | `b9b0b7c` | `go test ./...`, `go test -race ./...`, `go vet ./...`, `go mod verify`, 12 fixtures Go e matriz de build verdes |
| Evidência de execução | `8de1295` | este relatório | revalidação independente completa descrita nas seções 7 a 11 |

O agrupamento acima preserva a separação entre mudança funcional e linguagem. Não houve commit de cutover.

## 4. Correções feitas durante a auditoria

### `04e32d7` — aprendizado governado utilizável

RED observado:

- uma sessão debug real não conseguia indicar aprendizado ao terminar;
- uma fonte Markdown comum causava `LEARNING_SOURCE_INVALID` em vez de ser ignorada como não candidata;
- symlink sob a área controlada podia ser percorrido antes da rejeição da fonte.

GREEN:

- `debug finish` aceita indicação explícita e opcional de proposta;
- a evidência nasce dos eventos debug persistidos;
- somente fonte com frontmatter estruturado é candidata;
- travessia segura rejeita symlink e variantes case-insensitive de `.planning`;
- aprovação continua separada, humana, opt-in e ligada ao digest atual;
- kernel, schemas, `METHOD_CONTRACT` e skills não são editados automaticamente.

### `2ea080a` — ondas consumíveis e seguras

RED observado:

- tarefas com paths sobrepostos podiam aparecer na mesma onda;
- o adapter orientava o host a fornecer um `contract_digest` que a interface pública não produzia;
- faltava uma transição pública operacional que ligasse resultado, pack e conclusão da tarefa.

GREEN:

- conflito por path exato ou ancestral agora separa tarefas deterministicamente;
- a saída informa `resource_overlap`;
- adapters usam os digests realmente emitidos;
- a transição usa a ação pública existente `plan complete --task ... --context-pack ...`;
- resultado liga `pack_identity`, `pack_digest` e `package_digest`;
- schema 1 mantém o comportamento legado;
- decisões de host não foram incorporadas ao kernel.

### `50f0226` — DocViva inalterada não é reescrita

RED observado:

- close com conteúdo idêntico alterava `mtime` de arquitetura/spec;
- variantes case-insensitive de `.planning` nos paths de recuperação não falhavam como `PATH_UNSAFE`.

GREEN:

- escrita atômica vira no-op quando os bytes são iguais;
- promoção da árvore de specs preserva bytes e `mtime` dos arquivos inalterados;
- adição, alteração, remoção e modo de arquivos continuam promovidos;
- os pontos de close/recovery aplicam a mesma regra case-insensitive de path safety.

### `2ad3299` — piso de risco ligado ao drift atual

RED observado:

- uma quick iniciada como normal continuava normal mesmo após a DocViva atual ganhar migração destrutiva estruturada.

GREEN:

- a sessão guarda snapshot do modelo no início;
- `finish` compara o modelo atual real;
- sinais estruturados de `migration` e `destructive_migration` elevam o piso;
- a rota pública continua `quick`; o resultado protegido não introduz redirecionamento obrigatório para SDD.

### `b9b0b7c` — licença da dependência Go

RED observado:

- `golang.org/x/text v0.23.0` estava pinado, porém sem o texto de licença exigido pelo plano.

GREEN:

- `THIRD_PARTY_NOTICES.md` contém o aviso BSD 3-Clause da dependência;
- teste reconcilia módulos externos declarados com os notices.

## 5. Findings abertos

### IMPORTANT-001 — cobertura golden incompleta da superfície pública

Evidência:

- `contracts/cli-surfaces.json` registra 58 superfícies;
- as 58 possuem referências a behavior tests;
- apenas 5 superfícies do registro ligam fixtures golden, totalizando 8 referências;
- o diretório congelado possui 12 cenários e o harness executa esses 12;
- behavior tests focados não substituem a comparação golden completa exigida na Fase 0: argv, exit code, stdout, stderr e árvore/bytes do workspace para toda superfície pública.

Impacto:

- o Python não está completamente congelado como oráculo para todas as superfícies;
- divergências futuras podem não ser detectadas pelo harness de paridade.

Critério para fechar:

- criar fixtures determinísticas para todas as superfícies públicas congeladas, incluindo falhas, symlink/path traversal, concorrência, permissões e recuperação quando aplicável;
- executar cada fixture em Python e Go sem alterar golden para esconder divergências.

### IMPORTANT-002 — paridade Go e gates de cutover incompletos

Evidência:

- `bm-preview version --json` declara 6 fatias implementadas: `change-policy`, `direct:classify`, `direct:reopen`, `spec-diff:file`, `status:legacy` e `workspace:create-parser`;
- o registro público contém 58 superfícies;
- model, scope, planning, coherence, impact, context pack, DocViva, learning, update e companions restantes não foram portados integralmente;
- schema 1/schema 2 completos, crash recovery, concorrência, instalação limpa, update e rollback não possuem paridade Go demonstrada;
- `workspace:create-parser` é parser-only e retorna `NOT_IMPLEMENTED` para a operação.

Impacto:

- o gate central da seção 14 falha;
- o Go não pode virar backend oficial.

Estado seguro atual:

- Python segue oficial;
- Go segue `0.4.7-preview`, experimental e explícito;
- não há fallback silencioso Python/Go;
- não foi feito cutover.

Critério para fechar:

- portar verticalmente todas as superfícies congeladas;
- provar paridade completa nas fixtures ampliadas;
- validar instalação limpa, update, rollback, concorrência e recovery;
- obter nova auditoria independente sem finding CRITICAL ou IMPORTANT aberto.

### IMPORTANT-003 — jornada integrada obrigatória não demonstrada

Evidência:

- há testes focados e integrações parciais por módulo;
- não foi encontrada uma execução única, controlada e reproduzível que percorra os 13 passos da seção 15: projeto vazio, scope rastreável, design opcional, change, specs/modelo/planos/roadmap, coerência, aprovação, workspace, ondas/packs, conclusão, close recuperável, homologação real e estado pronto para deploy explícito.

Impacto:

- a composição entre subsistemas não está provada no fluxo público completo;
- a definição de pronto da seção 17 permanece aberta mesmo com shards unitários/integrados verdes.

Critério para fechar:

- adicionar uma fixture de jornada completa, com variante sem design e variante com design quando aplicável;
- validar schema 1 e schema 2, `.planning/` presente e intocado, erro/recuperação e deploy apenas como estado explícito, sem publicação real.

## 6. Interface pública e compatibilidade

O verificador retornou:

```text
command_count: 31
surface_count: 58
negative_surface_count: 4
errors: []
valid: true
```

O fluxo humano documentado permanece:

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

As mudanças auditadas não criam uma etapa humana obrigatória nova. O aprendizado é opt-in. O piso de risco protege a quick sem trocar sua rota pública.

## 7. Fixtures de compatibilidade

Os 12 cenários congelados passam em Python e no Go preview:

1. `change-policy-material.json`
2. `change-policy-read-only.json`
3. `direct-classify-default.json`
4. `direct-classify-protected.json`
5. `direct-reopen-terminal.json`
6. `retired-legacy-transition.json`
7. `retired-repo-hygiene.json`
8. `retired-route.json`
9. `spec-diff-created-output.json`
10. `status-legacy-json.json`
11. `status-legacy-text.json`
12. `workspace-old-companion-flags.json`

Resultado independente:

```text
Python: 12 passed, 0 failed
Go:     12 passed, 0 failed
Golden intencionalmente alterado: 0
```

Este resultado prova paridade somente para esses 12 cenários. Não prova paridade das 58 superfícies.

## 8. Testes finais independentes

| Comando | Resultado |
|---|---|
| `PYTHONDONTWRITEBYTECODE=1 python3 scripts/run_test_shards.py` em `origin/main` destacado | `22 shards aprovados` |
| `PYTHONDONTWRITEBYTECODE=1 python3 scripts/run_test_shards.py` na branch | `35 shards aprovados` |
| `python3 scripts/verify_cli_contract.py` | válido; 31 comandos, 58 superfícies, 4 negativas, 0 erros |
| `python3 scripts/run_cli_contract_fixtures.py --engine python` | 12/12 |
| `python3 scripts/run_cli_contract_fixtures.py --engine go --binary <temporário>` | 12/12 |
| `go test ./...` | verde |
| `go test -race ./...` | verde |
| `go vet ./...` | verde |
| `go mod verify` | `all modules verified` |
| matriz `CGO_ENABLED=0` para 5 targets | 5/5 compilados |

Os binários usados na auditoria foram temporários e removidos ao final. Alvos não nativos foram cross-compiled, não executados.

## 9. Métricas atuais de contexto

Definição: bytes de `SKILL.md` mais pack compilado em fixture versionada. A baseline mede bytes do contexto estático prescrito. Não houve medição de tokens nem alegação de economia de tokens.

| Skill/unidade | Antes | Depois | Fontes no pack | Redução medida |
|---|---:|---:|---:|---:|
| `executar-plano` — `C001/P01/T01` | 35.309 B / 3 arquivos | 16.019 B / 2 arquivos | 15 | 19.290 B (54,63%) |
| `executar-direto` — `Q012` | 28.559 B / 2 arquivos | 10.487 B / 2 arquivos | 4 | 18.072 B (63,28%) |
| `corrigir-bug` — `D004` | 27.042 B / 2 arquivos | 8.598 B / 2 arquivos | 2 | 18.444 B (68,21%) |
| `homologar-sistema` — `RC:build-a` | 30.528 B / 2 arquivos | 12.712 B / 2 arquivos | 3 | 17.816 B (58,36%) |
| `status-projeto` — `C001/P01` | 22.686 B / 2 arquivos | 8.497 B / 2 arquivos | 14 | 14.189 B (62,55%) |

Essas medições foram refeitas no head auditado. Elas substituem, para este head, os números históricos menores de `reports/evolution-0.4.7/phase2-context-docviva.json`, sem reescrever o relatório histórico.

Limite da evidência: bytes prescritos e compilados não equivalem a tokens nem provam o conteúdo efetivamente lido por um agente.

## 10. Métricas atuais de DocViva

Fixture independente em repositório temporário:

- antes: 3 arquivos, 72 bytes;
- escrita idêntica retornou `false` e preservou `mtime`;
- fluxo interno `not_applicable`: 0 arquivos alterados;
- fluxo comportamental: somente `.bianchini/current/specs/payment.md` mudou;
- artefato comportamental: 29 bytes;
- depois: 4 arquivos, 101 bytes.

Testes de close também demonstram preservação de `mtime` para arquitetura e specs inalteradas durante promoção. Recovery cobre specs, journal truncado e variantes de path inseguro.

Limite da evidência: a medição é estrutural. A qualidade semântica continua sujeita à revisão humana.

## 11. Python/Go, builds e checksums

Estado declarado pelo preview:

```text
version: 0.4.7-preview
engine: go-preview
official: false
preview: true
contract_version: 0.4
implemented_surfaces: 6 fatias declaradas
```

Builds determinísticos temporários do head de código `b9b0b7cbb42d41ac3132c1c76df5e790b0a53379`:

| Target | SHA-256 |
|---|---|
| darwin-amd64 | `26757c55be4f8c81abe9a06def06d424c04388a0fed8fcf7f90f583e44fc2c35` |
| darwin-arm64 | `ace26a3f2dcd4cf8f16becd647bca7bf5aca0034255504cba727ffbb95ba1733` |
| linux-amd64 | `049ac49171c41fa978e2c63b34c346e629bda5e95ffab04bcd08730761868229` |
| linux-arm64 | `b0fc158ad16c7489527fe82ca46c6e041bf8b455a5e6013eecfe6d04f0716fb7` |
| windows-amd64 | `60eae67f380495250199ccd2449d9fc1c409fadb7b98eb43547aedf051c91bba` |

Comando de build:

```bash
CGO_ENABLED=0 GOOS=<os> GOARCH=<arch> go build \
  -mod=readonly -trimpath \
  -ldflags "-s -w -buildid= -X github.com/felipebianchini2006/bianchini-method/internal/gokernel.BuildCommit=b9b0b7cbb42d41ac3132c1c76df5e790b0a53379" \
  -o <arquivo-temporário> ./cmd/bm-preview
```

Esses checksums são evidência de cross-build da auditoria. Não são artefatos de release e não foram publicados.

## 12. Gate de cutover

| Gate da seção 14 | Estado | Evidência |
|---|---|---|
| todas as superfícies públicas possuem paridade | **FALHA** | 6 fatias Go declaradas versus 58 superfícies registradas |
| schema 1 e schema 2 possuem fixtures | **FALHA** | cobertura Python focada existe; paridade Go integral não |
| suíte Python antiga continua verde | PASSA | baseline 22/22 e branch 35/35 |
| `go test ./...` verde | PASSA | comando independente verde |
| builds da matriz verdes | PASSA PARCIALMENTE | 5/5 cross-build; somente darwin-arm64 executado nativamente |
| instalação limpa validada | **FALHA** | não demonstrada para distribuição Go |
| update e rollback validados | **FALHA** | não demonstrados para backend Go oficial |
| nenhuma skill chama Python específico salvo launcher | **FALHA** | Python ainda é oficialmente consumido, como esperado no preview |
| nenhum backend silencioso | PASSA | preview e oficial são explícitos; inspeção/testes não acharam fallback |
| auditoria independente aprovada | **FALHA** | este relatório é `NEEDS_WORK` |

Resultado: cutover corretamente não realizado.

## 13. Definição de pronto da seção 17

| Critério | Estado |
|---|---|
| fluxo público preservado | demonstrado pelo contrato e skills auditadas |
| 22 shards originais passam | demonstrado |
| testes novos passam | demonstrado: 35 shards totais |
| specs em digest/approve/stale/close para changes novas | demonstrado nos testes Python |
| changes antigas fecham sem reescrita | demonstrado nos testes Python |
| packs são default e medidamente menores | demonstrado em bytes no Python |
| DocViva seletiva e sem reescrita inalterada | demonstrado estruturalmente |
| quick mantém rota e piso de risco | demonstrado |
| ondas consumíveis por qualquer host | demonstrado na interface host-neutral e fixtures dos adapters |
| adapters têm fonte canônica | demonstrado |
| aprendizado é opt-in, evidenciado e aprovado | demonstrado no backend Python |
| Go possui paridade de toda superfície | **não satisfeito** |
| backend visível | demonstrado |
| instalação, update e rollback funcionam | **não satisfeito para o cutover Go** |
| auditoria sem finding CRITICAL/IMPORTANT | **não satisfeito** |
| branch publicada | deve ser confirmado após o push do commit deste relatório |
| `main` intacta antes da auditoria | demonstrado |

## 14. Riscos e limitações restantes

- As 12 fixtures verdes cobrem somente uma fração da interface congelada.
- O Go preview não executa o fluxo público principal completo.
- Recovery e concorrência ainda não possuem prova de paridade Go.
- Instalação limpa offline, update e rollback de uma distribuição Go não foram validados.
- Alvos Linux e Windows foram compilados, mas não executados nativamente.
- A jornada completa da seção 15 precisa de fixture integrada.
- As métricas de contexto são bytes, não tokens.
- A medição de DocViva é estrutural, não uma homologação semântica humana.

## 15. Comandos exatos para auditoria independente

Checkout limpo:

```bash
git clone https://github.com/felipebianchini2006/bianchini-method.git
cd bianchini-method
git fetch origin --prune
git switch --track origin/dev/evolucao-sustentavel-0.4.7-0.5
git rev-parse origin/main
git merge-base origin/main HEAD
git rev-parse HEAD
git status --short --branch
git diff --name-only origin/main...HEAD -- .planning
```

Contrato e suíte Python:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/verify_cli_contract.py
PYTHONDONTWRITEBYTECODE=1 python3 scripts/run_cli_contract_fixtures.py --engine python
PYTHONDONTWRITEBYTECODE=1 python3 scripts/run_test_shards.py
```

Go:

```bash
go version
go mod verify
go test ./...
go test -race ./...
go vet ./...
go run ./cmd/bm-preview version --json
```

Paridade das 12 fixtures atuais com binário temporário:

```bash
audit_tmp_dir=$(mktemp -d /tmp/bm-audit-parity.XXXXXX)
go build -mod=readonly -trimpath -o "$audit_tmp_dir/bm-preview" ./cmd/bm-preview
PYTHONDONTWRITEBYTECODE=1 python3 scripts/run_cli_contract_fixtures.py \
  --engine go --binary "$audit_tmp_dir/bm-preview"
find "$audit_tmp_dir" -depth -delete
```

Matriz de build:

```bash
audit_tmp_dir=$(mktemp -d /tmp/bm-audit-build.XXXXXX)
build_commit=$(git rev-parse HEAD)
for target in darwin/amd64 darwin/arm64 linux/amd64 linux/arm64 windows/amd64; do
  go_os=${target%/*}
  go_arch=${target#*/}
  suffix=""
  if [ "$go_os" = windows ]; then suffix=".exe"; fi
  CGO_ENABLED=0 GOOS="$go_os" GOARCH="$go_arch" go build \
    -mod=readonly -trimpath \
    -ldflags "-s -w -buildid= -X github.com/felipebianchini2006/bianchini-method/internal/gokernel.BuildCommit=$build_commit" \
    -o "$audit_tmp_dir/bm-preview-${go_os}-${go_arch}${suffix}" ./cmd/bm-preview
  shasum -a 256 "$audit_tmp_dir/bm-preview-${go_os}-${go_arch}${suffix}"
done
find "$audit_tmp_dir" -depth -delete
```

## 16. Veredito

**NEEDS_WORK**

Motivo: os gates de paridade total Go, cobertura golden integral, instalação/update/rollback e jornada completa continuam abertos. A posição segura é manter Python oficial e Go preview explícito até que esses itens sejam implementados e uma nova auditoria independente os aprove.
