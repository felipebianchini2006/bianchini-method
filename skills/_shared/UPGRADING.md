# Transição para 1.1.1

A versão do CLI e os schemas dos documentos têm funções diferentes. A 1.1.1 corrige a identificação dos formatos introduzidos na 1.1.0 e mantém a leitura dos documentos completos dessa versão.

| Documento | Formato novo | Compatibilidade de leitura |
| --- | --- | --- |
| Plano | `plans/Pxx-slug/PLAN.md`, `schema_version: 3` | Schema 2 com `scenarios` completo, como produzido na 1.1.0 |
| Escopo selado | `schema_version: 2` com `extraction_record` | Schema 1 com manifesto e digest válido, como produzido na 1.1.0 |
| Prova | Log relativo à mudança: `results/logs/<id>.log` | Referência antiga `.bianchini/changes/<mudança>/results/logs/<id>.log`, inclusive após arquivamento |

Documentos da 1.1.0 não precisam ser regravados ou renumerados. Seus digests e aprovações permanecem intactos; contratos inválidos continuam sujeitos às validações, agora antecipadas no planejamento.

## Projetos da 1.0.0 ou anteriores

A ruptura de layout da 1.1.0 não é uma atualização transparente. A 1.1.1 detecta `STATE.md` com `method: "0.4"`, planos soltos `plans/Pxx-slug.md`, planos schema 2 sem cenários e escopos schema 1 sem manifesto. Retorna `WORKSPACE_UPGRADE_REQUIRED` antes de tratá-los como documentos atuais, sem convertê-los ou gerar evidência automaticamente.

Não há migrador automático nessa versão. Há duas opções:

1. Concluir o trabalho com a versão exata que o criou, em uma instalação separada e fixada nessa versão. Preserve o checkout ou pacote dessa versão e não execute `update-bm` nessa instalação. O atualizador de skills/binário não converte os projetos atendidos por ele.
2. Fazer uma transição revisada em uma cópia do projeto. Preserve antes um backup integral, incluindo arquivos ignorados e fontes de escopo. Confira o diff da cópia antes de substituir a original.

Na transição revisada:

- Organize cada plano em `plans/Pxx-slug/PLAN.md`, revise requisitos e escreva os cenários reais de aceite; use schema 3.
- Para escopo de PDF, recupere a fonte, confira sua integridade e refaça a conciliação por página. Execute `scope seal` com o manifesto revisado; não invente `extraction_record` para satisfazer o validador.
- Preserve planos, aprovações e provas antigas como histórico. Uma nova mudança deve carregar o trabalho restante e passar por `roadmap sync`, validação do modelo, `coherence check`, revisão semântica e nova aprovação. Não recalcule hashes para conservar aprovações antigas como se o contrato não tivesse mudado.
- Reexecute as verificações e a homologação do novo candidato. Somente promova a cópia após validar a jornada completa.

## Evidências e arquivo

`results/` é a fonte oficial dos registros. `plans/Pxx-slug/evidence/INDEX.md` é um índice derivado, atualizado durante a execução e conclusão. Seus links relativos continuam válidos quando a mudança inteira vai para `archive/`.

Para mudanças já arquivadas, inclusive as da 1.1.0, use `bm verify status --repo . --change C001`. A saída inclui os caminhos atuais dos logs e verifica seus digests. O comando não reescreve os registros históricos, não recupera arquivos perdidos e não renova aprovações.
