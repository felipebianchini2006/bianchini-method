# Arquitetura alvo

Um executável Go com módulos internos de responsabilidade clara. O pacote de distribuição contém somente as skills atuais e o binário. Scripts Python podem validar o produto, mas não implementam regras do método.

Workspace centraliza identidades e caminhos. Planos vivem em changes/Cxxx/plans/Pxx-slug/PLAN.md; RESULT.md e evidence ficam ao lado. Homologação fica em changes/Cxxx/homologation/RC-id com relatório e evidências. Current representa o sistema aceito. Registros técnicos podem ficar em results com resolvedor único.

CLI e validação determinística não inferem fidelidade semântica de hashes. Escopo registra cobertura por página; homologação exige cobertura dos cenários definidos pelo contrato aprovado. A skill opera o produto e registra provas reais. Defeitos conhecidos são corrigidos e retestados.

Operações irreversíveis e efeitos externos seguem autorização do usuário. Leitura/escrita mantém confinamento, atomicidade, locks e recuperação. Não implementar leitura de gerações anteriores. A mudança da própria ferramenta é registrada sem fingir compatibilidade dos artefatos entre contratos.

Módulos previstos: workspace/layout, núcleo de regras atuais, distribuição/atualização e CLI. Extrações adicionais dependem de redução concreta de acoplamento.
