---
name: corrigir-bug
description: Use para diagnosticar e corrigir bugs com sessão persistente, hipóteses verificáveis, RED/GREEN, regressão e rastreabilidade opcional a mudanças anteriores.
---

# Corrigir Bug

**Anuncie:** "Abrindo ou retomando um debug persistente no Bianchini Method."

Resolva o binário empacotado `../_shared/bin/bm` no Unix ou `../_shared/bin/bm.exe` no Windows. Ausência bloqueia; não use fallback Python. O CLI e o pack do caso fornecem o contrato operacional necessário.

Princípio: nenhum fix antes de uma causa sustentada por evidência. Sintoma, correlação e componente onde a falha aparece não são automaticamente causa raiz.

Ao mencionar a versão na abertura, no status ou na entrega, execute o binário empacotado com `version --json` uma vez na sessão e use o campo `version`: `Bianchini Method <version>`. `contract_version` e `STATE.md.method` identificam formatos internos; não são a versão instalada.

## 1. Abrir ou retomar

Sem `.bianchini`, `debug start` inicializa o workspace do método quando o projeto é
novo. Se houver documentação anterior reconhecida, o CLI retorna
`MIGRATION_REQUIRED`; migre explicitamente antes de abrir o caso. Nenhum comando
de debug pode cair em armazenamento anterior.

```bash
bm debug list --repo <repo>
bm debug start --repo <repo> ...
bm debug status --repo <repo> ...
bm debug resume --repo <repo> ...
```

O CLI aloca `Dxxx` em `.bianchini/debug/active/` e atualiza `STATE.md` sem copiar o histórico do caso.

Compile o contexto do caso antes da investigação:

```bash
bm context pack --repo <repo> --unit D004
```

Use o pack como fonte primária. `PACK_INCOMPLETE`, `PACK_TOO_LARGE` ou `STALE_EVIDENCE` bloqueia o caso; regenere o pack sem reler o contrato completo ou criar fallback manual.

Registre:

- esperado e fonte do contrato;
- observado;
- ambiente, commit/build e frequência;
- menor reprodução conhecida;
- impacto e alcance;
- evidências disponíveis e dados a mascarar.

Referência opcional comprovada:

```yaml
origin_refs: [C003/P04]
relation: caused_by | detected_in | regression_of
```

Não atribuir causa arquitetural somente por proximidade temporal. Referência inválida ou sem evidência é rejeitada.

## 2. Máquina de estados

```text
intake → reproduced → diagnosed → red → fixing → green
→ regression_checked → documented → resolved | blocked | escalated
```

Use `bm debug checkpoint --repo <repo> ...` em cada transição. O CLI bloqueia avanço sem a evidência exigida, GREEN antes de RED e evidência anterior ao último patch.

No diagnóstico, use `--hypothesis`, `--experiment`, `--eliminated-hypothesis` e `--root-cause`. Em `regression_checked`, registre ao menos um `--neighbor-regression`. Em `documented`, registre `--residual-risk`. O CLI mantém esses campos estruturados no `Dxxx`.

Diagnóstico sem autorização de correção pode parar em `diagnosed`. Incidente crítico ativo pode receber contenção reversível autorizada, preservando evidências, antes do fix definitivo.

## 3. Reprodução determinística

1. Confirmar estado base e mudanças locais.
2. Reproduzir pela menor interface pública: teste, API, CLI, UI ou procedimento.
3. Capturar entrada, saída, erro, horário e ambiente sem segredo ou dado pessoal.
4. Repetir o necessário para distinguir determinismo, flake, corrida ou dependência externa.
5. Variar uma dimensão por vez e comparar com um caso saudável.

Não alterar produção nem dados reais para reproduzir. Use fixture, sandbox, conta de teste ou cópia sanitizada.

Quando automação não for viável, registre procedimento manual determinístico com pré-condições, passos, esperado e real.

## 4. Investigar por evidência

Trace para trás desde o primeiro estado incorreto:

