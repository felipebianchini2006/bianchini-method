# Importação enxuta de design

Use somente quando houver referência visual.

1. Preservar o arquivo original. Se houver ZIP, validar path traversal e symlinks antes de extrair.
2. Criar inventário curto com páginas, componentes reutilizáveis, tokens visuais, assets, fontes, breakpoints e estados realmente presentes.
3. Capturar screenshot apenas de cada layout distinto. Usar desktop e mobile somente quando a responsividade alterar a estrutura.
4. Não capturar todas as combinações de estado. Registrar loading, vazio e erro apenas quando existirem no design ou forem críticos para a jornada.
5. Não extrair texto integral para JSON salvo quando o conteúdo precisar ser comparado automaticamente.
6. Criar hashes somente quando for importante detectar mudanças posteriores nos arquivos de referência.
7. Fidelidade significa preservar hierarquia, tokens e comportamento visível. Não inventar melhorias.
8. Encerrar qualquer servidor temporário ao final.

No perfil Full, screenshots e mapa de implementação podem ser ampliados conforme `full-assurance.md`.
