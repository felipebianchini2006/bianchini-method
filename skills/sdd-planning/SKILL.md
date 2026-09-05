---
name: sdd-planning
description: Use para planejar mudanças multifase com arquitetura global, ProjectModel, dependências e coerência entre todos os planos do Bianchini Method.
---

# SDD Planning

**Anuncie:** "Planejando o sistema completo com Bianchini Method."

Leia [`../_shared/METHOD_CONTRACT.md`](../_shared/METHOD_CONTRACT.md), [`../_shared/STATE_TEMPLATE.md`](../_shared/STATE_TEMPLATE.md) e [`../_shared/ADAPTIVE_GATES.md`](../_shared/ADAPTIVE_GATES.md). Resolva o binário empacotado `../_shared/bin/bm` no Unix ou `../_shared/bin/bm.exe` no Windows uma vez. Ausência bloqueia; não use fallback Python.

Esta skill planeja; não edita código de produção. Toda operação determinística pertence ao CLI.

`/auditar-arquitetura` continua manual e report-only; não a executar automaticamente durante o planejamento. A revisão semântica do pacote usa o `SemanticReviewer` deste fluxo.

Ao mencionar a versão na abertura, no status ou na entrega, execute o binário empacotado com `version --json` uma vez na sessão e use o campo `version`: `Bianchini Method <version>`. `contract_version` e `STATE.md.method` identificam formatos internos; não são a versão instalada.

## 1. Preflight

1. Ler regras do repositório, `.bianchini/STATE.md` quando existir, manifests, lockfiles, CI, testes e histórico recente.
2. Sem `.bianchini/`, executar `bm model init --repo <repo>` para criar o workspace.
3. Se existir documentação anterior do Bianchini, não adaptar nem importar durante o planejamento: instruir `/migrar-bianchini`.
4. Nunca ler `.planning/` como estado, contexto ou fallback.
5. Confirmar Git, stack, escopo e trabalho ativo. Mudança concorrente no mesmo workspace bloqueia.
6. Se houver mudança ativa com status `scope_ready`, executar `bm scope verify --repo <repo> --change Cxxx-slug`, reutilizar seu ID e não resumir novamente o PDF.
7. Sem mudança ativa, iniciar com `bm model init --repo <repo> --change "<nome curto>"` e usar o ID `Cxxx-slug` retornado.

Escopo vindo de PDF só entra quando `scope verify` retornar `verified: true` e `ready_for_sdd`. Digest inválido, fonte trocada ou `SCOPE.md` alterado bloqueia. Mudança ativa em outro estágio não é substituída.

Uma interface nova, redesign ou fluxo visual material exige design aprovado antes da arquitetura. Mudança pequena preserva tokens e componentes existentes. Projeto sem interface não cria design artificial.

## 2. Pesquisa proporcional

Ordem de leitura: decisão atual, escopo, modelo/specs aceitos, design válido, código, testes, documentação e histórico.

Brownfield com múltiplas aplicações/linguagens, legado relevante ou contratos pouco claros usa [`../_shared/agents/repo-cartographer.md`](../_shared/agents/repo-cartographer.md) em modo somente leitura. Não usar em projeto novo ou pequeno. Cache transitório: `.bianchini/.runtime/cartography/<hash-do-HEAD>-<digest-do-escopo>.md`; `HEAD` diferente invalida o cache e escopo diferente gera outro arquivo.

Use [`references/stack-research.md`](references/stack-research.md) e grave `.bianchini/changes/Cxxx-slug/RESEARCH.md` no menor modo suficiente:

- `repo_only`: stack estabelecida e nenhuma decisão sensível nova;
- `targeted_web`: API, pagamento, autenticação, mobile, infraestrutura ou versão mutável;
- `full`: regulação, auditoria ou várias decisões críticas.

Pesquisa web usa fontes primárias oficiais. Registre somente decisões aplicadas, versões, riscos e alternativas rejeitadas. Pesquisa não autoriza upgrade nem expansão de escopo.

Decida stack e arquitetura autonomamente dentro do escopo contratado. Considere código existente, bibliotecas, integrações, operação, segurança, concorrência e crescimento plausível. Ruby, Python, TypeScript, Go, Java e C# são opções válidas. Monólito ou microserviços dependem de isolamento e operação concretos. Redis, filas, workers e serviços separados exigem uma necessidade identificada; não elimine componentes necessários para reduzir a contagem de tecnologias. Sem demanda de escala explícita, registre premissas proporcionais e um caminho de evolução. Justificativa curta em ARCHITECTURE.md basta.

## 3. Modelar o sistema completo

Crie, nesta ordem. Quando houver `SCOPE.md` selado pelo `/preparar-escopo`, preserve-o sem reescrever:

