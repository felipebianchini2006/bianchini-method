# Convergência Codex — compatibilidade legada

Contrato mantido somente para retomar sidecars criados antes do executor canônico. Execuções novas usam `bm verify`, `bm plan complete` e `bm plan reopen`. Este documento não define conclusão fora do núcleo Go.

De `bm policy`, preservar modo, cadência e garantia. Ignorar somente limites de fix rounds e breaker do método base. Quando correção de bug ou homologação acionarem revisão, fix loop, breaker, redesign ou decisão de parada, este contrato prevalece.

## Sidecar

Caminho canônico:

```text
artifacts/bianchini/<planning_version>/codex/convergence/<plan_id>/<unit_id>.json
```

`review_guard.py` deriva caminho de repository root validado, `planning_version`, `plan_id` e `unit_id`. A identidade imutável vem do SHA-256 da unidade emitido por `task-brief`, não do nome exibido. Outro sidecar com a mesma identidade no plano é rejeitado. IDs aceitam somente letras ASCII, números, ponto, sublinhado e hífen. Paths devem permanecer no repositório real; traversal e symlink são inválidos.

Escrita usa arquivo temporário no mesmo diretório, flush, `fsync`, troca atômica e `fsync` do diretório. Sidecar válido anterior vira `.bak`. JSON principal truncado ou inválido é recuperado pelo backup válido. Migração de versão, quando necessária, é genérica, idempotente e preserva identidade, evidências e histórico.

## Fases e transições

Fases obrigatórias:

- `review_frozen`;
- `fixing`;
- `awaiting_review`;
- `redesigning`;
- `parked`;
- `completed`;
- `stopped`.

Tabela fechada:

| Fase atual | Comando | Próxima fase | Condição |
| --- | --- | --- | --- |
| inexistente | `freeze` | `review_frozen` | primeira revisão válida no `HEAD` atual |
| `review_frozen` | `submit-delta --kind implementation` | `awaiting_review` | zero blockers; primeira submissão de delta |
| `review_frozen` | `submit-delta --kind verification` | `awaiting_review` | revisão limpa após o único implementation; delta atual contém somente testes, fixtures, docs ou artifacts |
| `review_frozen` | `fix` | `fixing` | blocker congelado aberto; menos de dois fix rounds |
| `fixing` | `submit-delta --kind fix` | `awaiting_review` | commit do fix submetido |
| `review_frozen` | `redesign` | `redesigning` | blocker estrutural aberto; dois fixes; redesign disponível; seam idêntico |
| `redesigning` | `submit-delta --kind redesign` | `awaiting_review` | commit do redesign submetido |
| `awaiting_review` | `review` | `review_frozen` | revisão aceita; próximo passo ainda executável ou aprovação disponível |
| `awaiting_review` | `review` | `parked` | blocker aberto sem fix ou redesign disponível |
| `review_frozen` | `complete` | `completed` | zero blockers abertos; gates obrigatórios registrados e aprovados |
| `completed` | `reopen` | `awaiting_review` | `HEAD` posterior ao último review e motivo não vazio |
| qualquer não terminal | `stop` | `stopped` | categoria permitida com evidência completa |

`stopped` é terminal. `completed` aceita somente `reopen`; outros comandos mutáveis falham. Qualquer transição ausente da tabela falha. `parked` não significa concluída; trabalho independente continua.

A parada é isolada por unidade. `parked`, bloqueio local ou `stopped` de uma unidade não interrompem outras unidades sem dependência. A execução global só termina após entrega concluída ou quando todo trabalho restante estiver terminal ou estacionado sem ação segura disponível.

`gate` e `decision` registram dados sem mudar fase e são aceitos somente enquanto a unidade está executável. `status` e `migrate` preservam fase; podem validar estado terminal.

`freeze` cria sidecar e primeira revisão atomicamente. `review` só executa em `awaiting_review`. Fix ou redesign só executam em `review_frozen`. Dois fixes consecutivos sem `submit-delta --kind fix` e `review` intermediários são inválidos. Renomear unidade ou seam não cria nova identidade nem reseta contador.

`submit-delta --kind implementation` cobre o único delta de implementação subsequente à primeira revisão, somente quando freeze não deixou blocker e nenhum delta anterior foi submetido. Depois de uma revisão limpa desse implementation, pode existir um único `submit-delta --kind verification`; o guard rejeita esse delta se qualquer path desde `last_review_head` alterar código de produção. Verification aceita somente testes, fixtures, docs ou artifacts e sempre entra em `awaiting_review`; não é atalho para `complete`. Após fix ou redesign, usar kind correspondente antes de `review`.

## Blocker congelado

