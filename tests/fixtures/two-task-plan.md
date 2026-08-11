---
plan_id: P01
execution: grouped
review: plan_gate
---

# CRUD mínimo

### Tarefa 1 — Criar registro

**Execution:** grouped
**Review:** plan_gate
**Test seams:** HTTP POST
**Verification:** `pytest -q tests/test_create.py`

### Tarefa 2 — Listar registros

**Execution:** grouped
**Review:** plan_gate
**Test seams:** HTTP GET
**Verification:** `pytest -q tests/test_list.py`
