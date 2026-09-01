<!-- bianchini-method:host-adapter:start -->
## Bianchini Method — adapter de host

- Host: `claude-compatible`
- Arquivo: `CLAUDE.md`
- Capabilities: `CLAUDE.md`, `Agent Skills`, `subagents`

### Contrato comum

- Consuma somente o context pack validado para a unidade; não releia o contrato completo quando o pack estiver válido.
- Exija a mesma `pack_identity`, o mesmo `pack_digest` e o mesmo `package_digest` usados pelo CLI antes de executar ou revisar a unidade.
- Trate o CLI `bm` como autoridade para schema, digest, DAG, impacto, evidência e gates.
- Peça a próxima onda ao CLI; o host agenda agentes, modelos e paralelismo sem gravar decisões de host no kernel.
- Preserve o fluxo público e nunca acesse o namespace estrangeiro `.planning/`.

### Política do host

- Carregue as instruções compatíveis de `CLAUDE.md` e as Agent Skills declaradas pelo projeto.
- Use subagentes e hooks do host somente para executar a onda recebida, sem decidir gates no prompt.
<!-- bianchini-method:host-adapter:end -->
