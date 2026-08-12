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

- objetivo e estado atual relevante;
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
- cria ou retoma `.superpowers/bianchini/direct/<slug>/BRIEF.md`;
- mantém `PROGRESS.md`, `RESULT.md` e `.state.json` no mesmo scratch ignorado;
- não cria `PROJECT_STATE.md`, spec ou árvore `docs/bianchini/`.

Nunca versionar o scratch. `/.superpowers/` permanece no `.gitignore`.

### 3. Implementar continuamente

Use zero subagentes, zero revisor por microtarefa, zero task brief por alteração e zero review package por passo. Trabalhe em uma sequência contínua e mantenha o menor diff correto.

- Bug, regra de negócio, cálculo, transformação, parser, permissão ou máquina de estados: aplicar RED/GREEN no seam afetado.
- Mudança visual: validar no browser e registrar screenshot ou regressão visual quando o ambiente permitir.
- Mudança mecânica ou comportamental simples: executar checks focados e depois a regressão proporcional.
- Descobrir comandos no próprio repositório; não inventar comandos nem criar adapter por linguagem.
- Não criar abstração para antecipar escopo inexistente.
- Não instalar coverage, mutation testing, framework E2E, analisador arquitetural ou ferramenta externa de qualidade por padrão.

Após um checkpoint relevante, registre fatos reproduzíveis:

```bash
python3 <bm.py> direct checkpoint \
  --repo <repo> \
  --slug <slug> \
  --checkpoint "<resultado concluído>" \
  --changed-file <arquivo> \
  --command "<comando executado>" \
  --result-entry "<resultado observado>" \
  --verification passed \
  --next-action "<próxima ação única>"
```

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

Use `blocked` quando faltar autoridade ou condição externa; use `escalated` se a execução revelar complexidade estrutural. Não faça push, merge, publicação, deploy ou instalação global sem autorização explícita. Não use reset destrutivo, `git clean -fdx` ou remova trabalho alheio.

## Resposta final

Informe comportamento entregue, arquivos alterados, verificações e resultados, limitações, branch e o caminho do `RESULT.md`. Diferencie claramente o que foi implementado do que apenas foi observado.
