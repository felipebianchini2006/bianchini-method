---
name: corrigir-bug
description: Use somente com invocação explícita de /corrigir-bug ou dentro de uma execução cujo PROJECT_STATE declare method_version 2. Em projetos v1, apenas roteia ao systematic debugging legado e não concorre com skills gerais de debugging.
---

# Corrigir Bug

**Anuncie ao iniciar:** "Corrigindo bug via Bianchini Method <v1|v2> no risco <baixo|médio|alto|crítico>."

## Princípio

Nenhum fix antes de uma causa sustentada por evidência. Sintoma, correlação e componente onde a falha aparece não são automaticamente a causa raiz.

Leia [`../_shared/METHOD_CONTRACT.md`](../_shared/METHOD_CONTRACT.md), resolva `bm.py` e execute `route`.

- V1: exigir Superpowers e usar seu systematic debugging/TDD/revisão. Sem ele, `BLOQUEADO`.
- V2: validar estado e executar `workspace check` antes de qualquer fix. Continuar no mesmo ledger e RC; não criar trilha paralela.

## 1. Intake e risco

Registrar uma frase para cada item:

- comportamento esperado e fonte (spec, contrato, teste ou decisão);
- comportamento real;
- ambiente, versão/commit e frequência;
- menor sequência conhecida para reproduzir;
- impacto e alcance;
- evidência disponível e dados sensíveis que precisam ser mascarados.

Classificar:

- **baixo:** apresentação, docs ou configuração reversível sem contrato;
- **médio:** função comum, integração isolada ou regressão sem perda de dados;
- **alto:** autorização, migração, concorrência, offline, geolocalização, contrato compartilhado;
- **crítico:** segurança explorável, pagamento, privacidade, corrupção/perda de dados ou produção parada.

Risco alto/crítico exige isolamento seguro, confirmação independente da hipótese quando a capacidade existir e revisão independente. Para incidente crítico ativo, priorizar contenção reversível autorizada antes do fix definitivo e preservar evidências.

## 2. Reprodução determinística

1. Confirmar o estado base e mudanças locais.
2. Reproduzir pela menor interface pública possível: teste, API, CLI, UI ou procedimento.
3. Capturar entrada, saída, código de erro, horário e ambiente sem segredo ou dado pessoal.
4. Repetir o suficiente para distinguir determinismo, flake, corrida ou dependência externa.
5. Se não reproduzir, variar uma dimensão por vez e comparar com um caso saudável.

Não alterar produção nem dados reais para reproduzir. Usar fixture, sandbox, conta de teste, banco descartável ou cópia sanitizada.

Quando reprodução automatizada não for viável, escrever um procedimento manual determinístico com pré-condições, passos, esperado e real. A limitação deve aparecer na revisão.

## 3. Investigação por evidência

Trace a cadeia de dados para trás a partir do primeiro estado incorreto:

1. onde o valor/comportamento se torna errado pela primeira vez;
2. quem forneceu a entrada;
3. qual contrato deveria ter impedido o estado;
4. por que testes/gates não detectaram;
5. qual mudança ou condição ativou o defeito.

Comparar caso saudável e falho. Observar limites entre componentes antes de adicionar logs internos. Instrumentação temporária deve ser mínima, sanitizada e removida antes do commit.

Formular uma hipótese falsificável:

```text
A causa é <mecanismo> porque <evidências>. Se for verdadeira, <experimento mínimo> produz <resultado>; caso contrário, produz <contraprova>.
```

Testar uma hipótese por vez. Após três hipóteses refutadas, reler arquitetura/contratos e atualizar o diagnóstico. Fix rounds seguem `bm.py policy`: Lean 2, Standard 3, Full 5. Quando `breaker: true`, parar patches e bloquear problema estrutural.

## 4. Regressão RED

Criar a menor prova que:

- falha no código defeituoso pelo motivo correto;
- usa uma interface pública ou limite estável;
- contém expectativa independente da implementação;
- passa no caso saudável vizinho;
- não depende de ordem, tempo ou rede sem controle explícito.

Executar e registrar o RED. Para bug visual, o RED pode ser screenshot determinístico, comparação visual ou procedimento reproduzível que evidencie o defeito; não criar teste unitário artificial. Se o defeito for ambiental ou não automatizável, usar script/procedimento reproduzível e declarar a limitação.

Para corrida, tempo ou concorrência, preferir sincronização/relógio controlado a sleeps. Para integração externa, testar o contrato local e validar no sandbox real quando necessário.

## 5. Fix mínimo GREEN

Corrigir no ponto onde o contrato é violado, não apenas onde o erro aparece. Alterar uma causa por vez e evitar refatoração, atualização de dependência ou limpeza não necessária.

Depois:

1. executar a regressão e confirmar GREEN;
2. executar testes diretamente vizinhos;
3. remover instrumentação temporária;
4. verificar casos saudável, erro e recuperação;
5. para alto/crítico, executar gates de contrato, integridade e segurança aplicáveis;
6. provar sensibilidade do teste quando viável: reverter apenas o fix, confirmar RED e restaurar, ou demonstrar a falha no commit/base anterior.

Para bug visual, capturar evidência equivalente GREEN no mesmo viewport/plataforma e conferir estados vizinhos e acessibilidade afetada.

## 6. Revisão

Revisar o diff em duas passagens:

### Causa e spec

- evidência sustenta a causa declarada;
- regressão representa o sintoma e falha sem o fix;
- fix restaura o contrato aprovado;
- comportamento fora de escopo não mudou.

### Qualidade e risco

- mudança é mínima e não mascara falha;
- tratamento ocorre no limite correto;
- não introduz bypass de segurança, perda silenciosa ou incompatibilidade;
- teste não está acoplado a detalhes internos;
- logs e artefatos não expõem dados.

Achado crítico/importante exige nova rodada de fix e revisão do delta. Mudança necessária de regra de negócio ou contrato aprovado é bloqueio e pede decisão; não chamar de bug para evitar aprovação.

## 7. Reteste e registro

Se o bug veio de uma jornada/gate:

1. reexecutar a reprodução original;
2. reexecutar gate afetado e dependentes;
3. testar jornadas vizinhas de risco;
4. atualizar o ledger ou resumo de homologação com evidência e commit;
5. manter o mesmo RC apenas se o identificador incluir o novo commit/build; caso contrário, gerar novo RC.

O commit e o teste são o registro padrão do bug resolvido. Quando Git estiver disponível e commits fizerem parte do fluxo, usar commit atômico `fix: <causa raiz resumida>`, sem arquivos alheios.

Atualizar:

- `KNOWN_ISSUES.md` somente se o problema ou risco residual continuar aberto;
- `DECISIONS.md` somente para decisão difícil de reverter/contrato;
- `PROJECT_STATE.md` somente se status, RC, gate ou bloqueio mudou;
- ledger do plano ou `SUMMARY.md` da homologação quando o bug nasceu ali.

Não criar relatório permanente separado para bug simples.

## Encerramento

Informar sintoma reproduzido, causa raiz, teste RED/GREEN ou limitação manual, fix, comandos/resultados, retestes, commit e risco residual. Só declarar corrigido com evidência fresca no estado final.
