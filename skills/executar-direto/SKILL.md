---
name: executar-direto
description: Use para executar uma entrega coesa como quick normal ou protegido, com score determinístico, evidência final e documentação em `.bianchini/quick`.
---

# Executar Direto

**Anuncie:** "Classificando e executando este quick com Bianchini Method 0.4."

Use somente por invocação explícita de `/executar-direto` e resolva `bm.py`. Não acione outra metodologia. A escolha explícita deste fluxo é a decisão de roteamento: o quick nunca aciona `/sdd-planning`, independentemente do score, dos hazards ou da complexidade encontrada.

Planos, specs e decisões já existentes em `.bianchini/` são documentação e rastreio. Use-os como contexto confiável, sem exigir novo planejamento para executar a tarefa solicitada.

Quick normal e quick protegido podem usar subagentes quando o host suportar e houver frentes independentes que reduzam o tempo ou aumentem a qualidade. Use somente os contratos internos relevantes, com ownership fechado, contexto mínimo e saída esperada. Não fixe nome, modelo, reasoning effort, hierarquia, quantidade ou paralelismo; use os padrões atuais do host. Sem subagentes, cumpra a mesma responsabilidade inline.

O executor principal integra os resultados, resolve conflitos e mantém uma única revisão final do quick. Uma revisão independente pode rodar em paralelo quando o risco justificar. Não criar subagente por arquivo, camada de teste ou gate mecânico.

## 1. Confirmar que é uma entrega coesa

Leia regras, `.bianchini/STATE.md` quando existir, manifests, CI, Git e apenas os arquivos ligados ao objetivo. Registre objetivo, estado atual factual, não objetivos, aceite, seams e comandos reais de verificação.

Não use `.planning/`. Sem `.bianchini`, `direct start` inicializa o workspace 0.4
quando o projeto é novo. Se existir qualquer documentação anterior reconhecida,
o CLI bloqueia com `MIGRATION_REQUIRED`; use `/migrar-bianchini`. Nunca use flags
ou rotas de execução de versões anteriores.

## 2. Classificar o risco

`risk = scope + external_effect + migration + concurrency + money`.

Cada dimensão vale `0`, `1` ou `2`:

| Dimensão | 0 | 1 | 2 |
|---|---|---|---|
| `scope` | localizado | vertical coeso | vários objetivos/domínios |
| `external_effect` | nenhum | sandbox/reversível | produção/irreversível |
| `migration` | nenhuma | aditiva/reversível | destrutiva/difícil rollback |
| `concurrency` | não aplicável | retry/idempotência conhecidos | ordem/escritores sem solução |
| `money` | não financeiro | sandbox/consulta | estado ou efeito financeiro real |

Execute antes de editar:

```bash
bm.py direct classify --repo <repo> \
  --scope-score <0..2> \
  --external-effect-score <0..2> \
  --migration-score <0..2> \
  --concurrency-score <0..2> \
  --money-score <0..2> \
  [--multiple-objectives] \
  [--destructive-migration] \
  [--uncontrolled-concurrency] \
  [--undefined-ownership] \
  [--ambiguous-financial-rule] \
  [--new-material-architecture]
```

Roteamento retornado pelo CLI:

- `0–2`: quick normal;
- `3–10`: quick protegido.

Sinais críticos como `scope=2`, migração destrutiva, concorrência não controlada, ownership indefinido, regra financeira ambígua, arquitetura material nova ou várias entregas independentes tornam ou mantêm o quick protegido. Eles aumentam guards, pesquisa, checkpoints e evidências, mas nunca desviam o trabalho para outro fluxo.

Pagamento e webhook não escalam pela palavra. Eles podem ser quick protegido quando formam um fluxo único, usam arquitetura conhecida e possuem guards completos.

Em `direct start`, sinalize `--payment-flow` e/ou `--webhook-flow`. O CLI deriva os guards obrigatórios das dimensões e do tipo de fluxo. Guards são nomes estáveis como `official_docs`, `source_of_truth`, `local_contract`, `authenticity`, `deduplication`, `replay_order`, `idempotency`, `timeout_recovery`, `persistence`, `reconciliation`, `rollback` e `sandbox`.

## 3. Iniciar ou retomar

