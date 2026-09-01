<!-- bianchini-method:host-adapter:start -->
## Bianchini Method — adapter de host

- Host: `codex`
- Arquivo: `AGENTS.md`
- Capabilities: `AGENTS.md`, `Agent Skills`, `subagents`, `commentary updates`

### Contrato comum

- Consuma somente o context pack validado para a unidade; não releia o contrato completo quando o pack estiver válido.
- Exija a mesma `pack_identity`, o mesmo `pack_digest` e o mesmo `package_digest` usados pelo CLI antes de executar ou revisar a unidade.
- Trate o CLI `bm` como autoridade para schema, digest, DAG, impacto, evidência e gates.
- Peça a próxima onda ao CLI; o host agenda agentes, modelos e paralelismo sem gravar decisões de host no kernel.
- Preserve o fluxo público e nunca acesse o namespace estrangeiro `.planning/`.

### Política do host

- Faça o menor diff compatível que satisfaça a unidade e seus testes.
- Não crie abstrações especulativas; extraia apenas quando houver variação real comprovada.
- Use subagentes apenas para frentes independentes, com ownership fechado e integração pelo executor principal.
<!-- bianchini-method:host-adapter:end -->
