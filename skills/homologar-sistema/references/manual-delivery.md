# Manual e pacote de entrega

O manual descreve o release candidate aceito, não a intenção da spec nem funções futuras.

## Fonte e saída

- Fonte versionável: `docs/manuals/manual-do-sistema.md`.
- PDF curto quando `manual_pdf: quick_start` e completo quando `manual_pdf: full`: `artifacts/delivery/manual-do-sistema.pdf`.
- Com `manual_pdf: scope`, o nível vem do escopo aprovado; com `none`, nenhum manual é gerado.
- Manifesto geral da entrega: `artifacts/delivery/DELIVERY.md`.

## Conteúdo mínimo do manual

1. nome, versão, commit/build e data;
2. objetivo e público;
3. requisitos e plataformas homologadas;
4. instalação, configuração e primeiro acesso;
5. operações por perfil, organizadas por jornada;
6. permissões e comportamentos de segurança relevantes;
7. mensagens de erro comuns e recuperação;
8. backup, migração, offline ou integrações quando aplicáveis;
9. limitações conhecidas e suporte;
10. remoção/desinstalação quando o produto altera o ambiente.

Não incluir credenciais reais, tokens, dados pessoais, URL privada, conta interna ou screenshot não sanitizado. Exemplos usam valores fictícios claramente marcados.

## Geração adaptativa do PDF

Usar nesta ordem:

1. comando documentado no repositório;
2. gerador já instalado e versionado pelo projeto;
3. ferramenta de documentos disponível no ambiente;
4. conversor leve já presente no sistema.

Não instalar suíte pesada apenas para converter o manual sem autorização. PDF contratado e não gerado bloqueia a entrega.

## Validação

Abrir o PDF final e verificar:

- arquivo não vazio e legível;
- versão/RC corretos;
- sumário e hierarquia de títulos;
- nenhuma linha, tabela ou imagem cortada;
- links e referências internas úteis;
- páginas na ordem e sem páginas vazias acidentais;
- texto pesquisável quando possível;
- ausência de segredo/dado pessoal;
- checksum registrado no manifesto quando o pacote usa checksums.

O Markdown e o PDF devem representar o mesmo conteúdo. Se a geração introduzir diferença material, corrigir a fonte ou o pipeline e gerar novamente.
