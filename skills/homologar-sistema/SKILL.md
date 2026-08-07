---
name: homologar-sistema
description: Use quando todos os planos de implementação selecionados estiverem concluídos e for necessário validar o release candidate pelas jornadas reais dos usuários antes da entrega ou publicação.
---

# Homologar Sistema

**Anuncie ao iniciar:** "Homologando o release candidate <versão/commit> via bianchini-method."

## Princípio

Validar o artefato que será entregue, como usuário real, no escopo contratado. Evidência do RC executado vem antes do aceite; plataforma não executada, bug crítico aberto ou dependência externa indispensável não validada impedem alegar entrega concluída.

Este comando tem somente os quatro estágios abaixo. Não criar um plano adicional de homologação nem converter cada linha da matriz, tela ou clique em tarefa ou subagente.

## 1. Preparação e matriz de cobertura

1. Ler `AGENTS.md`, `docs/living/PROJECT_STATE.md`, o spec central ativo, critérios de aceite e planos concluídos selecionados. Confirmar versão, commit, build e ambiente do RC.
2. Extrair somente o escopo aprovado e implementado: plataformas entregues, perfis, permissões, jornadas críticas, integrações e estados de erro. Função futura ou fora do aceite é limitação/backlog, não bug.
3. Montar matriz concisa com `plataforma | perfil | jornada/comportamento | estados e risco | resultado | evidência`. Agrupar por plataforma e perfil, preservando a sessão. Fazer no máximo uma revisão da preparação.
4. Usar homologação ou ambiente descartável, dados sintéticos e conta de teste por perfil. Reutilizar seeds, fixtures e harnesses existentes.
5. Ler [references/platform-runners.md](references/platform-runners.md) e selecionar o runner por plataforma e risco.

**Limites de segurança:** sem autorização explícita, nunca cobrar de verdade, enviar mensagem real, executar exclusão destrutiva ou alterar produção. Mascarar tokens, credenciais, dados pessoais, documentos, endereços e pagamentos em logs, screenshots, evidências e manual. Não instalar framework novo quando Browser, Playwright, ADB, Xcode/Simulator, Maestro ou testes existentes atenderem.

## 2. Execução das jornadas reais

Executar pela interface do usuário, no build real:

- todas as funções relevantes de cada perfil;
- jornada principal, erros críticos, permissões e recuperação de cada perfil;
- cada comportamento interativo distinto ao menos uma vez, sem repetir o mesmo controle para todos os itens idênticos de uma lista;
- carregamento, vazio, erro, validação, confirmação, cancelamento, offline quando aplicável e retorno após reinício ou nova sessão;
- web em desktop e ao menos um viewport móvel realista.

Para aplicativo com código compartilhado, executar jornadas completas na plataforma primária e smoke crítico na secundária. Executar completo em Android e iOS quando houver comportamento nativo: câmera, arquivos, notificações, permissões, mapas, geolocalização, background, biometria, deep links, pagamentos ou diferença conhecida. Registrar a plataforma primária e o motivo. Nunca alegar suporte a plataforma não executada.

Salvar evidências por plataforma e perfil em `artifacts/qa/final/<data>/`, apontando caminhos na matriz. Não copiar logs brutos para documentos vivos nem para o contexto. Computer Use é fallback; preferir seletores, árvore de acessibilidade e ferramentas estruturadas.

## 3. Triagem, correção e reteste

Para cada falha, registrar: perfil, plataforma, jornada, passo, esperado, real, severidade e evidência. Separar bug do produto, indisponibilidade externa e item fora de escopo.

Bug crítico ou importante exige **REQUIRED SUB-SKILL:** usar `corrigir-bug`. Ela continua sendo a única skill de correção: causa raiz, teste RED, fix mínimo, revisão, verificação e commit atômico. Bugs independentes não entram no mesmo fix; bugs com a mesma causa podem compor uma onda.

Usar no máximo duas ondas de correção. Depois de cada fix, reexecutar a jornada afetada e os vizinhos de risco; ao final, executar smoke global curto. Se duas ondas não convergirem, parar, registrar o bloqueio e não mascarar o resultado. Bug crítico aberto bloqueia aceite.

Registrar problema externo ainda aberto em `docs/living/KNOWN_ISSUES.md`. Bug resolvido fica comprovado pelo commit, teste e resumo final. Se uma integração indispensável estiver indisponível, validar fake/sandbox e degradação quando possível, mas manter o projeto bloqueado até a validação real.

## 4. Pacote de aceite e manual PDF

Somente depois do último reteste aceito:

1. Criar `artifacts/qa/final/<data>/SUMMARY.md` com RC/ambiente, matriz resumida, jornadas, resultado, bugs corrigidos, bugs abertos e limitações.
2. Manter evidências sanitizadas nas subpastas por plataforma e perfil.
3. Ler e cumprir [references/manual-delivery.md](references/manual-delivery.md); gerar ou atualizar `docs/manuals/manual-do-sistema.md` e entregar `artifacts/delivery/manual-do-sistema.pdf`.
4. Atualizar factualmente `docs/living/PROJECT_STATE.md`; atualizar `docs/living/KNOWN_ISSUES.md` somente para problemas abertos.
5. Emitir `ACEITO` apenas sem bloqueador e com evidências completas. Caso contrário, emitir `BLOQUEADO`, listar o que foi validado e o próximo requisito verificável.

Esta homologação ocorre na mesma branch antes da revisão ampla final e de `superpowers:finishing-a-development-branch`. Correções entram antes dessa única revisão final. Ao terminar, devolver ao `executar-plano` o resultado, caminhos do resumo/manual e bloqueios.
