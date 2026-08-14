# Convergência Codex

Contrato exclusivo para revisão, fix loop, breaker, redesign e parada. Estado vive em sidecar por unidade; nunca em `PROJECT_STATE` ou schema do método base.

De `bm.py policy`, preservar modo, cadência e garantia. Ignorar somente limites de fix rounds e breaker do método base. Quando correção de bug ou homologação acionarem revisão, fix loop, breaker, redesign ou decisão de parada, este contrato prevalece.

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
| `review_frozen` | `fix` | `fixing` | blocker congelado aberto; menos de dois fix rounds |
| `fixing` | `submit-delta --kind fix` | `awaiting_review` | commit do fix submetido |
| `review_frozen` | `redesign` | `redesigning` | blocker estrutural aberto; dois fixes; redesign disponível; seam idêntico |
| `redesigning` | `submit-delta --kind redesign` | `awaiting_review` | commit do redesign submetido |
| `awaiting_review` | `review` | `review_frozen` | revisão aceita; próximo passo ainda executável ou aprovação disponível |
| `awaiting_review` | `review` | `parked` | blocker aberto sem fix ou redesign disponível |
| `review_frozen` | `complete` | `completed` | zero blockers abertos; gates obrigatórios registrados e aprovados |
| qualquer não terminal | `stop` | `stopped` | categoria permitida com evidência completa |

`completed` e `stopped` são terminais. Qualquer comando mutável nessas fases falha. Qualquer transição ausente da tabela falha. `parked` não significa concluída; trabalho independente continua.

A parada é isolada por unidade. Enquanto existir qualquer unidade independente executável em qualquer plano aprovado, o scheduler mantém `/root/luna_max` e `/root/sol_medium` trabalhando e continua o fluxo global. `parked`, bloqueio local ou `stopped` de uma unidade não interrompem outras unidades sem dependência. A execução global só termina após entrega concluída ou quando todo trabalho restante estiver terminal ou estacionado sem ação segura disponível.

`gate` e `decision` registram dados sem mudar fase e são aceitos somente enquanto unidade não for terminal. `status` e `migrate` preservam fase; podem validar estado terminal.

`freeze` cria sidecar e primeira revisão atomicamente. `review` só executa em `awaiting_review`. Fix ou redesign só executam em `review_frozen`. Dois fixes consecutivos sem `submit-delta --kind fix` e `review` intermediários são inválidos. Renomear unidade ou seam não cria nova identidade nem reseta contador.

`submit-delta --kind implementation` cobre implementação subsequente à primeira revisão, somente quando freeze não deixou blocker e nenhum delta anterior foi submetido. Após fix ou redesign, usar kind correspondente antes de `review`.

## Blocker congelado

Antes de cada revisão, gerar entrada determinística com `bm.py review-package --base <last_review_head> --head HEAD`. Entregar ao revisor somente esse pacote, o sidecar da unidade e o contrato `plan-reviewer-codex.md`. A primeira revisão usa a base da unidade; revisões seguintes usam exatamente o delta submetido.

Primeira revisão congela blockers. Blocker exige:

- requisito aprovado identificável;
- reprodução estruturada com `command` em argv, `cwd`, `exit_code` de falha e `observation`;
- impacto material;
- cenário alcançável;
- `risk_seam`;
- metadados estruturais.

Forma não estrutural:

```json
{
  "risk_seam": "public-api",
  "structural": false,
  "structural_class": null,
  "structural_evidence": null
}
```

Blocker estrutural usa `structural: true`, `structural_evidence` reproduzível e uma destas classes fechadas:

- `architecture_boundary`;
- `data_model`;
- `public_contract`;
- `state_machine`;
- `cross_cutting_invariant`.

Classe livre, evidência textual vaga ou combinação inconsistente é inválida.

Finding não crítico vira `deferred_hardening`. Blocker aberto nunca vira hardening silenciosamente. Revisão seguinte cobre somente blockers congelados abertos e regressões causadas pelo delta atual. Tarefa concluída nunca reabre.

## Regressão do delta

Novo `delta_regression` só vira blocker quando todas as provas existirem:

