---
plan_id: P01
method_version: 2
risk: low
execution: grouped
review: plan_gate
depends_on: []
---

# API de registros

### Tarefa 1 — Criar registro

**Execution:** grouped
**Review:** plan_gate
**Test seams:** HTTP POST /records
**Verification:** `pytest -q tests/api/test_create.py`

### Tarefa 2 — Listar registros

**Execution:** grouped
**Review:** plan_gate
**Test seams:** HTTP GET /records
**Verification:** `pytest -q tests/api/test_list.py`

### Tarefa 3 — Excluir registro

**Execution:** grouped
**Review:** plan_gate
**Test seams:** HTTP DELETE /records/:id
**Verification:** `pytest -q tests/api/test_delete.py`
