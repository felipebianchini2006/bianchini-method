# Pesquisa de stack para planejamento

Pesquise somente o necessário para decidir o ciclo atual. O objetivo é reduzir erro de arquitetura e retrabalho, não produzir um relatório enciclopédico.

## Ordem

1. Detectar versões e convenções reais em manifests, lockfiles, código, testes, CI e deploy.
2. Selecionar o menor modo suficiente e registrar o motivo:
   - `repo_only`: projeto existente, stack estabelecida, sem integração ou decisão sensível nova;
   - `targeted_web`: biblioteca/API nova, pagamento, autenticação, mobile, infraestrutura ou decisão sensível a versão;
   - `full`: garantia Full explícita, auditoria/regulação, arquitetura nova de alto impacto ou várias decisões críticas.
3. Listar decisões do escopo que dependem da stack. Ignorar famílias não aplicáveis.
4. Em modo web, consultar fontes primárias atuais: documentação oficial da versão, padrões/RFCs, repositório/release notes upstream, provedor e normas.
5. Comparar a prática recomendada com o código existente. Preferir compatibilidade e mudança mínima.
6. Transformar cada achado em decisão aplicada, alternativa rejeitada, risco ou lacuna. Se não altera o design, não ocupar o contexto ativo.

## Regras de evidência

- Em `repo_only`, não exigir internet; inventariar manifests, lockfiles, CI, testes e padrões locais.
- Em `targeted_web` e `full`, verificar na internet toda afirmação temporalmente instável.
- Usar fonte primária para questão técnica. Blog, agregador e conteúdo promocional servem apenas como pista para localizar a fonte original.
- Registrar título, URL HTTPS direta, versão/recorte relevante e `Acessado em: YYYY-MM-DD`.
- Distinguir fato da fonte, inferência para o projeto e decisão tomada.
- Não copiar trechos longos. Sintetizar a recomendação e apontar a seção.
- Quando a documentação não cobrir o caso, registrar a lacuna; não inventar consenso.

## Formato `repo_only`

```markdown
# Stack Research — <ciclo>

Research mode: repo_only
Motivo: <por que o repositório é evidência suficiente>

## Stack detectada
## Inventário local

- Manifests: <arquivos>
- Lockfiles: <arquivos ou nenhum>
- CI: <arquivos ou ausente>
- Testes: <comandos/padrões>
- Padrões locais: <decisões já comprovadas>

## Decisões aplicadas
## Riscos e lacunas
```

## Formato web

```markdown
# Stack Research — <ciclo>

Research mode: targeted_web | full
Motivo: <decisões que exigem fonte externa>

## Stack detectada

- <componente e versão comprovada no repositório>

## Fontes primárias

- Fonte primária: <título e versão/recorte>
  URL: https://...
  Acessado em: YYYY-MM-DD
  Aplicação: <decisão do ciclo afetada>

## Decisões aplicadas

- <prática escolhida> — <motivo e encaixe no código atual>

## Alternativas rejeitadas

- <alternativa> — <custo, incompatibilidade ou complexidade evitada>

## Riscos e lacunas

- <incerteza, risco residual ou “nenhum conhecido”>
```

No modo `full`, adicionar `## Escopo da pesquisa` e `## Decisões críticas`, mantendo apenas achados usados no design.

O arquivo integra a aprovação única. Ele não concede autorização para instalar dependência, atualizar versão, migrar dados, mudar infraestrutura ou expandir o escopo.
