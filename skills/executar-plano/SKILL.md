---
name: executar-plano
description: Use para executar planos aprovados do Bianchini Method com prova fresca, revisão vinculada ao código e fechamento seguro.
---

# Executar Plano

**Anuncie:** "Executando <planos> do Bianchini Method no modo <grouped|slice|strict>."

Argumentos: `all`, `N`, `N-M`. Sem argumento, mostrar `/status-projeto`. Executar todos somente quando o pedido atual for explícito.

Resolva `../_shared/bin/bm` no Unix ou `../_shared/bin/bm.exe` no Windows. Ausência bloqueia. Não use fallback Python. O backend Go é a única autoridade de estado, prova, revisão e conclusão. Hosts como Codex, Claude ou Grok podem mudar apresentação e distribuição do trabalho, nunca o significado de `completed`.

## 1. Preflight

1. Ler `.bianchini/STATE.md`. Sem estado válido, orientar `/migrar-bianchini` ou `/sdd-planning`.
2. Confirmar pacote aprovado, `COHERENCE.md` atual, planos solicitados aprovados e ausência de `stale_plans` que afetem a onda.
3. Executar:

```bash
bm model validate --repo <repo> --change C001
bm roadmap next-wave --repo <repo> --change C001 --format json
```

4. Executar somente unidades retornadas em `parallel_units`. Dependências ficam na ordem declarada.
5. Não reabrir planejamento por preferência interna. Alteração material de escopo, contrato público, dado, migration, jornada, efeito ou invariante volta para impacto/aprovação.
6. Executar `git status --porcelain` e preservar toda mudança preexistente. O pacote de planejamento aprovado deve estar em commit local atômico antes da implementação.

## 2. Estratégia Git simples

No uso solo, trabalhe no checkout primário e na branch já autorizada pelo repositório. Se a política do projeto usa `main` diretamente, não crie branch ou worktree intermediário.

Crie worktree somente quando houver isolamento simultâneo real, pedido explícito ou risco de colisão entre executores:

```bash
bm workspace create --repo <repo> --change C001 --plan P01
```

Não crie um worktree por fase por padrão. Ao terminar e integrar uma branch legada `bm/c001-p01`, limpe somente worktrees limpos e branches já ancestrais do `HEAD` atual:

```bash
bm workspace finish --repo <repo> --change C001
```

O comando recusa workspace sujo ou branch não integrada. Nunca apague trabalho pendente para satisfazer limpeza.

## 3. Contexto e execução

Antes de editar cada tarefa:

```bash
bm context pack --repo <repo> --unit C001/P01/T01
```

Valide o pack retornado. `PACK_INCOMPLETE`, `PACK_TOO_LARGE` ou `STALE_EVIDENCE` bloqueia a unidade; regenere o pack sem reler o contrato completo nem criar fallback manual.

Execute somente a tarefa tipada do frontmatter do plano. O corpo Markdown é explicação, não autoridade. O `task-brief` também deve vir do contrato tipado; headings soltos não criam tarefa.

As tarefas da mesma onda podem avançar em paralelo apenas sem sobreposição de arquivos, ownership ou efeitos. Não crie paralelismo para cumprir uma quantidade artificial de agentes.

Ordem de decisão interna:

```text
decisão aprovada
→ padrão já existente no repositório
→ stack atual
→ documentação oficial necessária
→ menor mudança reversível que atende ao aceite
```

Não implemente necessidade futura. Não crie camada, serviço, abstração ou framework sem requisito atual ou redução demonstrável de risco. Commits devem ser atômicos.

Quando houver execução realmente paralela, ferramentas disponíveis e autorização do host, use [`../_shared/agents/implementation-worker.md`](../_shared/agents/implementation-worker.md) com ownership sem sobreposição. O worker é opcional; nunca espere sua criação para prosseguir no checkout primário.

## 4. Prova da tarefa

Cada tarefa schema 2 declara `verify` com:

- `kind: command`: preferir `argv` estruturado, `cwd`, `timeout_seconds` e `proves`;
- `kind: procedure`: descrever o procedimento e fornecer um artefato real por `--evidence`.

Execute o comando pelo núcleo:

```bash
bm verify task --repo <repo> --change C001 --plan P01 --task T01 \
  --context-pack .bianchini/.runtime/context/C001-P01-T01.json
```

Para procedimento manual:

```bash
bm verify task --repo <repo> --change C001 --plan P01 --task T01 \
  --context-pack .bianchini/.runtime/context/C001-P01-T01.json \
  --evidence artifacts/evidence/T01.png
```

O núcleo registra argv, cwd, timeout, exit code, hashes de saída, revisão Git, fingerprint do código, digest do pacote e do context pack. Texto como "testes passaram" não é prova.

Uma falha persiste. Repetir a mesma prova no mesmo estado exige `--retry-reason`; não existe retry automático infinito. Prova verde só é reutilizada com `verify.cache: deterministic` e entradas controladas. O padrão fresh executa novamente para ambiente vivo ou desconhecido.

Na tarefa, execute a menor prova pública relacionada. Não execute E2E completo ou mutação por microtarefa; essas campanhas pertencem ao gate do plano ou do release quando declaradas.

## 5. Revisão limitada e correção

Revise na cadência do modo:

- `grouped`: uma revisão no gate do plano;
- `slice`: cada tarefa Txx representa uma slice vertical; revisão por Txx;
- `strict`: uma revisão por tarefa crítica.

