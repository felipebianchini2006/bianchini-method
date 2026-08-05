---
name: corrigir-bug
description: Use para diagnosticar e corrigir bugs em projetos SDD (ex. "/corrigir-bug <descrição>"). Camada de política sobre superpowers:systematic-debugging — não substitui o método. Exige teste que reproduz o bug antes do fix, aplica política de modelos (melhor modelo diagnostica e revisa; econômico implementa) e atualiza a documentação viva. Nunca corrige sintoma sem causa raiz confirmada.
---

# Corrigir Bug — política de correção sobre o systematic-debugging

Camada fina de política. O MÉTODO de diagnóstico é o `superpowers:systematic-debugging` — invocá-lo SEMPRE, primeiro, e segui-lo à risca. Esta skill define quem faz o quê, com que modelo, e o que fica registrado.

**Anuncie ao iniciar:** "Corrigindo bug via corrigir-bug + systematic-debugging."

## Papéis e modelos

| Papel | Claude Code | Codex |
|---|---|---|
| Diagnóstico (causa raiz) + revisão do fix | **Fable 5** | **GPT 5.6 Sol** (high/xhigh) |
| Implementação do fix + teste | Sonnet 5 (bug simples) / Opus 5 (bug em código crítico: domínio, offline, geo, segurança) | GPT 5.6 Luna max (simples) / Terra extra alto (crítico) |

O diagnosticador NÃO implementa; o implementador NÃO decide causa raiz.

## Fluxo

1. **Diagnóstico (orquestrador):** invocar `superpowers:systematic-debugging` e seguir até causa raiz CONFIRMADA com evidência (reprodução observada, não hipótese). Proibido propor fix antes disso.
2. **Teste RED primeiro (regra inviolável):** antes de qualquer correção, escrever teste automatizado que REPRODUZ o bug e observar a falha pelo motivo correto. Bug sem teste reproduzível = registrar em `KNOWN_ISSUES.md` o limite da reprodução e só então decidir com o usuário.
3. **Fix mínimo (subagente, modelo por criticidade):** implementação cirúrgica — só o necessário para o teste passar. Sem refatoração oportunista, sem "aproveitar para melhorar" (Karpathy). Rodar teste novo + testes vizinhos do módulo.
4. **Revisão (orquestrador):** (a) o fix ataca a causa raiz, não o sintoma; (b) diff mínimo e rastreável; (c) teste falharia sem o fix (verificar revertendo mentalmente ou com `git stash` se barato); (d) nenhuma regressão nos testes vizinhos.
5. **Registro:** `KNOWN_ISSUES.md` (issue fechada ou atualizada), `DEVELOPMENT_LOG.md` (entrada: bug, causa raiz, fix, commit), `TEST_EVIDENCE.md` (comando + resultado do teste novo). Se o bug revelou lacuna de spec/plano: emendar o documento citando a spec — nunca deixar código e spec divergentes.
6. **Commit:** `fix: <causa raiz em 1 linha>` incluindo o teste. Se em worktree de execução de plano, seguir o fluxo do plano; se em main, branch própria.

## Regras

- Bug crítico ou importante NUNCA vai para `KNOWN_ISSUES.md` como forma de adiamento sem decisão explícita do responsável.
- Fix que exige mudança de contrato/interface fixada em spec: PARAR e pedir decisão (ordem de autoridade — spec vence código).
- Máximo 2 ciclos de correção do fix reprovado; no 3º, escalar modelo do implementador um nível.
- Se durante o diagnóstico surgirem OUTROS bugs: registrar em `KNOWN_ISSUES.md` e não corrigi-los nesta sessão (escopo cirúrgico), salvo se bloquearem a reprodução.
