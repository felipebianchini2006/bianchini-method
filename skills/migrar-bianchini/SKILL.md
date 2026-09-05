---
name: migrar-bianchini
description: Use para migrar uma única vez documentação anterior do Bianchini Method para `.bianchini`, com prévia, checksums, rollback e `.planning` intocável.
---

# Migrar Bianchini

**Anuncie:** "Validando uma migração única para `.bianchini`."

Use por invocação explícita. Leia [`../_shared/METHOD_CONTRACT.md`](../_shared/METHOD_CONTRACT.md) e resolva o binário empacotado `../_shared/bin/bm` no Unix ou `../_shared/bin/bm.exe` no Windows. Ausência bloqueia; não use fallback Python. Não implemente adaptador de compatibilidade.

Ao mencionar a versão na abertura, no status ou na entrega, execute o binário empacotado com `version --json` uma vez na sessão e use o campo `version`: `Bianchini Method <version>`. `contract_version` e `STATE.md.method` identificam formatos internos; não são a versão instalada.

## 1. Verificar sem alterar

Sempre comece por:

```bash
bm migrate check --repo <repo>
```

`check` deve confirmar:

- repositório Git limpo;
- projeto anterior concluído ou `idle`;
- origens Bianchini reconhecidas;
- mapa origem → destino;
- SHA-256 de cada arquivo;
- ausência de colisão, symlink externo, arquivo especial e path traversal;
- destino final confinado a `.bianchini/`;
- nenhuma operação sobre `.planning/`.

Origens reconhecidas:

```text
docs/living/
docs/bianchini/
artifacts/bianchini/
documentos Bianchini identificáveis em docs/design/
.superpowers/bianchini/direct/
```

Formato desconhecido, ciclo ativo, Git sujo, colisão ou checksum inconsistente bloqueiam. Não tente corrigir arquivos antigos, adivinhar equivalência ou ampliar a lista de origens.

Se o usuário pediu apenas avaliação, pare após `check` e entregue a prévia.

## 2. Aplicar uma única vez

Quando o pedido atual autorizar a migração e `check` passar:

```bash
bm migrate apply --repo <repo>
```

O CLI deve:

1. criar staging transacional recuperável;
2. preservar histórico Git de arquivos rastreados;
3. escrever destinos e verificar checksums;
4. criar `.bianchini/archive/import-AAAA-MM-DD/MANIFEST.md`;
5. inicializar `.bianchini/PROJECT.md`, `STATE.md` e `current/`;
6. arquivar histórico anterior sem duplicação;
7. remover a origem somente após validar o destino;
8. restaurar o estado anterior se qualquer etapa falhar.

Não mover, copiar, converter, renumerar ou apagar `.planning/`. Não usar seus arquivos para preencher lacunas. A verificação final deve provar que ele permaneceu byte a byte igual.

## 3. Validar o resultado

Depois de `apply`:

```bash
bm model validate --repo <repo>
```

Confirme:

- `.bianchini/STATE.md` válido e compacto;
- arquitetura, modelo, specs, histórico, quicks e debugs nos destinos declarados;
- manifest com todos os hashes;
- cada destino do manifest existe e corresponde ao SHA-256 registrado;
- nenhuma origem Bianchini conhecida duplicada;
- Git mostra somente moves e arquivos esperados;
- `.planning/` inalterado;
- nenhum lock ou staging residual em `.bianchini/.runtime/`.

Crie commit atômico da migração quando Git fizer parte do fluxo. Não faça push, deploy ou outra alteração de produto por inferência.

## Saída

Informe prévia, bloqueios, quantidade de arquivos, manifesto, checksums verificados, estado final, preservação de `.planning`, commit e possibilidade de rollback.
