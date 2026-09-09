# Fluxo do método

## Planejar

Materialize o escopo em `.bianchini/changes/Cxxx-slug/SCOPE.md`. Quando a fonte for PDF, `scope seal` exige manifesto por página e registra o modo de extração sem afirmar revisão semântica automática.

O planejamento cria arquitetura, modelo, specs e planos. Cada plano fica em `plans/Pxx-slug/PLAN.md`, usa `schema_version: 3`, declara cenários e mantém `RESULT.md` e `evidence/INDEX.md` ao lado. O índice aponta para os registros oficiais em `results/`.

```bash
bm roadmap sync --repo . --change C001
bm model validate --repo . --change C001
bm coherence check --repo . --change C001 --structural-only
```

A validação do plano usa o mesmo domínio de aceite do release. `coherence check` confere também jornadas, perfis, plataformas e estados; `coherence approve` repete essa verificação antes de aceitar o pacote.

## Executar

Use `roadmap next-wave` para respeitar dependências. Cada tarefa recebe contexto limitado, prova e revisão proporcionais. Ao concluir um plano, simplifique o delta quando isso reduzir complexidade real e faça uma revisão de segurança proporcional à superfície alterada.

```bash
bm context pack --repo . --unit C001/P01/T01
bm verify task --repo . --change C001 --plan P01 --task T01 --context-pack <pack>
bm verify plan --repo . --change C001 --plan P01
```

## Homologar

Commite o código do candidato antes de `verify release`; mudanças de produto não commitadas impedem criar o RC. O comando inicia `homologation/<RC-id>/HOMOLOGATION.md`. Opere os cenários obrigatórios na superfície real. Para web, prefira o browser interno visível do harness quando disponível. Guarde evidências em `homologation/<RC-id>/evidence/`.

Corrija defeitos do escopo, gere novo RC quando o artefato mudar e reteste a jornada, os vizinhos de risco e o smoke aplicável. Falta de orçamento não autoriza aceite.

## Fechar

O fechamento exige release revisado, cenários obrigatórios aprovados, provas atuais e nenhum finding de defeito aberto.

```bash
bm cycle-close --repo . --change C001
```

Aceite técnico não executa deploy, cobrança, publicação ou outra ação externa sem autorização correspondente.

## Consultar evidências arquivadas

`bm verify status --repo . --change C001` consulta mudanças ativas ou arquivadas. A saída traz `archived` e `logs`, com caminhos atuais e integridade verificada, sem alterar provas seladas. Trata-se de um inventário histórico; não confirma validade das provas para o código atual.

Para formatos anteriores, consulte [Transição de formatos](upgrading.md).