Antes de cada revisão, gerar entrada determinística com `bm review-package --cwd <workspace> --base <last_review_head> --head HEAD --brief <task-brief.md> --report <report.md> --output <review-package.md>`. Entregar ao revisor somente esse pacote, o sidecar da unidade e o contrato `plan-reviewer-codex.md`. A primeira revisão usa a base da unidade; revisões seguintes usam exatamente o delta submetido.

Primeira revisão congela blockers. Blocker exige:

- `approved_requirement` igual a um identificador ou trecho existente no `task-brief` congelado;
- `proof_id` emitido pelo guard, com falha real no `HEAD` revisado;
- impacto material;
- cenário alcançável;
- `risk_seam`;
- metadados estruturais.

O guard consolida findings pela causa raiz. Todo defeito material comprovado contra requisito aprovado permanece blocker; quantidade não muda sua classificação. Duplicatas da mesma causa e requisito ausente do `task-brief` viram `deferred_hardening`.

Forma não estrutural:

```json
{
  "risk_seam": "public-api",
  "structural": false,
  "structural_class": null,
  "structural_evidence": null
}
```

Blocker estrutural usa `structural: true`, `structural_evidence` com `proof_id` vermelho no commit revisado e uma destas classes fechadas:

- `architecture_boundary`;
- `data_model`;
- `public_contract`;
- `state_machine`;
- `cross_cutting_invariant`.

Classe livre, evidência textual vaga ou combinação inconsistente é inválida.

Finding não crítico vira `deferred_hardening`. Blocker aberto nunca vira hardening silenciosamente. Revisão seguinte cobre somente blockers congelados abertos e regressões causadas pelo delta atual. Evidência nova posterior à conclusão exige `reopen`, preservando o histórico anterior.

## Regressão do delta

Novo `delta_regression` só vira blocker quando todas as provas existirem:

1. `delta_base` e `delta_head` resolvem para commits Git reais do repositório validado;
2. `delta_base` coincide com `last_review_head`;
3. `delta_head` coincide com `HEAD` atual;
4. `delta_head` descende de `delta_base`;
5. arquivo do finding está confinado ao repositório;
6. localização aponta linha adicionada, modificada ou removida pelo diff; linha apenas de contexto não vale;
7. `base_proof_id` e `head_proof_id` foram emitidos pelo guard para o mesmo argv e cwd;
8. proof da base pertence a `delta_base` e tem exit code real `0`; proof do head pertence a `delta_head` e tem exit code real diferente de `0`;
9. explicação causal liga mudança do delta ao defeito.

Rename deve ser resolvido pelo diff Git real. Linha removida referencia lado base e linha removida. Arquivo fora do diff, defeito preexistente, base e head com mesmo resultado ou cadeia Git inválida convertem finding para hardening.

Guard nunca executa texto arbitrário do finding. O comando `proof` executa argv estruturado com `shell=False`, em checkout isolado do commit, cwd confinado e timeout obrigatório. Persiste comando, cwd, exit code real, commit e hashes SHA-256 dos bytes de stdout e stderr. Cada registro recebe assinatura guard-owned; gravações paralelas usam lock. Reviewer referencia somente o `proof_id` emitido.

## Plano congelado e classe da mudança

`implementation_detail` ou `bounded_amendment` não autoriza nova decomposição, novo blocker, nova unidade ou novo ciclo de revisão. O executor registra a decisão e continua no mesmo sidecar. Somente `material_change` comprovada por `bm change-policy` pode interromper a unidade por mudança de escopo, contrato público, design aprovado ou invariante crítico.

Finding de qualidade dentro do contrato aprovado segue fix. Uma alternativa interna melhor não transforma o plano em inválido. Mudança material comprovada não vira blocker estrutural para obter redesign; usa `stop --kind material_change`.

## Fix, redesign e breaker

Máximo: dois fix rounds totais por identidade de unidade. Uma rodada pode cobrir vários blockers abertos. Após cada fix, commitar, submeter delta e revisar antes de iniciar outra rodada.

Após segunda revisão de fix:

- zero blockers: `next_action: approve`;
- blocker estrutural aberto e redesign ainda disponível: `next_action: redesign_allowed`;
- qualquer blocker aberto sem redesign disponível: fase `parked`, `next_action: park_unit`.

Redesign exige blocker estrutural aberto com classe reconhecida e evidência reproduzível. Máximo: um redesign total por unidade. Seam informado deve ser exatamente `risk_seam` congelado. Identidade da unidade controla limite; renomear seam ou argumento não o reinicia.

Depois do redesign, commitar, submeter delta e revisar. Finding não crítico restante permanece hardening adiado. Blocker aberto permanece blocker e estaciona unidade quando convergência acaba.