Execute `bm.py direct start` com objetivo, escopo, estado atual, aceite, verificações, cinco scores e overrides retornados por `classify`. O CLI aloca `Qxxx` e persiste:

```text
.bianchini/quick/Qxxx-slug/
├── BRIEF.md
├── PROGRESS.md
└── RESULT.md
```

O brief contém score, justificativas, modo, não objetivos, arquivos/interfaces prováveis, guards, comandos e digest. Retomada exige o mesmo digest; mudança de brief invalida evidências anteriores.

Depois de iniciar ou localizar o quick, compile seu contexto operacional:

```bash
bm.py context pack --repo <repo> --unit Q012
```

Use o pack como fonte primária. `PACK_INCOMPLETE`, `PACK_TOO_LARGE` ou `STALE_EVIDENCE` bloqueia a execução; regenere o pack sem reler o contrato completo ou montar contexto manual.

`STATE.md` aponta para o quick ativo sem copiar seu histórico. Branch principal suja, detached HEAD ou mudanças não reconhecidas bloqueiam. Use a branch segura criada/validada pelo CLI.

## 4. Guards do quick protegido

Aplicar somente os guards relevantes, mas nenhum obrigatório pode ficar implícito:

- provedor, ambiente, versão e documentação oficial;
- origem de verdade e estados duráveis;
- contrato local de API/webhook;
- autenticidade, deduplicação, replay e eventos fora de ordem;
- idempotência de comandos e efeitos financeiros;
- timeout/retry com resultado externo desconhecido;
- persistência antes do efeito quando o invariante exigir;
- reconciliação e recuperação após restart;
- rollback/compensação;
- testes locais, de contrato e sandbox;
- checkpoint antes de efeito real.

Não impor fila ou outbox automaticamente. Use o padrão mais simples já sustentado pela stack e pelo invariante.

Cobrança real, refund, operação paga, ativação externa ou outro efeito irreversível exige autoridade explícita no momento da ação. Sandbox aprovado não prova produção.

Se um guard revelar ownership ambíguo, regra indefinida ou arquitetura nova, resolva a decisão mais simples sustentada pelo repositório, pela documentação vigente e pelo aceite. Se faltar autoridade ou informação impossível de obter, finalize como `blocked` com o impedimento específico. Complexidade, risco ou necessidade de investigação não são bloqueios por si só.

## 5. Implementar e comprovar

Trabalhe continuamente, com o menor diff correto:

- regra, parser, permissão, cálculo ou bug: RED/GREEN no seam público;
- fronteira externa: contrato local e sandbox quando necessário;
- visual: browser/viewport e evidência comparável;
- mudança mecânica: checks focados e regressão proporcional.

Quando houver trabalho independente, despache em paralelo pesquisa localizada, implementação com ownership separado ou revisão especializada. Não terceirize a decisão de aceite, a integração do diff, os checkpoints nem a conclusão do quick.

Use `bm.py direct checkpoint` para registrar arquivo alterado, comando, resultado e evidência estruturada. Evidência de comando `passed` exige `exit_code: 0`; browser, screenshot ou manual exige referência reproduzível. Toda evidência fica vinculada ao digest do brief e ao fingerprint da árvore.

Não instalar framework de qualidade, criar abstração futura ou abrir tarefa por camada de teste. Em retomada, use `bm.py direct status` e leia apenas `PROGRESS.md`.

## 6. Concluir

Antes de `direct finish`:

1. comparar diff e aceite;
2. revisar contrato e qualidade;
3. executar todos os comandos planejados aplicáveis;
4. confirmar ausência de evidência falha, obsoleta ou alteração não registrada;
5. atualizar spec, arquitetura ou `SYSTEM_MODEL.md` somente quando o comportamento aceito mudou;
6. atualizar `STATE.md` atomicamente.

`completed` exige comportamento entregue, evidência fresca e nenhum bloqueio. `blocked` exige condição externa específica. O quick não possui saída `escalated`.

O `RESULT.md` diferencia código, testes, sandbox, deploy, efeito em produção/provedor e homologação humana.

Não fazer push, merge, deploy ou efeito externo além da autorização atual.

## Saída

Informe `Qxxx`, classificação e score, guards aplicados, comportamento, arquivos, verificações, limites de prova, branch, `RESULT.md` e próxima ação.
