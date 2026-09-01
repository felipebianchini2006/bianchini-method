---
name: executar-plano
description: Use para executar planos aprovados do Bianchini Method 0.4 com workspace isolado, contratos verificados, impacto seletivo e DocViva atualizada.
---

# Executar Plano

**Anuncie:** "Executando <planos> do Bianchini Method 0.4 no modo <grouped|slice|strict>."

Argumentos: `all`, `N`, `N-M`. Sem argumento, mostrar `/status-projeto`; executar todos somente quando o pedido atual for explícito.

Resolva [`../_shared/scripts/bm.py`](../_shared/scripts/bm.py) e use [`../_shared/ADAPTIVE_GATES.md`](../_shared/ADAPTIVE_GATES.md) somente no gate aplicável. O CLI e o pack carregam o contrato operacional da unidade.

## 1. Preflight

1. Ler `.bianchini/STATE.md`; sem ele, bloquear e orientar `/migrar-bianchini` ou `/sdd-planning` conforme o projeto.
2. Confirmar `status: approved|executing`, digest vigente, `COHERENCE.md` em `approved` e planos solicitados aprovados. Ler `schedule.plan_waves` e `schedule.task_waves` do checkpoint.
3. Projetar a onda executável com `bm.py roadmap next-wave --repo <repo> --change C001 --format json`. O host pode paralelizar somente `parallel_units`; o CLI não cria agentes nem escolhe modelo.
4. Validar o modelo sem reabrir a auditoria aprovada:

```bash
bm.py model validate --repo <repo> --change C001
```

5. Bloquear `ERROR`, `WARNING` aberto, plano `stale`, dependência incompleta, consumidor sem provider e divergência do modelo.
6. Exigir `git status --porcelain` vazio antes de criar ou retomar workspace.

Não executar `coherence check` nem `impact analyze` como consulta de preflight: ambos atualizam `COHERENCE.md`. O gate de workspace valida o checkpoint aprovado. Digest alterado exige nova revisão completa e nova aprovação explícita.

## 2. Workspace isolado

Criar o workspace por plano somente a partir do repositório fonte limpo:

```bash
bm.py workspace create --repo <repo> --change C001 --plan P01
```

O comando bloqueia pacote sem `COHERENCE.md` aprovado, plano `stale`, qualquer artefato do manifesto divergente do checkpoint ou do `HEAD`, Git sujo ou ID inválido. Para retomar, use `workspace locate|resume --repo <repo> --change C001 --plan P01`; dentro do workspace, use `workspace check --repo <workspace>`.

Branch esperada: `bm/c001-p01`. `main`, `master`, detached HEAD e worktree primária são proibidos. Não existe fallback para editar na branch principal.

Respeite `mise` e configuração equivalente. Instale/aquela dependência somente quando já estiver aprovada pelo plano.

## 3. Contexto mínimo e retomada

Compile o contexto da tarefa antes de editar:

```bash
bm.py context pack --repo <workspace> --unit C001/P01/T03
```

Valide o pack retornado e carregue somente suas fontes e referências. `PACK_INCOMPLETE`, `PACK_TOO_LARGE` ou `STALE_EVIDENCE` bloqueia a unidade; regenere o pack sem reler o contrato completo ou criar fallback manual.

O pack seleciona:

- índice atual;
- plano ativo;
- tarefa ativa e suas dependências `Txx`;
- partes do `SYSTEM_MODEL.md` tocadas;
- providers, consumers e restrições futuras do plano;
- specs e decisões referenciadas;
- último checkpoint e resultado do plano.

Não releia planos concluídos nem reconstrua estado pela conversa. Gere pelo CLI briefs, relatórios, pacotes de revisão e checkpoints determinísticos quando as interfaces estiverem disponíveis.

## 4. Plano congelado e mudanças

Siga esta ordem para decisão interna:

```text
decisão aprovada
→ padrão do repositório
→ stack/dependência existente
→ documentação oficial
→ opção reversível de menor risco
```

- detalhe interno reversível: decidir e registrar;
- ajuste limitado sem mudança de contrato: registrar no resultado;
- contrato, ownership, dado, migration, journey, efeito ou invariante alterado: parar a área afetada, registrar os IDs alterados e recalcular impacto;
- novo custo ou efeito irreversível: pedir autoridade no checkpoint, preservando o plano se o contrato não mudar.

Não redesenhar por preferência de nome, arquivo, comando equivalente ou solução "mais elegante". Não implementar necessidade futura.

## 5. Executar pela política

Fix round é hipótese, não entrega. Identifique o `risk_seam` estável; renomear a tarefa não reinicia sua contagem. Passe `--risk-seam` e `--consecutive-seam-findings` à política. Ao atingir o breaker, pare patches locais e redesenhe o seam.

Execute somente tarefas declaradas no frontmatter do plano. Respeite `task_waves`: tarefas da mesma onda podem avançar separadamente apenas quando não houver sobreposição real de arquivos, ownership ou efeitos. O orquestrador integra os resultados e mantém a ordem determinística dos IDs.

### Grouped

- agrupar unidades baixas do mesmo seam e ownership;
- um brief e uma revisão no gate do plano;
- `verification.fast` focal;
- commit atômico por grupo.

### Slice

