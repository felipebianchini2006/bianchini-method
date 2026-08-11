---
name: homologar-sistema
description: Use somente com invocação explícita de /homologar-sistema ou quando PROJECT_STATE declarar method_version 2 e release.status candidate. Em v1, apenas roteia à homologação legado.
---

# Homologar Sistema

**Anuncie:** "Homologando RC <id> com automação primeiro."

Leia [`../_shared/METHOD_CONTRACT.md`](../_shared/METHOD_CONTRACT.md) e resolva [`../_shared/scripts/bm.py`](../_shared/scripts/bm.py).

## 1. Rota e pré-condições

1. Executar `bm.py route`.
2. V1: exigir Superpowers e usar homologação legado; sem ele, `BLOQUEADO`.
3. V2: validar estado e confirmar planos `completed`, `verification.plan: passed`, fingerprint completo do RC (`id`, `revision`, `build`, `checksum`) e ambiente/dados de teste.
4. Confirmar plataformas, perfis e integrações no escopo aprovado.

Não homologar árvore fonte quando a entrega é um artefato diferente.

## 2. Automação primeiro

Antes de interação manual:

1. executar todos os comandos de `verification.release` no RC;
2. executar E2E codificado já existente para as jornadas críticas;
3. reunir relatórios, logs sanitizados e artefatos;
4. registrar em cada evidência o mesmo `rc`, `revision`, `build` e `checksum` do candidato, então executar `bm.py proof-map` para montar `comando/jornada -> prova automatizada -> RC -> lacuna`;
5. corrigir falha de produto antes de continuar.

Automação aprovada no mesmo RC prova o comportamento que observa. Não repetir manualmente a mesma jornada apenas para gerar outra evidência. Ainda explorar manualmente quando houver lacuna de UI visual, acessibilidade, usabilidade, integração/plataforma real, permissão nativa ou risco que o teste não observa.

Se regressão/E2E obrigatório não existir, isso vira lacuna planejada; não marcar automaticamente como falha quando o escopo aceita procedimento determinístico equivalente.

## 3. Matriz orientada a lacunas

Ler somente critérios/jornadas da spec, cabeçalhos/gates dos planos e resumos dos ledgers. Abrir detalhes quando uma prova ou falha exigir.

Criar `artifacts/qa/final/<data>/SUMMARY.md`:

```markdown
| ID | Plataforma | Perfil | Jornada | Prova automática | Lacuna manual | Resultado | Evidência |
|---|---|---|---|---|---|---|---|
```

Resultado: `passed | failed | blocked | not_run`. Fixar runner, versão, ambiente, horário e RC. Ler [`references/platform-runners.md`](references/platform-runners.md) somente para plataformas presentes.

## 4. Exploração manual das lacunas

Executar apenas lacunas do mapa:

- comportamento visual distinto e responsividade;
- acessibilidade e navegação real;
- permissões positivas/negativas não cobertas;
- validação, erro, cancelamento e recuperação não automatizados;
- persistência/reinício quando contratados;
- integração sandbox e comportamento nativo;
- plataforma secundária não comprovada por automação.

Preservar sessão por perfil. Preferir seletor acessível/estável; coordenada é último fallback. Evidência deve ser sanitizada.

Não alegar plataforma `not_run`. Fake não prova integração externa indispensável.

## 5. Triagem, fix e reteste

Para falha, registrar perfil, plataforma, jornada, passo, esperado, real, severidade, classificação e evidência.

- produto critical/important: executar `corrigir-bug` no mesmo workspace;
- ambiente: reparar harness e repetir;
- externo: validar contrato/degradação e bloquear quando indispensável;
- fora de escopo: registrar limitação, sem alterar RC.

Depois de código alterado: gerar novo RC, repetir automação afetada, lacuna manual correspondente, vizinhos de risco e smoke global. Após duas ondas de homologação sem convergir, `BLOQUEADO`.

Com telemetria habilitada, registrar somente a contagem de bugs de homologação e falhas de gate; detalhes continuam no resumo sanitizado, não na telemetria.

## 6. Veredito

`ACEITO` exige:

- `verification.release: passed` ou exceção de escopo explícita;
- E2E codificado aplicável aprovado;
- todas as lacunas obrigatórias executadas;
- nenhuma falha critical/important;
- plataformas/integrações indispensáveis reais executadas;
- evidências do RC final.

Caso contrário, `BLOQUEADO` com próximo requisito verificável. Não inventar “aceito com ressalvas”.

Ao aceitar, gravar `release.homologation: accepted` e `release.status: homologated`.

## 7. Manual conforme escopo

Resolver política com `bm.py policy`:

- `manual_pdf: none`: não gerar e não bloquear;
- `manual_pdf: quick_start`: gerar guia curto em Markdown e PDF;
- `manual_pdf: full`: gerar manual completo em Markdown e PDF;
- `manual_pdf: scope`: gerar o nível contratado na spec aprovada; sem contratação, não gerar.

Quando necessário, ler [`references/manual-delivery.md`](references/manual-delivery.md), criar `docs/manuals/manual-do-sistema.md`, gerar `artifacts/delivery/manual-do-sistema.pdf` e validar o PDF. Conversor ausente só bloqueia quando o manual é obrigatório no escopo.

## Saída

Informar RC, provas automatizadas, E2E, lacunas exploradas, matriz, bugs/retestes, veredito, manual quando aplicável e bloqueios. Se o host não invocar `corrigir-bug`, ler e cumprir seu contrato diretamente.
