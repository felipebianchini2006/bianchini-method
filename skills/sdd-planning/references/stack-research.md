# Pesquisa de stack para planejamento

Pesquise somente o necessário para decidir o ciclo atual. O objetivo é reduzir erro de arquitetura e retrabalho, não produzir um relatório enciclopédico.

## Ordem

1. Detectar versões e convenções reais em manifests, lockfiles, código, testes, CI e deploy.
2. Listar decisões do escopo que dependem da stack: autenticação/sessão, dados/migração/concorrência, filas/webhooks/idempotência, rendering/estado, offline, build/deploy/rollback, observabilidade e segurança. Ignorar famílias não aplicáveis.
3. Consultar fontes primárias atuais: documentação oficial da versão, padrões/RFCs, repositório ou release notes upstream, documentação do provedor e normas de segurança.
4. Comparar a prática recomendada com o código existente. Preferir compatibilidade e mudança mínima; não impor arquitetura “ideal” desconectada do repositório.
5. Transformar cada achado em decisão aplicada, alternativa rejeitada, risco ou lacuna. Se não altera o design, não ocupar o contexto ativo.

## Regras de evidência

- Verificar na internet toda afirmação temporalmente instável.
- Usar fonte primária para questão técnica. Blog, agregador e conteúdo promocional servem apenas como pista para localizar a fonte original.
- Registrar título, URL HTTPS direta, versão/recorte relevante e `Acessado em: YYYY-MM-DD`.
- Distinguir fato da fonte, inferência para o projeto e decisão tomada.
- Não copiar trechos longos. Sintetizar a recomendação e apontar a seção.
- Quando a documentação não cobrir o caso, registrar a lacuna; não inventar consenso.

## Formato obrigatório

```markdown
# Stack Research — <ciclo>

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

O arquivo integra a aprovação única. Ele não concede autorização para instalar dependência, atualizar versão, migrar dados, mudar infraestrutura ou expandir o escopo.
