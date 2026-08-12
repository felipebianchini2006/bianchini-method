---
name: executar-direto
description: Use quando o usuário solicitar a implementação estruturada de um projeto pequeno ou de uma entrega coesa sem planejamento SDD completo.
disable-model-invocation: true
---

# Executar Direto

**Anuncie:** "Executando diretamente com brief compacto, branch isolada e verificação proporcional ao risco."

Use esta skill somente por invocação explícita de `/executar-direto`. Leia [`../_shared/METHOD_CONTRACT.md`](../_shared/METHOD_CONTRACT.md) e resolva `bm.py` pelo mesmo contrato. É proibido invocar Superpowers automaticamente, instalar Agency Agents ou acionar outra metodologia.

## Quando usar

A execução direta é adequada quando existe um único objetivo coeso, com critérios de aceite claros, impacto localizado, uma sequência curta que pode ser implementada e verificada na sessão e risco baixo ou médio. Ela pode atravessar vários arquivos do mesmo fluxo, mas não pode esconder subsistemas independentes. Uma integração externa simples só permanece direta quando reutiliza padrão comprovado no repositório.

Escalone antes de alterar código quando houver qualquer um destes sinais:

- autenticação, pagamento ou webhook novos;
- multi-tenant, RLS, migração de dados ou infraestrutura sensível;
- secrets/IAM, concorrência relevante ou sincronização offline;
- geolocalização crítica, operação destrutiva ou arquitetura nova;
- diferenças substanciais entre plataformas;
- regra de negócio ambígua;
- risco alto/crítico ou mais de um subsistema independente.

No escalonamento, preserve o trabalho válido, pare antes do risco alto e gere apenas o handoff compacto em `RESULT.md`, com fatos, decisões, arquivos, comandos e bloqueios. Informe `Status: escalado` e use `/sdd-planning` como próximo passo. Não crie spec central, `PLANNING_REVIEW`, planos parciais ou manual PDF.

## Fluxo

### 1. Capturar contexto uma vez

Leia uma vez `AGENTS.md`, `CLAUDE.md`, README, manifests, lockfiles, scripts do projeto, CI, `git status`, histórico Git recente e os arquivos diretamente ligados ao objetivo, quando existirem. Leia arquivos adicionais somente para confirmar dependências reais; não faça análise completa do repositório.

Com isso, preencha:

- objetivo e estado atual relevante (`--current-state` é obrigatório e deve conter síntese factual da leitura localizada; texto genérico como "a confirmar" é rejeitado);
- escopo e não objetivos;
- critérios de aceite;
- arquivos/interfaces prováveis;
- risco, tipo de mudança e hazards;
- comandos de verificação afetados.

Não faça pesquisa ampla nem varra documentação viva inteira quando uma leitura localizada bastar. Não inicie entrevista; pergunte somente quando uma ambiguidade impedir a implementação correta.

### 2. Iniciar ou retomar

Execute `bm.py direct start` antes de editar código:

```bash
python3 <bm.py> direct start \
  --repo <repo> \
  --slug <objetivo-curto> \
  --objective "<objetivo>" \
  --scope "<escopo coeso>" \
  --current-state "<síntese factual do estado atual>" \
  --acceptance "<critério verificável>" \
  --verification "<comando afetado>" \
  --risk low \
  --change-kind behavioral
```

Repita `--acceptance`, `--verification`, `--non-objective`, `--likely-file`, `--hazard` e `--related-change` quando necessário. Use `--subsystems` para declarar a quantidade real de subsistemas independentes.
Ao preservar trabalho anterior ou escalar, repita também `--command` e `--result-entry` para registrar comandos e fatos já confirmados.

O comando:

- bloqueia detached HEAD;
- bloqueia branch principal suja;
- bloqueia mudanças não reconhecidas em feature branch;
- cria `bm/direct/<slug>` quando parte de `main` ou `master` limpas;
- não cria worktree por padrão; só reutilize uma quando o ambiente ou repositório já a exigir;
- registra `/.superpowers/` em `.git/info/exclude` sem alterar o `.gitignore` do projeto e confirma que `BRIEF.md`, `PROGRESS.md`, `RESULT.md` e `.state.json` não aparecem no `git status`;
- cria ou retoma `.superpowers/bianchini/direct/<slug>/BRIEF.md`;
- mantém `PROGRESS.md`, `RESULT.md` e `.state.json` no mesmo scratch ignorado;
- calcula um digest de identidade do brief (objetivo, estado atual, escopo, não objetivos, aceite, risco, tipo, hazards, subsistemas e comandos de verificação);
- não cria `PROJECT_STATE.md`, spec ou árvore `docs/bianchini/`.

Nunca versionar o scratch. Na retomada, digest igual retoma; digest diferente bloqueia — use um novo slug ou atualize explicitamente o brief com `--update-brief`. Nunca retome uma execução nova sobre um `BRIEF.md` antigo.

### 3. Implementar continuamente

Use zero subagentes, zero revisor por microtarefa, zero task brief por alteração e zero review package por passo. Trabalhe em uma sequência contínua e mantenha o menor diff correto.

