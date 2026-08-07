---
name: status-projeto
description: Use quando for necessário obter um resumo rápido e somente leitura do estado atual de um projeto Bianchini Method, sem o usuário precisar abrir specs, planos ou documentos vivos.
---

# Status do Projeto

**Anuncie ao iniciar:** "Identificando o status atual do projeto."

## Coleta mínima

1. Ler `AGENTS.md` para respeitar as regras locais.
2. Consultar branch, alterações locais e último commit do Git.
3. Ler `docs/living/PROJECT_STATE.md`. Ele é a fonte principal para versão ativa, aprovação, planos, fase, gate final, bloqueios e próximo passo.
4. Ler `docs/living/KNOWN_ISSUES.md` somente se existir e houver problemas abertos.
5. Consultar apenas a pasta de planos da versão ativa e o último `artifacts/qa/final/*/SUMMARY.md` quando for necessário confirmar contagens ou o gate de homologação.

Não alterar arquivos, executar build/testes, criar plano ou despachar subagentes. Não inferir sucesso pela existência de arquivos: se o estado estiver ausente ou contraditório, informar `não registrado` ou `inconsistente`.

## Resposta

Responder em uma tela, sem despejar YAML, listas de arquivos ou conteúdo dos documentos:

```text
Projeto: <nome>
Branch: <branch> — <limpa|N alterações locais>
Fase: <planejamento|aguardando aprovação|execução|homologação|bloqueado|entregue|não registrado>
Planos: <concluídos/total e próximo plano>
Gate final: <não configurado|pendente|aceito|bloqueado>
Bloqueios: <nenhum registrado|resumo curto>
Próximo passo: <ação objetiva>
Comando: </sdd-planning|/executar-plano ...|/homologar-sistema|outro>
```

Omitir campos sem aplicação somente quando isso reduzir ruído. Mostrar caminhos apenas se faltar uma fonte obrigatória ou existir inconsistência que o responsável precise corrigir.
