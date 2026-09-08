# Portabilidade final da 1.1.0

Commit verificado: `4ff215b2d348ab69e9a4f918e8041b75762440f0`.

A matriz nativa aprovou testes, vet e build em Linux, macOS e Windows. A análise de concorrência passou em Linux e macOS. Os cinco testes Python mantidos e a jornada pública passaram no job auxiliar.

CI: https://github.com/felipebianchini2006/bianchini-method/actions/runs/34287828942

## Correções e revisão

A primeira execução encontrou rejeição de caminhos absolutos nativos do Windows, diferenças CRLF nas fixtures e um executável de teste sem `.exe`. O resolvedor agora aceita caminhos nativos sem permitir backslash em contratos relativos; traversal, symlinks e namespaces proibidos continuam cobertos. O teste de confinamento também confirma a rejeição de backslash em caminhos absolutos no Unix.

A segunda execução isolou três suposições sobre permissões POSIX nos testes. As verificações agora comparam a representação efetiva do host e continuam validando preservação de permissões, cache e integridade. Nenhum desses testes foi desativado.

## Distribuição e provas

Os cinco pacotes finais estão em `.bianchini/.runtime/distribution/4ff215b/`. O manifesto copiado em `evidence/distribution.json` registra commit e SHA-256 de cada pacote. Todos os hashes foram conferidos. O binário macOS arm64 extraído do pacote declarou versão 1.1.0 e executou novamente a jornada pública.

`evidence/native-ci.json` registra os jobs nativos. `evidence/native-package.json` registra a identidade do executável. `evidence/packaged-public-journey.log` contém o resultado da jornada. Essa execução usa `--protocol-test`: suas revisões de fixture exercitam o protocolo e não são apresentadas como revisão independente.

A revisão principal está em `.bianchini/archive/C001-metodo-unificado/results/IMPLEMENTATION_REVIEW.md`. O candidato original desse arquivo permanece histórico; os pacotes acima incluem a correção posterior de portabilidade. Não houve publicação de tag/release nem alteração da instalação pessoal.