## `next_action`

`freeze` e `review` sempre retornam valor determinístico entre:

- `approve`;
- `fix_required`;
- `redesign_allowed`;
- `park_unit`;
- `completed`;
- `stopped`.

Nunca retornar `continue`. `completed` só pode ser retornado por `complete`, sem blocker aberto e depois de gates obrigatórios aprovados. `stop` retorna `stopped`.

## Gates e conclusão

Declarar cada gate obrigatório no `freeze`. Registrar resultado com `gate --proof-id`; o guard deriva `passed` ou `failed` do exit code real e prende o proof ao commit atual. `complete` exige `HEAD` revisado, zero blocker aberto e todos os gates obrigatórios `passed` exatamente nesse commit. Hardening adiado não impede conclusão. Unidade `parked` continua incompleta.

## Paradas

Somente estas categorias produzem `stopped`:

### `essential_external_credential`

Exige `service`, `missing_credential`, `blocked_operation` e `local_alternative_proof`.

### `destructive_action`

Exige `action`, `target`, `irreversible_effect` e `safe_alternative_proof`.

### `new_cost`

Exige `provider`, `operation`, `estimate` positivo, `currency` ISO 4217 e `indispensability_proof`.

### `material_change`

Exige `approved_requirement`, `change_kind`, contrato atual, mudança necessária, motivo que bloqueia a execução e `evidence_proof_id` vermelho no `HEAD` atual. `change_kind` aceita somente `scope`, `public_contract`, `approved_design` ou `critical_invariant`.

### `real_impossibility`

Exige `invariant`, lista não vazia `attempts` e `safe_workaround_absence_proof`. Cada tentativa contém somente `proof_id` real, vermelho e pertencente ao `HEAD` atual.

Sem todos os campos estruturados, `stop` falha. Decisão técnica interna nunca retorna `ask_user` ou `stopped`: escolher opção reversível de menor risco, registrar decisão automática e continuar. Bloqueio local não para unidade independente.

## Comandos

Usar `python3 <review_guard.py> <comando> --help` como autoridade para flags. Operações principais:

```bash
python3 <review_guard.py> proof --root <workspace> --planning-version <version> --plan <plan> --unit <unit> --commit <commit> --cwd <cwd> --timeout <segundos> -- <argv...>
python3 <review_guard.py> freeze --root <workspace> --planning-version <version> --plan <plan> --unit <unit> --unit-identity <unit_sha256_do_task_brief> --task-brief <task-brief.md> --seam <seam> --review-head <HEAD> --findings <findings.json> --required-gate <gate>
python3 <review_guard.py> fix --sidecar <sidecar.json> --blocker <id> --summary <summary>
python3 <review_guard.py> redesign --sidecar <sidecar.json> --blocker <id> --seam <seam> --summary <summary>
python3 <review_guard.py> submit-delta --sidecar <sidecar.json> --kind <implementation|fix|redesign|verification> --base <commit> --head <commit>
python3 <review_guard.py> review --sidecar <sidecar.json> --findings <findings.json>
python3 <review_guard.py> gate --sidecar <sidecar.json> --gate <gate> --proof-id <proof_id>
python3 <review_guard.py> decision --sidecar <sidecar.json> --kind <internal|local_block> --summary <summary>
python3 <review_guard.py> stop --sidecar <sidecar.json> --kind <categoria> --evidence <evidence.json>
python3 <review_guard.py> complete --sidecar <sidecar.json>
python3 <review_guard.py> reopen --sidecar <sidecar.json> --head <commit-posterior> --reason <motivo>
python3 <review_guard.py> status --sidecar <sidecar.json>
python3 <review_guard.py> migrate --sidecar <sidecar.json>
```

Sequência de convergência:

```text
freeze
submit-delta --kind implementation -> review  # somente quando houver implementação subsequente elegível
submit-delta --kind verification -> review    # somente após review limpa do único implementation; testes/fixtures/docs/artifacts
fix -> submit-delta -> review
fix -> submit-delta -> review
redesign -> submit-delta -> review
gate -> complete
reopen -> review
```

Comandos mutáveis validam fase antes de escrever. `status` valida ou recupera sidecar sem alterar fase. Nenhum comando, resultado ou estado contém `ask_user`.

## Revisão final do release

Após homologação aceita e antes da entrega, revisar release completo contra spec, planos, contratos cruzados, hardening adiado, segurança e diff desde primeira `base_revision`. Usar revisor Codex, sidecar próprio e mesma máquina de convergência. Somente após aprovação e verificação ampla registrar revisão final aprovada; então núcleo pode criar entrega.