```text
SCOPE.md         resultados, limites, aceite e ações externas; criar somente sem intake selado
specs/expected/*.md  comportamento observável com IDs estáveis
specs/MANIFEST.json  mapeamento SCOPE → spec (gerado para IDs iguais)
specs/diff.md    projeção gerada pelo roadmap sync
ARCHITECTURE.md  decisões, stack, seams, trade-offs e alternativas
SYSTEM_MODEL.md  módulos, contratos, ownership, dados, integrações e journeys
plans/Pxx.md ou plans/Pxx-*.md   fases e tarefas tipadas
ROADMAP.md       visão derivada de todas as fases e suas relações
```

`SYSTEM_MODEL.md` usa o frontmatter descrito em [`../_shared/STATE_TEMPLATE.md`](../_shared/STATE_TEMPLATE.md). Ele descreve o estado final esperado, não o histórico de decisões.

Para specs compactas, use headings `## REQ-001: comportamento` com os mesmos IDs do SCOPE. `roadmap sync` gera MANIFEST.json inicial e diff.md. Se usar outros IDs, escreva o mapeamento explícito antes do sync; não duplique o texto do escopo. Specs descrevem comportamento, arquitetura descreve contratos estruturais e planos descrevem sequência e provas.

Não use a LLM para decidir ordem topológica, cobertura ou referências válidas. O CLI deriva e valida esses dados depois que os planos estiverem materializados.

## 4. Planejar por contratos

Cada plano em `plans/Pxx.md` ou `plans/Pxx-entrega.md` representa uma entrega rejeitável ou verificável. O prefixo `Pxx` é a identidade canônica e deve coincidir com o `id` do frontmatter; o sufixo descritivo em kebab-case é opcional. Não criar tarefa por arquivo, camada de teste, ferramenta ou documento.

O frontmatter de cada plano declara:

```yaml
schema_version: 2
id: P01
status: planned
result: <resultado observável>
requirements: [REQ-001, NFR-001]
acceptance: [<critério verificável>]
depends_on: []
provides: [<capability ou contrato>]
consumes: [<capability ou contrato>]
modules: [<módulo>]
interfaces: [<interface>]
ownership: [<recurso possuído>]
model_delta: <delta tipado de S(n-1) para Sn>
data: []
migrations: []
effects: []
rollback: <recuperação>
verifications: [<comando real e resultado esperado>]
future_constraints: []
execution: grouped | slice | strict
review: plan_gate | per_slice | per_task
tasks:
  - id: T01
    name: <ação curta>
    result: <resultado observável>
    covers: [REQ-001]
    depends_on: []
    files: [src/caminho.ext]
    action: <mudança concreta no seam público>
    verify:
      kind: command | procedure
      argv: [<executável>, <arg1>, <arg2>]
      cwd: .
      timeout_seconds: 300
      cache: fresh  # deterministic somente com entradas controladas
      proves: <o que a evidência demonstra>
    done: <condição objetiva de conclusão>
    risk_seam: <fronteira estável de risco>
```

Cada `Txx` é uma unidade executável e verificável, não uma nota em prosa. A tarefa deve caber no contexto de execução, indicar arquivos confinados ao repositório, cobrir ao menos um ID rastreável do `SCOPE.md` e declarar suas dependências. Caminho absoluto, `..`, `./`, barra invertida e `.planning/` são proibidos.

Para `kind: command`, use exatamente um de `argv` ou `run`; `argv` é preferido e não passa por shell. Para `kind: procedure`, use `run` como descrição determinística, não declare `argv` e planeje o artefato real que será entregue como evidência. `cwd` é relativo ao repositório e `timeout_seconds` fica entre 1 e 3600.

O modo define a granularidade obrigatória: `grouped → plan_gate`, `slice → per_slice` (cada Txx é a slice vertical identificável), `strict → per_task`. O CLI rejeita combinações incompatíveis, campos extras, IDs duplicados, dependência futura/cíclica, requisito sem tarefa e referência de módulo/interface/dado ausente no modelo.

No corpo, registre apenas contexto complementar, estados de erro/recuperação e decisões úteis. Não usar `TBD`, "tratar erros" ou abstração para consumidor futuro inexistente.

Preserve 100% do escopo. Setup, config e docs entram na primeira entrega que os consome. Ações externas declaram `needed_by`, fallback e checkpoint de autoridade.

Depois de materializar todos os planos, gere o roadmap. Não o mantenha manualmente:

```bash
bm roadmap sync --repo <repo> --change C001
```

## 5. Simular todas as fases

O pacote deve demonstrar:

```text
S0 atual → S1 após P01 → S2 após P02 → ... → Sn final
```

