---
name: homologar-sistema
description: Use para homologar explicitamente o release candidate ligado a uma mudança do Bianchini Method 1.0, combinando gates automatizados, jornadas reais e varredura visual.
---

# Homologar Sistema

**Anuncie:** "Homologando RC <id> no sistema real."

Resolva o binário empacotado `../_shared/bin/bm` no Unix ou `../_shared/bin/bm.exe` no Windows. Ausência bloqueia; não use fallback Python. O CLI e o pack do RC fornecem o contrato operacional necessário.

## Princípio obrigatório

Homologação possui dois gates complementares:

1. automação reproduzível para regressão, contratos e jornadas codificadas;
2. execução real de caixa-preta no release candidate, pela mesma superfície usada pelo usuário.

Quando existir interface, é obrigatório abrir e operar o release candidate no browser, emulador, simulador ou aplicativo final. Leitura de código, teste unitário, resposta de API, screenshot isolado ou E2E headless sem observação da interface não substitui a execução real.

Automação reduz repetição, mas não elimina o passe real. Um E2E pode servir também como execução real somente quando roda contra o RC atual, usa a interface final sem mock do comportamento validado, percorre a jornada completa e produz trace, vídeo ou screenshots observáveis.

## 1. Rota e pré-condições

1. Ler `.bianchini/STATE.md` e executar `bm model validate --repo <repo>`.
2. Exigir `.bianchini/changes/Cxxx-*/results/RELEASE.md` com `status: reviewed`. Confirmar `candidate.id`, `candidate.kind`, `revision`, `build`, `checksum`, `fingerprint`, `proof_ids` e `review_id`.
3. Homologar obrigatoriamente antes do `cycle-close`, na raiz única `.bianchini/changes/Cxxx-*`. Criar ali `results/HOMOLOGATION.md` com `schema_version: 1`, o mesmo `fingerprint`, `change`, cópia exata de `candidate` em `rc`, `status: running`, listas vazias de `gates`, `blockers`, `findings` e `manual_proofs`. Não sobrescrever uma homologação existente.
4. Compilar `bm context pack --repo <repo> --unit RC:<fingerprint>` e usar somente suas referências. `PACK_INCOMPLETE`, `PACK_TOO_LARGE` ou `STALE_EVIDENCE` bloqueia a homologação; não montar contexto manual.
5. Confirmar plataformas, perfis, integrações, journeys do `SYSTEM_MODEL.md` e critérios de aceite do escopo aprovado.
6. Preparar o ambiente executável, contas por perfil, dados determinísticos e sandboxes necessárias.

Não homologar árvore fonte quando a entrega é outro artefato. Se uma plataforma com interface não puder ser iniciada e operada, registrar `not_run` e declarar `BLOQUEADO`; nunca inferir aprovação pelo código.

## 2. Baseline automatizada

No RC atual:

1. confirmar que `bm verify release` já executou todos os gates integrados obrigatórios no candidato final e que a revisão do release aprovou os mesmos `proof_ids`;
2. reunir relatórios e logs sanitizados já vinculados ao RC, confirmando que evidência de mutação pertence ao commit/RC atual e ao seam exigido;
3. vincular cada evidência ao mesmo `rc`, `revision`, `build` e `checksum`;
4. executar `bm proof-map` para identificar o que a automação realmente prova;
5. corrigir falha de produto antes de avançar.

Homologação confirma as provas produzidas nos gates e depois opera o produto; não iniciar uma nova campanha unitária, de integração, E2E ou mutação dentro desta skill. Evidência obrigatória ausente ou obsoleta retorna ao `executar-plano`/`corrigir-bug` e mantém `BLOQUEADO`.

O mapa automatizado orienta prioridade, não decide sozinho o aceite. “Os testes passaram”, “o código parece correto” e “não há lacuna manual” não autorizam pular a execução real. Não escrever uma nova suíte apenas para evitar abrir o sistema.