Use [`../_shared/agents/plan-reviewer.md`](../_shared/agents/plan-reviewer.md) como contrato da revisão. O revisor recebe requisito, diff e `proof_id`. Avalia contrato, correção, segurança, simplicidade, compatibilidade e testes. Não redesenha por preferência. Entregue o caminho do arquivo de saída da revisão; em `grouped`, nunca revise por microtarefa.

Em risco alto ou crítico envolvendo autenticação, autorização, pagamentos, privacidade, segredos, migração destrutiva ou integridade, aplique a passagem somente leitura de [`../_shared/agents/security-reviewer.md`](../_shared/agents/security-reviewer.md). Não executá-la em tarefa comum. Entregue o caminho do arquivo de saída do parecer e trate findings no mesmo ciclo limitado.

Registre o veredito:

```bash
bm verify review --repo <repo> --change C001 --scope task \
  --plan P01 --task T01 --reviewer <identidade> --verdict approved \
  --proof <proof-id>
```

Se houver defeito material, use `--verdict changes_requested --finding <JSON>` com target, observed, requirement, severity, evidence (arquivo real) e expected_fix. RED não é obrigatório para inspeção concreta ou evidência visual. Após corrigir, gere provas apropriadas e aprove com `--resolves-review <id>`. Não espere outro agente por polling. Cada chamada termina com um veredito persistido. O loop continua somente quando existe mudança concreta e encerra em aprovação, alteração material ou bloqueio real.

Fix round é hipótese, não entrega. Identifique o `risk_seam` estável e passe `--risk-seam` e `--consecutive-seam-findings` à política; renomear a tarefa não reinicia a contagem. Repetir correções sem nova evidência aciona o limite do perfil e termina em bloqueio explícito, nunca em loop silencioso.

Finding novo depois de uma conclusão válida reabre explicitamente a unidade:

```bash
bm plan reopen --repo <repo> --change C001 --plan P01 \
  --reason "finding posterior ao gate do plano"
bm plan reopen --repo <repo> --change C001 --plan P01 --task T01 \
  --reason "defeito reproduzido pela interface pública"
```

Quando o plano ainda não foi concluído, use apenas a segunda chamada. Dependentes concluídos devem ser reabertos primeiro; o núcleo recusa criar um estado impossível.

Não reescreva histórico para esconder a conclusão anterior. A auditoria de reabertura é preservada.

## 6. Concluir tarefa e plano

Após prova verde vigente, conclua. Em grouped, omita `--review`; em strict/slice, forneça a revisão correspondente ao mesmo fingerprint:

```bash
bm plan complete --repo <repo> --change C001 --plan P01 --task T01 \
  --context-pack .bianchini/.runtime/context/C001-P01-T01.json \
  --result "comportamento entregue" \
  --proof <proof-id> --review <review-id>
```

Depois das tarefas, execute todos os gates do plano. grouped exige a revisão integrada abaixo. strict/slice já possuem revisão focal e não exigem outra revisão do plano:

```bash
bm verify plan --repo <repo> --change C001 --plan P01
bm verify review --repo <repo> --change C001 --scope plan --plan P01 \
  --reviewer <identidade> --verdict approved --proof <proof-id>
bm plan complete --repo <repo> --change C001 --plan P01 \
  --actual-delta <delta-real.json> --result "plano entregue" \
  --proof <proof-id> --review <review-id> \
  --completed-task T01 --completed-task T02
```

`--completed-task T01` é compatibilidade explícita e, quando usado, deve listar todas as tarefas na ordem aprovada. Ele nunca substitui resultados, provas ou revisão persistidos.

`completed` significa que o núcleo validou os artefatos, não que o executor declarou sucesso. Evidência narrativa continua permitida apenas no schema legado e deve ser reportada como garantia legada.

## 7. Release, homologação e fechamento

Depois do último plano, execute os gates integrados dos planos sobre o candidato final, preservando as provas históricas das tarefas:

```bash
bm verify release --repo <repo> --change C001 \
  --build <arquivo-real> --checksum <sha256-esperado> --delivery ready
bm verify review --repo <repo> --change C001 --scope release \
  --reviewer <identidade> --verdict approved \
  --proof <proof-id> [--proof <proof-id> ...]
```

O release produz `results/RELEASE.md` com RC, fingerprint e provas. Homologue esse RC enquanto a mudança ainda está em `.bianchini/changes/`. Procedimentos manuais exigem evidência do mesmo RC. Só depois registre `HOMOLOGATION.md` aceita.

Commite o código e os artefatos finais. Então execute:

```bash
bm cycle-close --repo <repo> --change C001
```

O fechamento bloqueia se o release não estiver revisado, se a prova estiver stale, se a homologação não pertencer ao RC exato, se houver blocker ou se o candidato não for ancestral do `HEAD` salvo apenas por commits de `.bianchini`.

Projetos antigos não são declarados inválidos em massa. Antes de confiar em resultados legados, execute uma auditoria final de release; preserve o histórico e reabra somente unidades com falha reproduzida.

## Saída

Informe: mudança/plano, tarefas concluídas, provas e revisões, fingerprint do RC, homologação, commits, integração, limpeza de worktrees, bloqueios reais e o que ainda depende de ambiente externo. Nunca misture código validado, deploy e homologação humana.