1. onde o valor/comportamento se torna errado;
2. quem produziu a entrada;
3. qual contrato deveria impedir o estado;
4. por que os gates não detectaram;
5. qual condição ativou o defeito.

Formule uma hipótese falsificável:

```text
A causa é <mecanismo> porque <evidências>.
Se verdadeira, <experimento> produz <resultado>; senão, <contraprova>.
```

Teste uma hipótese por vez e preserve hipóteses eliminadas. Instrumentação é mínima, sanitizada e removida antes do commit.

Para crash window, partial commit, TOCTOU, retry ou recuperação após restart, identifique primeiro o invariante quebrado. Escolha correção local ou mudança arquitetural proporcional. Não escale automaticamente por categoria.

O seam representa o risco estável: renomear a tarefa não zera o seam nem suas tentativas consecutivas.

## 5. Regressão RED

Crie a menor prova que:

- falha no código defeituoso pelo motivo correto;
- usa interface pública ou limite estável;
- tem expectativa independente da implementação;
- passa no caso saudável vizinho;
- controla ordem, tempo e rede quando aplicável.

Use unitário para lógica isolada, integração/contrato para fronteira, E2E focado para jornada e evidência visual comparável para apresentação. Corrida usa relógio/sincronização controlados, não sleep arbitrário.

Execute RED pelo checkpoint com `--command <comando> --test-file <arquivo-da-regressão> --failure-pattern <assinatura-do-defeito>`. O executor exige exit 1, assinatura observada e ausência de timeout/spawn error. Outros códigos de saída precisam de um harness que distinga falha do contrato de infraestrutura, sem mascará-la.

## 6. Fix mínimo e GREEN

Corrija onde o contrato é violado. A menor mudança aceitável é a menor que torna o invariante verdadeiro; manter uma coreografia comprovadamente insegura não é mudança mínima.

Depois:

1. executar a mesma regressão e confirmar GREEN;
2. executar testes vizinhos de risco;
3. repetir a reprodução original;
4. validar sucesso, erro e recuperação;
5. remover instrumentação;
6. provar sensibilidade do teste quando viável.

GREEN e regression_checked também exigem `--command`. GREEN usa o mesmo comando e arquivo de teste imutável do RED. Qualquer alteração posterior invalida as provas; repita checkpoint green no mesmo Dxxx e depois regression_checked/documented. A retomada preserva o RED histórico.

## 7. Revisar e decidir impacto

Revise:

- evidência sustenta causa e relação opcional;
- RED representa o sintoma e falha sem o fix;
- fix restaura o contrato sem bypass ou perda silenciosa;
- regressões cobrem vizinhos reais;
- logs e artefatos não expõem dados;
- comportamento fora de escopo não mudou.

Bug que restaura spec aceita não altera a spec. Se a investigação provar que contrato, ownership, modelo, migração, journey ou invariante aceito está errado, finalize como `escalated`, registre os contratos afetados e use o impact radius no planejamento. Não use bug para contornar aprovação.

## 8. Finalizar

```bash
bm debug finish --repo <repo> ...
```

Quando a resolução demonstrar um padrão causal reutilizável, a finalização pode
nomear explicitamente uma proposta com `--learning-classification`,
`--learning-statement`, `--learning-tag` e `--learning-validity`. Isso cria apenas
uma fonte elegível para `bm learn propose`; aprovação humana continua separada
e obrigatória.

`resolved` exige causa, RED, GREEN, reprodução original, regressão vizinha e documentação vigentes. `blocked` exige condição externa específica. `escalated` preserva toda a investigação.

O CLI move casos resolvidos para `.bianchini/debug/resolved/` e atualiza `STATE.md`. Somente padrões causais realmente reutilizáveis entram em `KNOWLEDGE.md`; não copie o caso inteiro.

Quando Git fizer parte do fluxo, use commit atômico `fix: <causa resumida>`, sem arquivos alheios. Não faça push/deploy por inferência.

## Saída

Informe `Dxxx`, reprodução, causa, hipóteses eliminadas relevantes, RED/GREEN, fix, regressões, relação comprovada, commit, risco residual, arquivo resolvido e limite de prova.