Execute:

```bash
bm roadmap sync --repo <repo> --change C001
bm model validate --repo <repo> --change C001
bm coherence check --repo <repo> --change C001 --structural-only
bm impact analyze --repo <repo> --change C001 --plan <Pxx>
```

O estrutural bloqueia ciclo de fase ou tarefa, cobertura faltante, referência desconhecida, provider ausente, consumidor adiantado, ownership incompatível, migração fora de ordem, journey incompleta, efeito externo sem guard e divergência de `Sn`. A resposta inclui ondas determinísticas de fases e tarefas executáveis em paralelo.

Registre em `COHERENCE.md` findings e `Impact Radius` (`local | direct | transitive | global`). Um plano não pode parecer correto sozinho enquanto invalida outro.

## 6. Revisão semântica conjunta

Leia `SCOPE`, `RESEARCH`, `ARCHITECTURE`, `SYSTEM_MODEL`, `ROADMAP` e todos os planos juntos. Produza JSON com findings sobre:

- abstração especulativa ou módulo sem profundidade;
- solução mais complexa que o necessário;
- responsabilidade no seam errado;
- conflito semântico entre decisões;
- aderência à stack e documentação oficial;
- jornada operacionalmente incoerente;
- risco arquitetural omitido;
- tarefa grande demais para um contexto seguro;
- sobreposição de arquivos ou ownership entre tarefas paralelas;
- lacuna entre requisito, tarefa, aceite e verificação;
- ordem de tarefa que oculta dependência semântica.

Formato mínimo, salvo temporariamente em `.bianchini/.runtime/semantic-review.json`:

```json
{
  "prompt": "<identificador/versão do contrato de revisão>",
  "inputs": "<review_input_digest retornado pelo check estrutural>",
  "sources": ["<fonte oficial aplicada>"],
  "findings": [
    {
      "code": "SPECULATIVE_ABSTRACTION",
      "severity": "WARNING",
      "phases": ["P03"],
      "contracts": ["contract_id"],
      "evidence": "<fato verificável>",
      "expected_fix": "<correção ou justificativa necessária>",
      "status": "open"
    }
  ]
}
```

Não registrar raciocínio interno. O CLI persiste somente findings normalizados e digests de prompt, entradas e fontes.

Normalize pelo CLI:

```bash
bm coherence check --repo <repo> --change C001 \
  --semantic-report <relatorio.json>
```

`inputs` deve ser exatamente o `review_input_digest` retornado pelo check estrutural. Ele vincula o parecer aos hashes atuais de `SCOPE`, `RESEARCH`, `ARCHITECTURE`, `SYSTEM_MODEL`, `ROADMAP` e todos os planos. Qualquer alteração torna o parecer obsoleto.

`ERROR` estrutural bloqueia. `WARNING` exige correção ou justificativa técnica verificável `accepted_with_justification` incluída no digest. `INFO` é observação. A revisão semântica indisponível não pode ser marcada como executada nem virar passe automático.

Um pacote completo sem `ERROR` ou `WARNING` aberto retorna `ready_for_approval` e o digest exato a aprovar. Isso ainda não é aprovação.

## 7. Garantia, decisão técnica e estado

Escolha `lean`, `standard` ou `full` pelo risco real. Não há quantidade fixa de fases ou tarefas. Distribua provas focais nas tarefas e gates integrados em `verifications` do plano; a release repete esses gates sobre o candidato atual, sem repetir todos os comandos históricos das tarefas.

Após revisão semântica disponível e zero ERROR/WARNING aberto, registre a decisão técnica do pacote:

```bash
bm coherence approve --repo <repo> --change C001 \
  --digest <digest-retornado-pelo-check> --decided-by "<agente>"
```

O estado `approved` significa pacote habilitado para execução. `approval.kind: technical_decision` distingue a decisão autônoma da aprovação comercial do escopo. `--approved-by` permanece para aprovação humana que realmente ocorreu. Nunca registrar aprovação humana por inferência.

Mudança material no produto contratado, novo custo recorrente, ação irreversível ou informação de negócio indispensável pode exigir intervenção. Arquivos, nomes, biblioteca equivalente dentro das restrições, correção comprovada de teste e organização de tarefas são decisões técnicas autônomas. Se afetarem o pacote, sincronize e revalide o digest sem pedir aprovação rotineira.

Crie commit local atômico do pacote. Esta skill entrega o planejamento; prossiga à implementação quando o pedido atual também autorizar executar.

## Saída

Informe ID da mudança, pesquisa, arquitetura, modelo final, fases, dependências, impact radius, findings por severidade, guards externos, perfil, digest e bloqueios.
