# Bianchini Method Lean

Camada enxuta sobre o Superpowers para planejar, executar e corrigir projetos sem duplicar o trabalho das skills-base.

## Skills

- **`sdd-planning`**: transforma escopo, plano mestre e design em uma especificação central e planos executáveis. Usa perfil Lean por padrão e só adiciona artefatos quando o risco real justificar.
- **`executar-plano`**: aplica política de modelos e checkpoints sobre `superpowers:subagent-driven-development`, reutilizando ledger, task briefs, relatórios e pacotes de revisão da skill-base.
- **`corrigir-bug`**: aplica `superpowers:systematic-debugging` com fluxo proporcional à criticidade do bug.

## Princípios

1. Uma fonte de verdade para cada informação.
2. Um único spec central por padrão.
3. Menos planos, com tarefas maiores e revisáveis.
4. Sem releitura integral quando um caminho ou trecho específico basta.
5. Sem documentação operacional duplicada do Git, ledger e relatórios de teste.
6. Revisão e validação proporcionais ao risco.
7. Arquitetura mínima, sem abstrações ou infraestrutura especulativas.

## Documentação padrão

Sempre:

- `docs/superpowers/vN/specs/<data>-<sistema>-system-design.md`
- `docs/superpowers/vN/plans/`
- `docs/living/PROJECT_STATE.md`

Somente quando houver conteúdo real:

- `docs/living/DECISIONS.md`
- `docs/living/KNOWN_ISSUES.md`

Rastreabilidade detalhada, evidência consolidada, mapas visuais completos, specs complementares e revisão adversarial ficam restritos a projetos que realmente exigem esse nível de garantia.

## Instalação

```bash
for s in sdd-planning executar-plano corrigir-bug; do
  mkdir -p ~/.claude/skills/$s
  cp -R skills/$s/. ~/.claude/skills/$s/
done

# Codex: troque ~/.claude por ~/.codex
```

## Uso

No repositório do projeto:

```text
/sdd-planning
/executar-plano all
/corrigir-bug <descrição>
```

O fluxo normal é planejar, aprovar a especificação e os planos, executar pelo `executar-plano` e usar `corrigir-bug` somente para falhas fora da execução normal de uma tarefa.