1. `delta_base` e `delta_head` resolvem para commits Git reais do repositório validado;
2. `delta_base` coincide com `last_review_head`;
3. `delta_head` coincide com `HEAD` atual;
4. `delta_head` descende de `delta_base`;
5. arquivo do finding está confinado ao repositório;
6. localização aponta linha adicionada, modificada ou removida pelo diff; linha apenas de contexto não vale;
7. reprodução usa `command` como argv estruturado, `cwd` confinado, `base_exit_code: 0` e `head_exit_code` diferente de zero;
8. mesma reprodução passa na base e falha no head;
9. explicação causal liga mudança do delta ao defeito.

Rename deve ser resolvido pelo diff Git real. Linha removida referencia lado base e linha removida. Arquivo fora do diff, defeito preexistente, base e head com mesmo resultado ou cadeia Git inválida convertem finding para hardening.

Guard nunca executa texto arbitrário, `shell=True`, string de shell ou expansão fornecida pelo finding. Aceita somente argumentos estruturados validados e cwd confinado.

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

Declarar cada gate obrigatório no `freeze`. Registrar resultado pelo guard com evidência JSON contendo `command` como argv, `cwd`, `exit_code` e `observation`. O guard prende a evidência ao commit atual. `complete` exige `HEAD` revisado, zero blocker aberto e todos os gates obrigatórios `passed` exatamente nesse commit. Hardening adiado não impede conclusão. Unidade `parked` continua incompleta.

## Paradas

Somente estas categorias produzem `stopped`:

### `essential_external_credential`

Exige `service`, `missing_credential`, `blocked_operation` e `local_alternative_proof`.

### `destructive_action`

Exige `action`, `target`, `irreversible_effect` e `safe_alternative_proof`.

### `new_cost`

Exige `provider`, `operation`, `estimate` positivo, `currency` ISO 4217 e `indispensability_proof`.

### `real_impossibility`

Exige `invariant`, lista não vazia `attempts` e `safe_workaround_absence_proof`. Cada tentativa contém `command` como argv, `cwd`, `exit_code` e `observation`.

Sem todos os campos estruturados, `stop` falha. Decisão técnica interna nunca retorna `ask_user` ou `stopped`: escolher opção reversível de menor risco, registrar decisão automática e continuar. Bloqueio local não para unidade independente.

## Comandos

Usar `python3 <review_guard.py> <comando> --help` como autoridade para flags. Operações principais:

```bash
python3 <review_guard.py> freeze --root <workspace> --planning-version <version> --plan <plan> --unit <unit> --unit-identity <unit_sha256_do_task_brief> --task-brief <task-brief.md> --seam <seam> --review-head <HEAD> --findings <findings.json> --required-gate <gate>
python3 <review_guard.py> fix --sidecar <sidecar.json> --blocker <id> --summary <summary>
python3 <review_guard.py> redesign --sidecar <sidecar.json> --blocker <id> --seam <seam> --summary <summary>
python3 <review_guard.py> submit-delta --sidecar <sidecar.json> --kind <implementation|fix|redesign> --base <commit> --head <commit>
python3 <review_guard.py> review --sidecar <sidecar.json> --findings <findings.json>
python3 <review_guard.py> gate --sidecar <sidecar.json> --gate <gate> --status <passed|failed> --evidence <evidence.json>
python3 <review_guard.py> decision --sidecar <sidecar.json> --kind <internal|local_block> --summary <summary>
python3 <review_guard.py> stop --sidecar <sidecar.json> --kind <categoria> --evidence <evidence.json>
python3 <review_guard.py> complete --sidecar <sidecar.json>
python3 <review_guard.py> status --sidecar <sidecar.json>
python3 <review_guard.py> migrate --sidecar <sidecar.json>
```

Sequência de convergência:

```text
freeze
submit-delta --kind implementation -> review  # somente quando houver implementação subsequente elegível
fix -> submit-delta -> review
fix -> submit-delta -> review
redesign -> submit-delta -> review
gate -> complete
```

Comandos mutáveis validam fase antes de escrever. `status` valida ou recupera sidecar sem alterar fase. Nenhum comando, resultado ou estado contém `ask_user`.

## Revisão final do release

Após homologação aceita e antes da entrega, revisar release completo contra spec, planos, contratos cruzados, hardening adiado, segurança e diff desde primeira `base_revision`. Usar revisor Codex, sidecar próprio e mesma máquina de convergência. Somente após aprovação e verificação ampla registrar revisão final aprovada; então núcleo pode criar entrega.
