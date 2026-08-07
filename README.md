# Bianchini Method Lean

Camada enxuta sobre o Superpowers para planejar, executar, homologar e corrigir projetos sem duplicar o trabalho das skills-base.

## Skills

- **`sdd-planning`**: transforma escopo, plano mestre e design em uma especificação central e planos executáveis. Seleciona automaticamente um perfil proporcional ao risco ou respeita o perfil informado pelo usuário.
- **`executar-plano`**: aplica política de modelos e checkpoints sobre `superpowers:subagent-driven-development`, reutilizando ledger, task briefs, relatórios e pacotes de revisão da skill-base.
- **`homologar-sistema`**: valida o release candidate por perfis e plataformas contratadas, controla correções bloqueantes e gera o manual PDF da versão testada.
- **`status-projeto`**: resume fase, planos, gate final, bloqueios e próximo comando sem exigir que o usuário abra os arquivos do projeto.
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

## Perfis de garantia

- **Lean**: um spec central, auto-revisão, jornadas críticas e documentação viva mínima. Indicado para a maioria dos MVPs e sistemas comerciais.
- **Standard**: permite até três specs complementares e revisão cruzada dos contratos e regras críticas. Indicado quando vários fatores de risco relevantes coexistem.
- **Full**: garantia ampliada para auditoria, regulação, segurança elevada ou risco operacional grave.

Sem argumento, `sdd-planning` usa `auto`: faz uma análise curta dos riscos e informa o perfil selecionado e o motivo. Um perfil manual é sempre respeitado; riscos adicionais são registrados e controles extras ficam restritos às áreas críticas indispensáveis, sem promover o projeto inteiro.

## Versionamento e aprovação

O primeiro ciclo de planejamento usa `docs/superpowers/v1/`. Planejamento pendente pode ser atualizado na versão atual; após aprovação ou execução, um novo ciclo usa o próximo número e o histórico não é sobrescrito. A versão ativa fica registrada em `docs/living/PROJECT_STATE.md`.

Todo planejamento novo começa como `pending_approval`. A aprovação explícita registra o estado `approved`, a data e os planos aprovados em `docs/living/PROJECT_STATE.md`. `/executar-plano` executa somente planos com essa aprovação registrada; uma aprovação explícita na conversa atual pode ser registrada imediatamente antes da execução.

## Instalação

```bash
for s in sdd-planning executar-plano homologar-sistema status-projeto corrigir-bug; do
  mkdir -p ~/.claude/skills/$s
  cp -R skills/$s/. ~/.claude/skills/$s/
done

# Codex: troque ~/.claude por ~/.codex
```

## Uso

No repositório do projeto:

```text
/sdd-planning
/sdd-planning auto
/sdd-planning lean
/sdd-planning standard
/sdd-planning full
/executar-plano all
/homologar-sistema
/status-projeto
/corrigir-bug <descrição>
```

Exemplos:

```text
/sdd-planning                  # seleção automática
/sdd-planning lean             # força Lean
/sdd-planning standard         # força Standard
/sdd-planning full             # força Full
/executar-plano 1 a 3          # executa o intervalo aprovado
```

Fluxo normal:

`/sdd-planning` -> `/executar-plano all` -> `/homologar-sistema` automático no fechamento -> entrega.

`corrigir-bug` continua sendo a única skill de correção, inclusive durante a homologação.
