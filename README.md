# Bianchini Method

Método de desenvolvimento orientado a escopo, contratos e evidências. O CLI `bm`, escrito em Go, é a única autoridade operacional.

## Princípios

- todo estado do método fica em `.bianchini/`;
- planos descrevem resultados observáveis, dependências e cenários;
- provas ficam vinculadas ao código, ao plano e ao release candidate;
- homologação opera o produto real e corrige defeitos do escopo antes do aceite;
- decisões técnicas rotineiras são autônomas; ações externas preservam os limites de autorização;
- o método não promete fidelidade, cobertura ou qualidade que não verificou.

## Instalação

Requer Go 1.23 ou superior.

```bash
go build -trimpath -o bm ./cmd/bm
./bm version --json
```

O pacote distribuído instala as skills e o binário em `_shared/bin/bm` no Unix ou `_shared/bin/bm.exe` no Windows.

## Workspace

```text
.bianchini/
├── PROJECT.md
├── STATE.md
├── current/
│   ├── ARCHITECTURE.md
│   ├── SYSTEM_MODEL.md
│   ├── specs/
│   └── guides/
├── changes/C001-slug/
│   ├── SCOPE.md
│   ├── ARCHITECTURE.md
│   ├── SYSTEM_MODEL.md
│   ├── ROADMAP.md
│   ├── plans/P01-slug/
│   │   ├── PLAN.md
│   │   ├── RESULT.md
│   │   └── evidence/INDEX.md
│   ├── results/
│   └── homologation/RC-id/
│       ├── HOMOLOGATION.md
│       ├── evidence/
│       └── delivery/
├── quick/
├── debug/
├── archive/
└── .runtime/
```

`STATE.md` é um índice compacto. Arquitetura aceita, modelo, specs e guias ficam em `current/`. Cada plano mantém `PLAN.md`, `RESULT.md` e um índice derivado em `evidence/INDEX.md`. Provas, revisões, resultados de tarefas e logs têm uma única fonte oficial em `results/`. Os links relativos do índice sobrevivem ao arquivamento. O fechamento move a mudança concluída para `archive/`.

Atualizações de projetos antigos: consulte [Transição de formatos](docs/upgrading.md).

## Fluxo planejado

1. `/preparar-escopo` transforma um PDF em `SCOPE.md` rastreável quando necessário.
2. `/design-projeto` cria um contrato visual quando a mudança exige design material.
3. `/sdd-planning` modela o sistema e cria planos em `plans/Pxx-slug/PLAN.md`.
4. `/executar-plano` implementa, verifica, revisa e grava `RESULT.md`.
5. `/homologar-sistema` percorre os cenários no RC real, captura evidências e corrige defeitos.
6. `bm cycle-close` sincroniza o estado aceito e arquiva a mudança.

Mudanças coesas podem usar `/executar-direto`. Bugs com causa incerta usam `/corrigir-bug`. `/auditar-arquitetura` produz relatório sob pedido explícito.

## Cenários e homologação

Planos declaram cenários com requisito, plataforma, perfil, estado, risco, resultado esperado e tipos de evidência. A homologação registra cada cenário no RC final. Todo cenário exige observação real. Interfaces também exigem screenshot; API e CLI podem acrescentar log quando ele comprovar o efeito.

`ACEITO` exige todos os cenários obrigatórios aprovados e nenhuma falha conhecida aberta. Um hash prova integridade dos bytes. Ele não prova interpretação semântica, execução da jornada ou qualidade visual.

## CLI

Comandos públicos:

```text
version
model init|validate
scope seal|verify
roadmap sync|next-wave
coherence check|approve
impact analyze
plan complete|reopen
verify task|plan|release|review|status
context pack|verify
workspace create|check|locate|resume|finish
direct classify|start|status|checkpoint|finish|reopen
debug start|list|status|resume|checkpoint|finish
design-audit seal|verify
change-policy
policy
adapter render|install
learn propose|list|approve|reject|deactivate
spec-diff
status
update-bm
cycle-close
```

Use `bm --help` e `bm <command> --help` para a interface instalada. A referência curta está em [docs/cli-contract.md](docs/cli-contract.md).

## Verificação local

```bash
go test ./...
go vet ./...
go build -trimpath -o ./bm ./cmd/bm
./bm version --json
```

O CI executa testes, vet e build em Ubuntu, macOS e Windows. Consulte [docs/workflow.md](docs/workflow.md) para o fluxo completo e [docs/go-backend.md](docs/go-backend.md) para os limites do backend.

## Licença e atribuições

Consulte [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) para atribuições de referências e dependências.