Não iniciar novo planejamento, campanha de arquitetura ou redesign durante homologação. Divergência interna segue `change-policy`; somente mudança material comprovada invalida o pacote afetado.

## 3. Inventário e matriz de aceite

Ler critérios e jornadas das specs, plataformas/perfis do escopo, contratos dos planos e resultados registrados. Depois, inspecionar a navegação do RC para inventariar telas, menus, rotas e ações expostas.

Completar o `results/HOMOLOGATION.md` inicial em `changes`, sem apagar o frontmatter e as evidências anteriores:

```markdown
| ID | Plataforma | Perfil | Jornada ou ação | Automação | Execução real | Visual | Resultado | Evidência |
|---|---|---|---|---|---|---|---|---|
```

A matriz deve cobrir:

- todos os fluxos e ações disponíveis no RC que pertencem ao escopo;
- todos os fluxos críticos ponta a ponta e todas as ações primárias alcançáveis por cada perfil;
- ações secundárias com ao menos um smoke pelo limite público;
- telas e estados visuais distintos, sem repetir combinações equivalentes;
- integrações e plataformas indispensáveis;
- diferenças entre o escopo e o que está exposto no RC.

Resultado: `passed | failed | blocked | not_run`. Fixar runner, versão, ambiente, horário, perfil, viewport/dispositivo e fingerprint do RC.

## 4. Execução real obrigatória

Usar ferramenta já disponível no projeto ou host. Para web, preferir browser control, Playwright ou Cypress contra a aplicação em execução. Para mobile, usar emulador/simulador ou dispositivo de teste. Para desktop, abrir o artefato final. API e CLI usam sua interface pública real.

Para cada plataforma e perfil:

1. iniciar sessão limpa e realizar acesso, troca de perfil e logout quando aplicável;
2. percorrer todos os menus e rotas, executar cada ação primária dentro do escopo e fazer smoke das ações secundárias;
3. executar cada jornada crítica ponta a ponta, confirmando efeitos posteriores em listas, detalhes, dashboards ou persistência;
4. testar sucesso e ao menos uma condição relevante de validação, permissão ou erro;
5. testar cancelamento, voltar, recarregar, reiniciar ou recuperação quando o fluxo tiver estado persistente;
6. observar loading, vazio, erro e disabled quando forem alcançáveis ou críticos;
7. verificar console e rede no browser, logs nativos ou saída do processo para erros inesperados;
8. registrar evidência sanitizada nos marcos relevantes e em toda falha.

Preservar sessão por perfil durante a jornada. Preferir papel, nome acessível ou identificador estável; coordenada é último fallback. Não enviar mensagem real, cobrar, publicar, excluir dados reais ou executar ação destrutiva sem autorização explícita.

## 5. Varredura visual obrigatória

Toda entrega com interface recebe validação visual básica, mesmo sem design importado ou critério visual explícito. Observar a interface real, não apenas arquivos ou componentes isolados.

Em cada tela ou família visual distinta, verificar:

- hierarquia, clareza da ação principal e consistência entre telas;
- alinhamento, espaçamento, tipografia, contraste e legibilidade;
- corte, overflow, sobreposição, scroll indevido e elementos fora da área visível;
- responsividade em desktop e mobile quando a interface for responsiva; tablet somente quando contratado ou estruturalmente diferente;
- foco visível, teclado e nomes acessíveis aplicáveis;
- modais, menus, dropdowns, toasts e feedback após ações;
- loading, vazio, erro, sucesso e disabled relevantes;
- fidelidade ao `DESIGN_MANIFEST.json`, contrato, prototype e brand kit aprovados, quando existirem; arquivos visuais sem manifesto são ignorados.

Capturar screenshot de cada estado visual distinto necessário para provar o resultado e de toda falha. Não bloquear por preferência estética pessoal. Um achado visual bloqueia apenas quando viola o escopo, prejudica compreensão, acessibilidade, responsividade ou conclusão da jornada.

## 6. Triagem, correção e reteste

