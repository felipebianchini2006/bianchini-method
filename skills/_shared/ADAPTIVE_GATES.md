# Gates adaptativos

Os gates provam a entrega na stack real e alimentam `verification.fast`, `verification.plan` e `verification.release`.

`model validate`, `roadmap sync` e `coherence check` validam o pacote e suas specs. A revisão do pacote não se repete por tarefa.

- `fast`: menor comando útil durante grupo, slice ou tarefa;
- `plan`: sequência completa ao concluir o plano;
- `release`: regressão automatizada, E2E codificado e build do RC antes da execução real e da varredura visual de homologação.

## Composição por estágio

- `fast`: unitários focados quando houver lógica, integração/contrato focada quando uma fronteira mudar e regressão diretamente relacionada. Não roda E2E completo.
- `plan`: suítes afetadas de unitários e integração/contrato, regressão do plano e E2E das jornadas críticas entregues. Quando `bm policy` exigir prova adicional de sensibilidade, registrá-la pelo fluxo normal de `verify`.
- `release`: suíte unitária completa configurada, integração/contratos aplicáveis, E2E de todas as jornadas críticas, regressão completa configurada e build do RC.

Essas famílias compõem os comandos do estágio. Não criar tarefa, revisão ou subagente por camada de teste. E2E continua orientado a jornada crítica, não a cada tela.

## Descoberta

Derivar comandos nesta ordem:

1. `AGENTS.md`, `CLAUDE.md`, `CONTRIBUTING.md` e README do projeto;
2. scripts do manifesto (`package.json`, `pyproject.toml`, `Makefile`, `justfile`, `Taskfile`, workspace files);
3. CI versionada;
4. convenção nativa da stack, somente se o repositório não definir comando.

Registrar comando exato, diretório, pré-condições e resultado esperado. Não inventar um comando que não foi confirmado no projeto.

## Famílias de gate

Selecionar somente as aplicáveis:

| Família | Prova | Exemplos de stacks |
|---|---|---|
| format/lint | sintaxe e padrões automatizáveis | todas |
| type/compile | contratos estáticos ou compilação | TypeScript, Kotlin, Swift, Go, Rust, Java, .NET |
| unit | regras isoladas observáveis | todas |
| integration | contratos entre módulos/infra, incluindo contract tests | API, banco, filas, filesystem, provedores |
| migration | ida, consumidores afetados e rollback/forward-fix | bancos e dados persistidos |
| build/package | artefato distribuível | web, mobile, desktop, biblioteca, CLI |
| security | autorização, segredos, dependências, entradas | áreas de alto/crítico risco |
| e2e/smoke | jornada real pelo limite externo | UI, API pública, CLI |
| platform | comportamento no alvo suportado | browser, Android, iOS, desktop, firmware |
| docs/manual | instruções e exemplos executáveis | SDK, CLI, operações e release |

## Matriz mínima por tipo de mudança

- **Documentação/configuração:** lint ou parser aplicável, links/caminhos e exemplo principal.
- **Biblioteca:** lint, tipos/compilação, unitários, integração da API pública e pacote quando distribuído.
- **API/backend:** lint/tipos, unitários de domínio, integração de persistência/contratos, smoke do endpoint e migração quando houver.
- **Web:** lint/tipos, unitários úteis, build, jornada crítica no browser e viewport móvel.
- **Mobile/desktop:** análise estática, unitários, build do alvo e smoke no simulador/dispositivo disponível.
- **CLI:** lint/compilação, unitários, invocação real com sucesso, erro, código de saída e filesystem temporário.
- **Dados/ML:** validação de schema, determinismo/tolerância, amostra representativa, regressão de métricas e custo quando aplicável.
- **Infra:** validação do manifesto/plano, policy/security, dry-run e aplicação apenas com autorização do ambiente.

## Falha e reexecução

Classificar a falha antes de corrigir: produto, teste, ambiente, flake ou dependência externa. Usar `corrigir-bug` para defeito do produto. Depois do fix, reexecutar o gate que falhou e dependentes; no fechamento do plano, executar novamente a sequência completa definida para ele.

Gate indisponível não equivale a aprovado. Registrar `not_run`, razão, risco residual e prova alternativa. Se a plataforma ou integração for requisito de aceite, manter `BLOQUEADO`.

## Evidência mínima

Para cada gate registrar no ledger:

```yaml
- name: <nome estável>
  command: <comando ou procedimento>
  cwd: <diretório>
  result: passed | failed | not_run
  executed_at: <ISO-8601>
  summary: <contagens e saída relevante>
  evidence: <caminho, se houver>
```