- entregar comportamento vertical;
- teste comportamental no seam público;
- revisão por slice;
- commit atômico por slice.

### Strict

- uma unidade crítica por execução;
- RED pela interface pública, GREEN mínimo e regressão vizinha;
- revisão independente;
- commit atômico por tarefa.

Quando subagentes estiverem disponíveis e autorizados, use [`../_shared/agents/implementation-worker.md`](../_shared/agents/implementation-worker.md). O worker recebe somente contrato, brief, modelo necessário e arquivo de resultado. Não criar subagente por camada de teste.

## 6. Verificação e revisão

Na unidade, execute `verification.fast`: unitário, contrato/integração e regressão diretamente relacionados. E2E entra somente quando for a menor prova pública. Não execute E2E completo ou mutação por microtarefa.

No gate do plano, execute `verification.plan`: suítes afetadas, regressão do plano, jornadas críticas e mutação seletiva exigida. No release, execute os comandos completos aprovados.

Revise em dois eixos:

- **Contrato:** entrega, `provides`, `consumes`, model delta, aceite e ausência de escopo extra;
- **Qualidade:** correção, segurança, simplicidade, compatibilidade e testes.

Use [`../_shared/agents/plan-reviewer.md`](../_shared/agents/plan-reviewer.md) na cadência do modo: `grouped` no gate do plano, `slice` por slice e `strict` por tarefa. Entregue o caminho do arquivo de saída da revisão; nunca revise por microtarefa em `grouped`.

Em risco alto ou crítico envolvendo autenticação/autorização, pagamentos, privacidade, secrets, migração destrutiva ou integridade, execute passagem somente leitura por [`../_shared/agents/security-reviewer.md`](../_shared/agents/security-reviewer.md). Não executá-la em tarefa comum. Entregue o caminho do arquivo de saída do parecer e trate findings no fix loop existente.

Finding estrutural, crash window, partial commit, TOCTOU, efeito externo antes de persistência, retry ambíguo, idempotência concorrente ou recuperação após restart invalida a hipótese. Pare patches e redesenhe o seam com máquina de estados e matriz de falhas.

## 7. Fechar cada plano

No HEAD final:

1. registrar comandos, cwd, horário, resultado e exit code;
2. registrar `provides/consumes` realmente entregues e o delta real do modelo;
3. comparar o delta com o prometido;
4. executar, quando houver mudança material:

```bash
bm.py impact analyze --repo <repo> --change C001 --plan P01 \
  --changed-contract <id>
```

5. marcar somente consumidores realmente atingidos como `stale`;
6. repetir jornadas e gates apontados pelo impacto;
7. ao concluir cada tarefa schema 2, registrar o resultado com o context pack
   verificado usado por ela:

```bash
bm.py plan complete --repo <repo> --change C001 --plan P01 --task T01 \
  --context-pack .bianchini/.runtime/context/C001-P01-T01.json \
  --result "<resultado da tarefa>" \
  --verification "<evidência da tarefa>"
```

8. depois de todas as tarefas, materializar o delta real em JSON e executar:

```bash
bm.py plan complete --repo <repo> --change C001 --plan P01 \
  --actual-delta <delta-real.json> \
  --result "<resultado>" \
  --verification "<evidência>" \
  --completed-task T01 \
  --completed-task T02
```

`--completed-task` permanece aceito para compatibilidade e, quando informado,
deve listar todos os `Txx` na ordem aprovada. O CLI exige os resultados próprios
das tarefas, vinculados a `pack_identity`, `pack_digest` e `package_digest`, e
revalida o pacote completo antes de aceitar a conclusão do plano.

9. confirmar o resultado em `.bianchini/changes/Cxxx-*/results/` e o `STATE.md` atualizado.

`not_run`, flake aberto, evidência obsoleta ou dependência indispensável mantém o plano bloqueado. Uma mudança interna sem contrato/dado/invariante não invalida planos futuros.

## 8. Fechar a mudança

Depois do último plano:

1. reconstruir `Sn` e executar `model validate`;
2. exigir equivalência com o `SYSTEM_MODEL.md` final;
3. executar o check estrutural, a revisão semântica conjunta atualizada e journeys ponta a ponta;
4. executar `verification.release` e homologação aplicável no RC exato;
5. revisar o release completo uma vez;
6. se o digest mudou, obter nova aprovação explícita e gravá-la com `coherence approve`;
7. sincronizar arquitetura, modelo e specs em `.bianchini/current/`;
8. mover a mudança concluída para `.bianchini/archive/`;
9. deixar `STATE.md` compacto em `idle` com `last_completed` e próxima ação.

Depois dos gates aplicáveis e com Git limpo, execute `bm.py cycle-close --repo <repo> --change C001`. O CLI recompõe o modelo pelos resultados, promove arquitetura/modelo e arquiva a mudança com rollback de falha intermediária.

Existência isolada de endpoint, tabela, fila ou tela não comprova integração. Diferencie código, testes, sandbox, deploy, efeito externo e homologação humana.

Não fazer push, merge, deploy ou publicação por inferência. Respeite a autorização atual do usuário e as regras do repositório.

## Saída

Informe mudança/plano, modo, workspace, modelo antes/depois, contratos entregues, impact radius, planos `stale`, gates, commits, resultados, DocViva e bloqueios.
