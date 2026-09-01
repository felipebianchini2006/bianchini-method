<!-- bianchini-method:host-adapter:start -->
## Bianchini Method — adapter de host

- Host: `generic`
- Arquivo: `AGENTS.md`
- Capabilities: `AGENTS.md`, `Agent Skills`

### Contrato comum

- Consuma somente o context pack validado para a unidade; não releia o contrato completo quando o pack estiver válido.
- Exija a mesma `pack_identity` e o mesmo `contract_digest` usados pelo CLI antes de executar ou revisar a unidade.
- Trate o CLI `bm` como autoridade para schema, digest, DAG, impacto, evidência e gates.
- Peça a próxima onda ao CLI; o host agenda agentes, modelos e paralelismo sem gravar decisões de host no kernel.
- Preserve o fluxo público e nunca acesse o namespace estrangeiro `.planning/`.

### Política do host

- Descubra e carregue as Agent Skills declaradas pelo projeto antes de executar uma unidade.
- Execute cada unidade com o pack recebido e devolva evidência ao CLI sem reimplementar gates.
<!-- bianchini-method:host-adapter:end -->
