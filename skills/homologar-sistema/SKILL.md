---
name: homologar-sistema
description: Homologa um release candidate no produto real, percorre jornadas, revisa UI/UX, corrige defeitos do escopo e retesta até um veredito verificável.
---

# Homologar Sistema

**Anuncie:** "Homologando RC <id> no sistema real."

Leia `.bianchini/STATE.md`, o escopo, os planos e resultados da mudança. Resolva o binário empacotado `../_shared/bin/bm` no Unix ou `../_shared/bin/bm.exe` no Windows. Valide o modelo e confirme que o RC pertence à revisão e às provas atuais.

Registre a homologação em `.bianchini/changes/Cxxx-*/homologation/<RC-id>/HOMOLOGATION.md`. Guarde capturas, traces e logs sanitizados em `evidence/` e materiais de entrega em `delivery/`. Nunca aprove a árvore fonte quando o candidato entregue é outro artefato.

## Descobrir o harness

Descubra as ferramentas disponíveis no projeto e no host: browser control, browser interno do harness, suíte E2E, emulador, simulador, runner nativo, cliente de API ou harness de CLI. Leia [`references/platform-runners.md`](references/platform-runners.md) apenas para a plataforma em uso.

Para web, prefira o browser interno visível do harness quando disponível. Uma suíte existente pode complementar a jornada. Headless isolado não substitui observar a interface final.

Use a melhor ferramenta disponível. Peça autorização somente quando uma ferramenta necessária estiver ausente e sua instalação for a única forma razoável de homologar uma plataforma obrigatória. Uma ferramenta opcional ausente não bloqueia se outra superfície real produzir evidência equivalente.

## Preparar a matriz

Use `scenarios` dos planos como fonte de verdade. Cada execução em `HOMOLOGATION.md.scenarios` registra `plan`, `id`, `result`, `fingerprint`, `observed` e evidências `{kind,path,sha256}` sob `homologation/<RC-id>/evidence/`. Uma tabela pode ser projeção para leitura; não mantenha duas fontes editáveis.

Cubra requisitos, jornadas e combinações relevantes de perfil, plataforma e estado. Não produza um produto cartesiano sem risco. Faça smoke de ações secundárias pelo limite público.

Fixe RC, revision/build, ambiente, perfil, viewport ou dispositivo e horário. Resultado válido: `passed`, `failed`, `blocked` ou `not_run`. Uma linha obrigatória `not_run` impede aceite.

## Operar o produto real

Para cada combinação necessária:

1. iniciar em estado conhecido e usar a mesma superfície do usuário;
2. percorrer a jornada completa, incluindo persistência e efeitos posteriores;
3. validar sucesso e condições relevantes de erro, permissão, cancelamento e recuperação;
4. observar loading, vazio, erro, sucesso e disabled quando aplicáveis;
5. verificar console, rede, logs ou saída do processo;
6. capturar screenshots nos marcos que provam o resultado e em toda falha.

Preserve sessão durante uma jornada. Use nomes acessíveis e identificadores estáveis; coordenadas são último recurso. Ações externas, destrutivas, publicações, cobranças ou mensagens reais continuam limitadas pela autorização do usuário.

## Revisar UI e UX

Em cada tela ou estado distinto, observe hierarquia, clareza, conteúdo, alinhamento, espaçamento, tipografia, contraste, foco, teclado, overflow, responsividade, feedback e consistência. Compare com o design aprovado quando existir. O design aprovado prevalece sobre preferências genéricas.

Trate heurísticas visuais como diagnóstico e confirme seu impacto no produto. Não aplique proibições estéticas cegas nem limite correções reais por número de iterações ou teto de polish. Continue até a interface cumprir o contrato e as jornadas funcionarem.

## Corrigir e retestar

Corrija todo defeito real dentro do escopo encontrado na homologação. Registre esperado, observado, severidade, causa e evidência; aplique `corrigir-bug` quando a falha exigir investigação. Gere novo RC quando o artefato mudar e repita:

1. verificações afetadas;
2. jornada que falhou;
3. estados e fluxos vizinhos de risco;
4. smoke proporcional das plataformas e perfis afetados.

Escolha provas ligadas aos riscos e às alegações do plano. Não lance campanhas cegas. Orçamento de tempo, contexto ou tokens não transforma falta de prova em aprovação. Pare somente diante de bloqueio real: dependência externa indispensável, plataforma obrigatória indisponível após alternativas razoáveis, decisão material ausente ou falha sem correção segura dentro do escopo.

## Prontidão operacional

Quando aplicável, verifique configuração, dados, migrações, integrações, observabilidade, implantação, rollback ou recuperação. Use ambiente descartável ou sandbox oficial. Aceite técnico não autoriza deploy nem outra mutação externa.

## Veredito

`ACEITO` exige todos os cenários obrigatórios executados no RC final, provas atuais vinculadas, jornadas reais aprovadas, revisão visual concluída e nenhum finding de defeito aberto. Todo finding com severidade diferente de `info` precisa estar `resolved`; qualquer `blocking: true` também precisa estar resolvido. Sugestão estética sem defeito pode ser `info`. Caso contrário, registre `BLOQUEADO` com o próximo requisito verificável. Não use “aceito com ressalvas”.

`verify release` cria o `HOMOLOGATION.md` inicial com status `running`, gates atuais e cenários `not_run`. Atualize esse registro; não crie um segundo documento concorrente.

Quando houver manual contratado, leia [`references/manual-delivery.md`](references/manual-delivery.md) e grave a entrega no diretório `delivery/` da homologação.

Na saída, informe RC, plataformas e perfis operados, jornadas, evidências, defeitos corrigidos, retestes, prontidão operacional e veredito.
