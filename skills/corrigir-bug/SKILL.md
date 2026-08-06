---
name: corrigir-bug
description: Use para diagnosticar e corrigir bugs com causa raiz, reprodução e fix mínimo. Aplica fluxo proporcional ao risco sobre superpowers:systematic-debugging, sem obrigar múltiplos agentes e documentos para bugs simples.
---

# Corrigir Bug Lean

**Anuncie ao iniciar:** "Corrigindo bug via systematic-debugging no nível <simples|crítico>."

## Base obrigatória

Invocar `superpowers:systematic-debugging` primeiro e seguir suas fases. Usar `superpowers:test-driven-development` para o teste de regressão e `superpowers:verification-before-completion` antes de concluir.

Nenhum fix antes de uma causa raiz sustentada por evidência.

## Classificação

### Simples

Bug isolado, baixo risco, contrato inalterado e mudança pequena.

- Um único agente econômico capaz pode diagnosticar, criar a reprodução, implementar e testar.
- O orquestrador revisa o diff e a evidência.
- Não despachar um agente separado apenas para repetir o diagnóstico.

### Crítico

Afeta segurança, autorização, pagamentos, integridade de dados, sincronização, migração, concorrência, geolocalização ou contrato compartilhado.

- O melhor modelo confirma a causa raiz.
- Um implementador adequado aplica o fix mínimo e o teste.
- Um revisor capaz verifica causa, escopo, regressão e contrato.

| Papel | Claude Code | Codex |
|---|---|---|
| Diagnóstico/revisão crítica | Fable 5 | GPT 5.6 Sol high/xhigh |
| Implementação crítica | Opus 5 | GPT 5.6 Terra extra alto |
| Bug simples | Sonnet 5 | GPT 5.6 Luna max ou Terra alto |

Usar o nível equivalente se o modelo nomeado não estiver disponível.

## Fluxo

1. Reproduzir de forma consistente e reunir evidência.
2. Confirmar a causa raiz, não apenas o componente onde o erro aparece.
3. Criar teste automatizado RED. Quando isso não for tecnicamente viável, usar o menor script reproduzível ou procedimento manual determinístico e registrar a limitação.
4. Aplicar um único fix cirúrgico, sem refatoração oportunista.
5. Rodar o teste novo e os testes diretamente vizinhos.
6. Revisar o diff e verificar que o teste falharia sem o fix.
7. Commitar como `fix: <causa raiz em uma linha>`.

Após três hipóteses ou fixes sem sucesso, parar e revisar a arquitetura conforme `systematic-debugging`. Não empilhar tentativas.

## Documentação

O commit e o teste são o registro padrão de um bug resolvido.

Atualizar:

- `KNOWN_ISSUES.md` somente se o problema continuar aberto ou existir limitação conhecida;
- `DECISIONS.md` somente se houver decisão de contrato ou arquitetura;
- `PROJECT_STATE.md` somente se o bug alterar status, entrega ou bloqueio.

Não atualizar `DEVELOPMENT_LOG` e `TEST_EVIDENCE` para cada bug por padrão.

Se o bug revelar divergência entre código e spec, corrigir a fonte errada. Se exigir mudança de requisito ou contrato aprovado, parar e pedir decisão antes de alterar.

Outros bugs encontrados entram em `KNOWN_ISSUES.md` apenas quando reais e relevantes. Não corrigi-los na mesma sessão salvo se bloquearem a reprodução.
