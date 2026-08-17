# Importação enxuta de design

Use somente quando existir `docs/design/<version>/DESIGN_MANIFEST.json` aprovado e válido para o mesmo escopo.

1. Executar `bm.py design-audit verify`; arquivo solto em `docs/design` não é fonte de verdade.
2. Preservar originais. ZIP exige bloqueio de path traversal e symlink antes de extrair.
3. Usar o inventário do manifesto: superfícies, contrato, prototype, tokens, screenshots, breakpoints e arquivos.
4. Planejar pela hierarquia, tokens, componentes, estados e comportamento visível do contrato.
5. Não capturar toda combinação equivalente. Desktop/mobile somente quando a estrutura mudar.
6. Não extrair texto integral para JSON nem gerar hashes paralelos; o manifesto é a identidade única.
7. Fidelidade preserva o design aprovado. Melhoria estética nova exige `/design-projeto`, não improviso no plano.
8. Incluir manifesto e todos os arquivos listados no pacote aprovado.
9. Encerrar qualquer servidor temporário.

Design antigo, incompleto ou com `scope_digest` divergente é ignorado e não pode restringir a implementação.
