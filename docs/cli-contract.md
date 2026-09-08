# Contrato público do CLI

A ajuda do binário é a fonte executável da interface. Consulte:

```bash
bm --help
bm <command> --help
bm version --json
```

Famílias públicas:

| Família | Responsabilidade |
|---|---|
| `model`, `scope`, `roadmap`, `coherence`, `impact` | criar e validar o pacote da mudança |
| `plan`, `verify`, `context` | executar unidades e registrar provas atuais |
| `workspace` | isolar trabalho quando necessário |
| `direct` | executar uma entrega coesa |
| `debug` | investigar e corrigir um defeito com evidência |
| `design-audit` | selar e verificar o pacote visual |
| `change-policy`, `policy` | classificar impacto e gates proporcionais |
| `adapter` | renderizar ou instalar orientação do host |
| `learn` | governar aprendizados explícitos |
| `spec-diff`, `status`, `update-bm` | inspeção e manutenção |
| `cycle-close` | fechar e arquivar uma mudança aceita |

Saídas estruturadas usam JSON. Erros de entrada retornam código 2, gates bloqueados retornam 3 e workspace inseguro retorna 4. Um comando pode restringir mais esses códigos; a ajuda e os testes do binário prevalecem.

O contrato versionado usado por testes e empacotamento fica em `contracts/cli-surfaces.json`. Ele deve ser gerado ou atualizado a partir do backend atual e não pode apontar para implementações removidas.