- Bug, regra de negócio, cálculo, transformação, parser, permissão ou máquina de estados: aplicar RED/GREEN no seam afetado.
- Mudança visual: validar no browser e registrar screenshot ou regressão visual quando o ambiente permitir.
- Mudança mecânica ou comportamental simples: executar checks focados e depois a regressão proporcional.
- Descobrir comandos no próprio repositório; não inventar comandos nem criar adapter por linguagem.
- Não criar abstração para antecipar escopo inexistente.
- Não instalar coverage, mutation testing, framework E2E, analisador arquitetural ou ferramenta externa de qualidade por padrão.

Após um checkpoint relevante, registre fatos reproduzíveis com evidência estruturada:

```bash
python3 <bm.py> direct checkpoint \
  --repo <repo> \
  --slug <slug> \
  --checkpoint "<resultado concluído>" \
  --changed-file <arquivo> \
  --command "<comando executado>" \
  --result-entry "<resultado observado>" \
  --evidence '{"kind": "command", "command": "<comando>", "exit_code": 0, "status": "passed", "summary": "<resumo>"}' \
  --verification passed \
  --next-action "<próxima ação única>"
```

`--evidence` aceita `kind: command | browser | manual | screenshot`. Evidência de comando exige `command` e `exit_code` (status `passed` só com `exit_code: 0`); browser, screenshot e procedimento manual exigem `evidence` com caminho ou descrição determinística e podem declarar `check_id` para que uma nova tentativa do mesmo check substitua a anterior. Cada evidência é carimbada com o digest do brief e o fingerprint da árvore de trabalho no momento do registro. `--verification passed` sem ao menos uma evidência aprovada é bloqueado. `--update-brief` invalida verificação e evidências anteriores.

Em retomada, execute `bm.py direct status --repo <repo> --slug <slug>` e leia `PROGRESS.md`; não redescubra o projeto inteiro.

### 4. Revisar e concluir

Antes de concluir:

1. comparar o diff com o `BRIEF.md`;
2. revisar correção, segurança, regressões e simplicidade;
3. executar testes afetados, typecheck/compilação, lint, build, smoke e verificação visual somente quando aplicáveis e proporcionais;
4. confirmar que nenhum requisito foi silenciosamente adiado;
5. registrar limitações e itens encontrados fora de escopo.

Faça uma única auto-revisão final em dois eixos: **Brief**, confirmando todos os critérios de aceite; e **Qualidade**, confirmando correção, simplicidade, compatibilidade, testes e ausência de escopo extra. Um revisor independente só é justificável quando vários módulos relevantes, risco médio significativo, contrato não confirmado ou uma falha exigirem julgamento; risco alto sempre escala.

Finalize com:

```bash
python3 <bm.py> direct finish \
  --repo <repo> \
  --slug <slug> \
  --status completed \
  --behavior "<comportamento entregue>" \
  --verification "<comando e resultado>" \
  --next-action "Revisão humana e entrega local."
```

`--status completed` usa a evidência estruturada salva nos checkpoints, não frase livre: exige estado `active`, verificação `passed`, cada comando de verificação planejado no brief coberto pela evidência mais recente com `status: passed` e `exit_code: 0` (teste automatizado, typecheck, lint, build, smoke) ou por evidência browser, screenshot ou procedimento manual determinístico, ao menos um comportamento entregue e nenhum bloqueio aberto. Evidência atual `failed`, `blocked` ou `not_run` bloqueia, assim como evidência obsoleta: toda evidência vigente precisa carregar o digest do brief atual e o fingerprint da árvore final do código; qualquer alteração posterior ao registro exige reexecutar as verificações e registrar novo checkpoint. Comando planejado não aplicável só pode ser dispensado explicitamente com `--waive-verification "comando: justificativa"`, registrado nas limitações. O CLI também compara o `git status` com os arquivos registrados: alteração não registrada bloqueia; use checkpoint `--changed-file` ou aceite explicitamente com `--accept-unrecorded "caminho: justificativa"`. `--status blocked` e `--status escalated` exigem motivo via `--blocker` ou `--limitation`.

Use `blocked` quando faltar autoridade ou condição externa; use `escalated` se a execução revelar complexidade estrutural. Ambos podem registrar verificações incompletas, mas nunca declarar conclusão. As únicas transições permitidas são `active → completed`, `active → blocked` e `active → escalated`; `completed`, `blocked` e `escalated` são terminais e `finish` não pode ser repetido sobre eles. Execução escalada nunca vira concluída: continue por `/sdd-planning` ou um novo slug. Somente `blocked` aceita `direct reopen --slug <slug> --next-action "<ação>"`, que preserva o `RESULT.md` anterior antes de reabrir.

Não faça push, merge, publicação, deploy ou instalação global sem autorização explícita. Não use reset destrutivo, `git clean -fdx` ou remova trabalho alheio.

Os contratos internos de `skills/_shared/agents/` pertencem ao método completo: o modo direto não os carrega. O revisor independente excepcional descrito acima não usa o catálogo Agency Agents.

## Resposta final

Informe comportamento entregue, arquivos alterados, verificações e resultados, limitações, branch e o caminho do `RESULT.md`. Diferencie claramente o que foi implementado do que apenas foi observado.
