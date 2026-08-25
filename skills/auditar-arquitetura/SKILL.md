---
name: auditar-arquitetura
description: Use somente quando o usuário invocar /auditar-arquitetura ou pedir explicitamente uma auditoria arquitetural. É manual, report-only e não ativa por risco ou pela presença do Bianchini Method 0.4.
disable-model-invocation: true
---

# Auditar Arquitetura

**Anuncie:** "Auditando hotspots e mudanças recentes; o resultado será somente um relatório."

Leia [`../_shared/METHOD_CONTRACT.md`](../_shared/METHOD_CONTRACT.md) e resolva `bm.py`.

## Contrato

Esta skill é manual, report-only e não implementa correções. Perfil `full`, risco alto/crítico e achados de melhoria não disparam a skill nem bloqueiam planejamento, aprovação ou entrega por si só.

Um defeito funcional, de segurança ou integridade diretamente demonstrável não é uma “melhoria arquitetural”: registrá-lo separadamente, com reprodução/evidência, e encaminhá-lo ao fluxo `corrigir-bug` ou ao gate responsável. Não alterar código, status de plano nem aprovação durante a auditoria.

## Rota

1. Se existir `.bianchini/STATE.md`, executar `bm.py model validate --repo <repo>` e usar somente seus ponteiros atuais.
2. Sem `.bianchini`, auditar apenas o intervalo Git solicitado; não inicializar nem migrar o método.
3. Se o repositório não tiver Git ou histórico suficiente, declarar a limitação e auditar apenas o delta fornecido explicitamente.

## Coleta econômica

Começar pelo histórico, antes de ler a spec inteira:

1. identificar base/HEAD ou período solicitado;
2. usar `git log --stat`, `git log --name-only` e `git diff --name-only` para localizar arquivos recentemente alterados;
3. contar frequência de mudança por arquivo e diretório para encontrar hotspots;
4. priorizar arquivos que combinam frequência, tamanho do delta, dependências e criticidade;
5. abrir os arquivos alterados, testes e contratos adjacentes necessários para confirmar cada hipótese;
6. consultar spec/ADR somente nas seções referenciadas pelo delta.

Não classificar arquivo como problema apenas porque muda muito. Histórico aponta onde investigar; evidência no código/contrato sustenta o candidato.

## Análise

Procurar oportunidades locais e verificáveis em:

- limites de responsabilidade e acoplamento;
- contratos públicos, estados, erros e compatibilidade;
- ownership de dados, invariantes, migração e concorrência;
- trust boundaries, autorização, segredos e privacidade;
- resiliência, observabilidade, deploy e recuperação;
- testabilidade por interfaces estáveis;
- duplicação ou abstração que aumente custo real de mudança.

Evitar reescrita ampla, arquitetura futura e preferência estética. Uma proposta deve reduzir um custo ou risco observado.

Quando o delta tocar autenticação, autorização, pagamentos, segredos ou outra área sensível, a análise de trust boundaries pode seguir o contrato somente leitura [`../_shared/agents/security-reviewer.md`](../_shared/agents/security-reviewer.md), passando ao subagente apenas o caminho do contrato, os arquivos do delta e o caminho do parecer; não copiar o conteúdo do contrato para o prompt.

## Classificação dos candidatos

Ordenar pelo nível de confiança:

- `Strong`: evidência direta no delta/histórico e benefício claro;
- `Worth exploring`: sinal consistente, mas exige experimento ou medição curta;
- `Speculative`: hipótese plausível sem evidência suficiente; não recomendar execução.

Cada candidato deve conter exatamente os campos:

- `Problema`: comportamento estrutural observado e evidência com caminhos;
- `Proposta`: menor mudança capaz de testar ou corrigir o problema;
- `Benefício`: custo, risco ou complexidade reduzidos;
- `Risco`: regressão, migração, compatibilidade e custo da proposta;
- `Prioridade`: `P0 | P1 | P2 | P3`, justificada.

Separar uma seção `Defeitos funcionais diretos` dos candidatos estruturais. Para cada defeito, informar reprodução, impacto e gate que deve bloquear; não sugerir que a auditoria arquitetural o aprovou ou corrigiu.

## Relatório

Quando houver mudança ativa, criar `.bianchini/changes/Cxxx-*/results/ARCHITECTURE_AUDIT.md`; sem mudança ativa, devolver o relatório no destino explicitamente pedido pelo usuário. Incluir:

- intervalo Git, data e limitações;
- arquivos alterados e hotspots priorizados;
- candidatos `Strong`, `Worth exploring` e `Speculative`;
- defeitos funcionais diretos separados;
- próximos experimentos pequenos;
- declaração `REPORT_ONLY`.

HTML é opcional e só pode ser gerado quando o usuário pedir explicitamente. Nesse caso, criar uma versão estática ao lado do Markdown, escapar conteúdo dinâmico e não carregar scripts, fontes ou recursos remotos.

Não alterar `STATE.md`, `COHERENCE.md`, aprovação ou status de plano. Nunca usar `blocked` por candidato de melhoria.

## Saída

Informar intervalo analisado, hotspots, candidatos por confiança, defeitos diretos, limitações e caminhos dos relatórios. Não implementar, aprovar, fazer push ou publicar.
