---
name: executar-plano-codex
description: Alias explícito do executor canônico do Bianchini Method para uso no Codex.
disable-model-invocation: true
---

# Executar Plano — Codex

**Anuncie:** "Executando <planos> pelo executor canônico do Bianchini Method no Codex."

Leia integralmente o `SKILL.md` de `executar-plano` instalado em `../executar-plano/SKILL.md` e siga esse contrato sem criar uma segunda máquina de estados. No checkout fonte deste repositório, o arquivo correspondente está em `../../../skills/executar-plano/SKILL.md`.

O Codex pode usar suas ferramentas próprias para editar, executar testes e obter uma revisão independente. Isso não cria outro significado para `proof`, `review`, `completed`, `reopen`, release ou homologação. Todos esses estados pertencem ao binário Go empacotado em `../_shared/bin/bm`; não use fallback Python.

Regras específicas do host:

- não crie worktree apenas por estar no Codex;
- não espere reviewer, subagente ou ferramenta em loop;
- uma revisão produz `approved` ou `changes_requested` em uma execução limitada;
- registre o resultado pelo `bm verify review` do contrato canônico;
- use `bm plan reopen` quando surgir prova nova contra uma conclusão anterior;
- o sidecar e `review_guard.py` deste pacote existem somente para retomar execuções legadas; não são autoridade de conclusão para novas execuções.

Uso explícito:

```text
$executar-plano-codex all
```
