---
name: update-bm
description: Use somente com invocação explícita de /update-bm para verificar e atualizar a instalação local do Bianchini Method.
disable-model-invocation: true
---

# Atualizar Bianchini Method

**Anuncie:** "Verificando a versão instalada do Bianchini Method."

Esta skill é exclusivamente manual. Não verificar ou atualizar automaticamente durante planejamento, execução, correção ou homologação.

Resolva o CLI empacotado em `../_shared/bin/bm` no Unix ou `../_shared/bin/bm.exe` no Windows. A raiz instalada é o diretório `skills` que contém esta skill e `_shared`. Ausência bloqueia; não use fallback Python.

## Verificar sem alterar

Quando o argumento for `check`, `status` ou `--check`:

```bash
<bm> update-bm --check --format text
```

Informar versão instalada, versão oficial e se existe atualização. Falha de rede não autoriza assumir que a instalação está atualizada.

## Verificar e atualizar

Sem argumento, ou com `update`:

```bash
<bm> update-bm --format text
```

O comando usa somente a `main` oficial de `felipebianchini2006/bianchini-method`.

Comportamento:

- instalação copiada: baixa o pacote oficial, valida o archive, preserva skills alheias, cria backup e substitui somente os diretórios gerenciados;
- checkout Git: exige branch `main`, árvore limpa e atualização fast-forward de `origin/main`;
- versão igual: não altera arquivos;
- versão local mais nova: nunca faz downgrade;
- erro, archive inseguro ou falha de escrita: bloqueia e mantém ou restaura a instalação anterior.

Não usar `sudo`, não apagar backups manualmente, não forçar merge Git e não alterar outro diretório de skills por inferência.

## Saída

Informar:

- versão anterior;
- versão oficial encontrada;
- situação `up_to_date | update_available | updated | ahead`;
- modo `installed_package | git_checkout`;
- caminho do backup quando criado;
- bloqueio objetivo, se houver.
