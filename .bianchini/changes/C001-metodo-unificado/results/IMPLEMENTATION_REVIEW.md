# Revisão da implementação 1.1.0

Revisores: root e subagentes GPT-5.6 Sol. Revisão técnica do delta; não é aprovação humana nem declaração de ausência absoluta de defeitos.

## Arquitetura e simplificação

Go continua como única autoridade operacional. Python permanece em launcher e avaliações auxiliares. Foram retirados backend duplicado, oráculo, comandos de gerações anteriores, overlay separado e reset de linhagem do atualizador.

`internal/workspace` centraliza o layout sem replicar políticas de validação. `internal/acceptance` valida cenários e seus resultados usando tipos explícitos. Verificação foi separada em comandos, execução, registros, identidade da fonte e fechamento. Locks, escrita atômica, journal e recuperação continuam nas fronteiras de I/O existentes.

## Findings corrigidos

- RC podia declarar HEAD enquanto o produto continha bytes não commitados. A criação exige código limpo antes e depois dos gates.
- Resoluções e procedimentos manuais podiam apontar para qualquer arquivo do repositório. Todos os tipos de evidência de homologação agora exigem o diretório `evidence/` do candidato, arquivo regular, conteúdo não vazio e hash atual.
- O campo `blocking` aceitava texto sem bloquear. Agora exige booleano quando presente.
- Alterar cenários sobre o mesmo artefato podia manter a identidade do candidato. O digest do pacote aprovado agora participa da identidade do RC.
- Manifesto de escopo podia conter chave JSON duplicada. O parser estrito recusa ambiguidade.
- Serialização de manifesto tipado podia produzir digest diferente na leitura. O selo normaliza a representação antes de calcular o digest.
- A retirada dos helpers antigos mudou a interpretação de `json.Number("0")`. A semântica falsa do zero foi restaurada.
- Exemplos e fixtures usavam caminhos e aprovações de formatos retirados. Foram atualizados para o contrato atual sem dispensar specs, cobertura, revisão ou atualidade de provas.

## Segurança proporcional

Foram revisadas as fronteiras alteradas: confinamento de caminhos, symlinks, integridade de evidências, arquivos de imagem, comandos sem shell, origem de atualização, tamanho de arquivos, identidade do candidato e preservação transacional. Os testes de pacote continuam cobrindo instalação real e rollback. Evidências e hashes não substituem inspeção semântica nem operação do produto.

## Integração de skills

Planejamento inclui caminho de prova, cenários ligados a riscos e experimentos para premissas críticas. Execução e debug incluem simplificação e revisão após refatoração. Cada plano encerra com revisão de segurança proporcional. Design e homologação incorporam critérios selecionados do Impeccable. Homologação prefere o browser interno visível para web, corrige defeitos do escopo e repete as jornadas afetadas.

## Limites

O produto deste repositório é uma CLI e um conjunto de skills. A avaliação local opera a CLI e um serviço demonstrativo. Ela não demonstra que qualquer aplicação futura estará livre de bugs. A matriz nativa de CI complementa os testes locais. Esta mudança não publica tag/release nem altera a instalação pessoal do usuário.
