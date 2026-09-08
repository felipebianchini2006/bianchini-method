# Backend Go

`bm` é o backend oficial e único do Bianchini Method. `bm version --json` informa `engine: go`, `official: true`, `version` e as superfícies implementadas.

O backend resolve caminhos dentro de `.bianchini/`, valida contratos, escreve de forma atômica e vincula provas ao estado atual. As skills orientam decisões e jornadas; não replicam validação determinística em Markdown.

As garantias têm limites claros:

- digest confirma os bytes incluídos;
- manifesto de páginas confirma fonte, ferramenta declarada e IDs registrados por página;
- revisão semântica é um parecer vinculado às entradas atuais;
- prova de comando confirma a execução registrada no ambiente indicado;
- homologação confirma somente cenários realmente operados no RC identificado.

Nenhuma dessas garantias, isoladamente, prova ausência de defeitos, fidelidade semântica completa, deploy bem-sucedido ou efeito em produção.
