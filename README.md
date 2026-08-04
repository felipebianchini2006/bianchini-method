# sdd-planning — skill de planejamento Spec-Driven Development para Claude Code

Skill de agente que transforma **escopo comercial (PDF) + plano mestre (.md) + referência visual (pasta `design/` com HTML/ZIP do Cloud Design)** em especificações aprováveis e planos de implementação TDD executáveis por agentes de IA — usando o fluxo Spec-Driven Development do [Superpowers](https://github.com/obra/superpowers), sem escrever uma linha de código de produção.

## O que ela faz

1. **Pré-voo** — localiza e lê as fontes, inicializa git, registra fatos/premissas/conflitos.
2. **Design** — extrai o ZIP com segurança, gera `MANIFEST.sha256`, captura screenshots de todas as telas via Playwright e produz `DESIGN_INVENTORY.md` (regra de fidelidade 1:1).
3. **Spec central** — com **Apêndice de Convenções Compartilhadas** (envelope de erro, paginação, nomes de artefatos, enums) fixado ANTES das specs complementares, eliminando divergências entre documentos escritos em paralelo.
4. **Specs complementares** em subagentes paralelos + **revisão adversarial cruzada como gate obrigatório** (nomes, contradições, lacunas de cobertura por ID de requisito).
5. **Documentação viva** — `PROJECT_STATE`, `DEVELOPMENT_LOG`, `DECISIONS_LOG`, `REQUIREMENTS_TRACEABILITY`, `KNOWN_ISSUES`, `TEST_EVIDENCE`, `DESIGN_IMPLEMENTATION_MAP` + ADRs, como memória operacional da execução.
6. **Planos em ondas** (nenhum plano lê outro pela metade), formato `superpowers:writing-plans`, código TDD completo apenas nas tarefas críticas, incluindo fase final de **validação dirigida por agente** (web via Playwright + emulador Android + simulador iOS).
7. **Matriz de cobertura + PLANNING_REVIEW.md** — todos os requisitos rastreados de spec a teste planejado; termina pedindo aprovação do responsável.

## Princípios embutidos

- [Karpathy Guidelines](https://github.com/forrestchang/andrej-karpathy-skills): pensar antes, simplicidade primeiro, alterações cirúrgicas, execução orientada a objetivo verificável.
- Arquitetura mínima: sem microserviços, Kubernetes, GraphQL, CQRS, Redis ou abstrações especulativas sem necessidade comprovada e registrada.
- Melhores práticas por linguagem verificadas na documentação oficial atual (nunca de memória).
- Zero placeholders (`TBD`/`TODO` proibidos), critérios sempre verificáveis por comando.

## Instalação

```bash
mkdir -p ~/.claude/skills/sdd-planning
curl -fsSL https://raw.githubusercontent.com/felipebianchini2006/sdd-planning-skill/main/skills/sdd-planning/SKILL.md \
  -o ~/.claude/skills/sdd-planning/SKILL.md
```

## Uso

No repositório do projeto novo (contendo o PDF de escopo, o plano mestre `.md` e a pasta `design/`):

```text
/sdd-planning
```

A skill só planeja — a implementação começa depois da aprovação, via `superpowers:subagent-driven-development`.

## Requisitos

- Claude Code com o plugin [Superpowers](https://github.com/obra/superpowers) instalado.
- Opcional: skill `karpathy-guidelines`, `playwright-cli` (screenshots do design), MCP context7 (docs oficiais).

## Licença

MIT