Para cada falha, registrar plataforma, perfil, jornada, passo, esperado, real, severidade, classificação e evidência.

- produto `critical` ou `high`: executar `corrigir-bug` no mesmo workspace;
- divergência de escopo, contrato público ou design aprovado: classificar com `change-policy`; `material_change` bloqueia apenas a área afetada e não vira fix loop;
- ambiente: reparar o harness e repetir;
- externo: validar contrato/degradação e bloquear quando indispensável;
- fora de escopo: registrar limitação sem ampliar o RC.

Após alteração de código, gerar novo RC e repetir:

1. automação afetada;
2. jornada real que falhou;
3. estados visuais e fluxos vizinhos de risco;
4. smoke global por plataforma e perfil afetado.

Não repetir a mesma homologação no mesmo estado. Falha de produto reabre a tarefa ou plano afetado com `bm plan reopen`, exige novo código, nova prova, novo release e novo fingerprint. Falha externa indispensável ou falha reproduzida sem correção segura declara `BLOQUEADO`. Com telemetria habilitada, registrar apenas contagem de bugs e falhas de gate.

## 7. Veredito

`ACEITO` exige:

- todos os gates obrigatórios do release com resultado `passed`;
- unitários, integração/contratos, regressão e E2E crítico do `verification.release` aprovados;
- evidência de mutação vigente quando `bm policy` marcar `selective` ou `required_selective`;
- todas as plataformas e perfis obrigatórios executados no RC real;
- todos os fluxos críticos e ações primárias da matriz com execução real `passed`;
- varredura visual concluída para toda interface aplicável;
- nenhuma falha `critical` ou `high` aberta, nem finding com `blocking: true` pendente;
- integrações indispensáveis validadas em ambiente real ou sandbox oficial;
- nenhuma linha obrigatória como `not_run`;
- evidências vinculadas ao fingerprint do RC final.

Caso contrário, `BLOQUEADO` com o próximo requisito verificável. Não inventar “aceito com ressalvas”.

Ao aceitar, registrar `status: accepted`, o `rc` exato, a lista completa de `gates`, cada entrada com `proof_id` do release e `result: passed`, nenhuma entrada em `blockers`, fingerprint e evidências em `HOMOLOGATION.md`. Para cada `manual_requirement` do release, registrar em `manual_proofs` um objeto com `plan`, `task`, path real em `evidence` e `evidence_sha256`. A sincronização de arquitetura, modelo e specs ocorre somente no `cycle-close`; homologação não edita `.bianchini/current/` nem o digest aprovado.

Uma linha não aplicável pertence à matriz explicativa, com justificativa de escopo; não substitui um gate obrigatório em `gates`. `findings` é lista explícita; severidades válidas são `critical`, `high`, `medium`, `low` e `info`. Estados: `open`, `resolved`, `accepted`. Aceitar risco baixo não resolve finding bloqueante. Resolução exige `resolution_evidence` com caminho de arquivo real e `resolution_sha256` dos bytes atuais.

## 8. Manual conforme escopo

Resolver política com `bm policy`:

- `manual_pdf: none`: não gerar e não bloquear;
- `manual_pdf: quick_start`: gerar guia curto em Markdown e PDF;
- `manual_pdf: full`: gerar manual completo em Markdown e PDF;
- `manual_pdf: scope`: gerar o nível contratado na spec aprovada; sem contratação, não gerar.

Quando necessário, ler [`references/manual-delivery.md`](references/manual-delivery.md), criar o manual dentro de `.bianchini/changes/Cxxx-*/results/` e validar o PDF. Conversor ausente só bloqueia quando o manual é obrigatório no escopo.

## Saída

Informar RC, baseline automatizada, plataformas/perfis realmente operados, fluxos e ações executados, varredura visual, matriz, bugs/retestes, veredito, manual quando aplicável e bloqueios. Se o host não invocar `corrigir-bug`, ler e cumprir seu contrato diretamente.
