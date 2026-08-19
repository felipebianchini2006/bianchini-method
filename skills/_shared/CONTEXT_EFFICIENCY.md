# Context Efficiency v3.1

Esta referência descreve as projeções derivadas adicionadas ao Bianchini Method. Nenhuma delas substitui o `PROJECT_STATE.md`, a spec completa, o plano aprovado, o ledger ou as evidências do release.

## Enforcement das unidades quality v2

Cada unidade de um plano `planning.quality_version: 2` deve declarar:

```markdown
**Change:** state-machine
**Readiness refs:** D-001, A-001, P-001, U-001, SD-001
```

`planning-audit` valida de forma determinística:

- categoria `Change` suportada pela política;
- formato e existência de cada referência;
- presença do plano em `destinations` do item de readiness;
- cobertura de todos os itens de readiness destinados ao plano.

Pacotes `quality_version: 1` permanecem compatíveis.

## Brief hidratado

`task-brief` pode produzir uma projeção compacta do contexto da unidade:

```bash
python3 <bm.py> task-brief \
  --plan docs/bianchini/changes/v3/plans/P02-auth.md \
  --task 3 \
  --state docs/living/PROJECT_STATE.md \
  --root . \
  --hydrate-context \
  --ledger-tail-lines 40 \
  --output .superpowers/bianchini/context/P02-T03.md
```

A projeção contém somente o digest aprovado, metadados do plano, itens de readiness citados, seções exatas de spec, `verification.fast`, execução ativa e final do ledger. O arquivo deve permanecer em scratch ignorado e pode ser regenerado a qualquer momento.

## Diff de specs

A spec futura completa continua sendo a fonte de verdade. `spec-diff` cria apenas uma visualização ADDED, MODIFIED e REMOVED:

```bash
python3 <bm.py> spec-diff \
  --root . \
  --base docs/bianchini/current/specs/auth.md \
  --target docs/bianchini/changes/v3/spec-deltas/auth.md \
  --output artifacts/bianchini/v3/deltas/auth.md
```

As duas specs devem usar IDs estáveis em headings:

```markdown
## AUTH-001: Renovação de sessão
```

O resultado carrega os SHA-256 da base e do target. Alterar qualquer fonte torna a projeção anterior obsoleta.

## Evidência de mutation testing

`mutation-evidence verify` normaliza e valida o relatório no estado final do código:

```bash
python3 <bm.py> mutation-evidence verify \
  --state docs/living/PROJECT_STATE.md \
  --root . \
  --plan P03 \
  --risk-seam pricing-calculation \
  --tool normalized \
  --command "python3 mutation_runner.py" \
  --report artifacts/mutation/report.json \
  --revision "$(git rev-parse HEAD)" \
  --output artifacts/bianchini/v3/mutation/P03-pricing.json
```

Formato normalizado mínimo:

```json
{
  "schema_version": 1,
  "mutants": [
    {"id": "M1", "status": "killed"},
    {
      "id": "M2",
      "status": "survived",
      "classification": "equivalent",
      "justification": "O operador produz o mesmo resultado no domínio aprovado."
    }
  ]
}
```

Também é aceito o relatório JSON do Stryker. Survivors usam `equivalent`, `unreachable`, `non_material` ou `blocking`. Classificação não bloqueante exige justificativa. Revisão divergente do HEAD ou do RC, survivor sem classificação, mutante ignorado ou erro de execução bloqueiam quando a política for `selective` ou `required_selective`. Percentual global nunca decide o gate.
