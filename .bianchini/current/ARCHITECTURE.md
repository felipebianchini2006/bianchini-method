# Arquitetura alvo

Um executável Go com módulos internos de responsabilidade clara. O pacote de distribuição contém somente as skills atuais e o binário. Scripts Python podem validar o produto, mas não implementam regras do método.

Workspace centraliza identidades e caminhos. Planos vivem em changes/Cxxx/plans/Pxx-slug/PLAN.md; RESULT.md e evidence/INDEX.md ficam ao lado. O índice é derivado; provas, revisões, logs e resultados de tarefas continuam em results. Links relativos e resolução pela identidade da mudança preservam a navegação após arquivamento. Homologação fica em changes/Cxxx/homologation/RC-id com relatório e evidências. Current representa o sistema aceito. Registros técnicos podem ficar em results com resolvedor único.

CLI e validação determinística não inferem fidelidade semântica de hashes. Escopo registra cobertura por página; planejamento e homologação usam o mesmo domínio acceptance para os cenários. Coherence confere jornadas e dimensões antes da aprovação. Screenshots exigem decodificação integral com limites de dimensões e pixels. A skill opera o produto e registra provas reais. Defeitos conhecidos são corrigidos e retestados.

Operações irreversíveis e efeitos externos seguem autorização do usuário. Leitura/escrita mantém confinamento, atomicidade, locks e recuperação. Formatos anteriores incompatíveis são identificados e exigem transição revisada. Documentos completos da 1.1.0 continuam legíveis sem reescrever selos. A mudança da própria ferramenta é registrada sem fingir compatibilidade dos artefatos entre contratos.

Módulos previstos: workspace/layout, núcleo de regras atuais, distribuição/atualização e CLI. Extrações adicionais dependem de redução concreta de acoplamento.
