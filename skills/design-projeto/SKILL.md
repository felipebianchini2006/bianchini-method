---
name: design-projeto
description: Use somente com invocação explícita de /design-projeto ou quando /sdd-planning detectar interface nova, redesign ou fluxo visual material sem contrato válido na mudança ativa do Bianchini Method.
---

# Design Projeto

**Anuncie:** "Criando contrato visual executável antes do planejamento."

Esta skill produz referência visual, não código de produção. O pacote pertence à mudança ativa em `.bianchini/`.

Ao mencionar a versão na abertura, no status ou na entrega, execute o binário empacotado com `version --json` uma vez na sessão e use o campo `version`: `Bianchini Method <version>`. `contract_version` e `STATE.md.method` identificam formatos internos; não são a versão instalada.

## 1. Definir o ciclo e o escopo

1. Ler `.bianchini/STATE.md` e localizar a mudança `Cxxx-*` ativa.
2. Sem workspace, executar `bm model init --repo <repo>` e iniciar a mudança pelo `/sdd-planning`.
3. Usar `SCOPE.md` da mudança; sem escopo materializado, bloquear apenas o design.
4. Não alterar requisitos, jornadas, texto obrigatório ou identidade fornecida.

Resolver o binário empacotado `../_shared/bin/bm` no Unix ou `../_shared/bin/bm.exe` no Windows. Ausência bloqueia; não usar fallback Python. O manifesto será aceito pelo planejamento somente quando o hash corresponder exatamente ao escopo atual.

## 2. Decidir a profundidade

- Sem interface: encerrar como `not_applicable` sem criar design.
- Interface existente com design system estável e mudança pequena: documentar somente o delta.
- Landing page, site institucional ou portfólio: usar `taste-skill`, `design-taste-frontend` ou equivalente quando instalado.
- Dashboard, SaaS, ERP, aplicativo ou fluxo multiestado: usar somente o modo de conceito de `frontend-app-builder` ou equivalente quando instalado; parar antes de qualquer implementação de produção.
- Sem adaptador: usar o contrato interno desta skill.

Adaptadores são opcionais. Nunca tornar o BM dependente de Claude, Taste, Image Gen ou fornecedor específico.

## 3. Produzir o pacote

Criar somente:

```text
.bianchini/changes/Cxxx-slug/design/
  DESIGN_MANIFEST.json
  DESIGN_CONTRACT.md
  tokens.css
  prototype/
    index.html
    interactions.js      # somente se necessário
  screenshots/           # obrigatório antes de aprovar o manifesto
```

O protótipo deve ser HTML/CSS/JS estático, sem build, backend, banco, autenticação real ou dependência de produção.

Cobrir somente as superfícies que reduzem incerteza:

- app shell ou primeira dobra;
- tela principal;
- fluxo central;
- estado vazio, erro ou confirmação realmente importante;
- mobile somente quando a estrutura mudar.

Não prototipar todo CRUD, todas as permissões ou cada tela equivalente.

## 4. Contrato visual

`DESIGN_CONTRACT.md` registra:

- público e objetivo;
- arquitetura de informação;
- superfícies e jornadas cobertas;
- tokens, tipografia, spacing e containers;
- componentes e variantes;
- loading, vazio, erro, sucesso e disabled relevantes;
- breakpoints e comportamento responsivo;
- acessibilidade mínima;
- conteúdo e assets permitidos;
- decisões `DS-001`, `DS-002` etc.;
- limites e itens não desenhados.

O protótipo precisa ser navegável nos fluxos apresentados. Controles visíveis não podem ser decorativos quando representam uma decisão de interação.

## 5. Manifesto

Criar `DESIGN_MANIFEST.json` com:

```json
{
  "schema_version": 1,
  "status": "draft",
  "source": "generated",
  "scope_source": null,
  "scope_digest": null,
  "design_digest": null,
  "contract": ".bianchini/changes/C001-slug/design/DESIGN_CONTRACT.md",
  "prototype": ".bianchini/changes/C001-slug/design/prototype/index.html",
  "tokens": ".bianchini/changes/C001-slug/design/tokens.css",
  "screenshots": [".bianchini/changes/C001-slug/design/screenshots/desktop.png"],
  "surfaces": ["app-shell", "primary-flow"],
  "breakpoints": ["desktop", "mobile"],
  "files": []
}
```

Listar em `files` todos os artefatos do pacote, exceto o próprio manifesto.

Selar hashes:

```bash
<bm> design-audit seal --root <repo> --scope <scope> --manifest <manifest>
```

Depois da aprovação explícita ou delegação inequívoca registrada no escopo, mudar `status` para `approved` e verificar:

```bash
<bm> design-audit verify --root <repo> --scope <scope> --manifest <manifest>
```

Arquivo solto nunca é fonte de verdade. Somente manifesto `approved`, íntegro e ligado ao `SCOPE.md` da mudança pode entrar no planejamento.

## 6. Revisão visual

Antes de aprovar o manifesto, usar browser ou simulador para:

1. abrir o protótipo;
2. testar navegação e estados apresentados;
3. verificar desktop e mobile aplicável;
4. revisar overflow, contraste, foco, hierarquia e clareza;
5. capturar uma evidência por layout distinto;
6. atualizar `files`, selar novamente e verificar.

Sem runner visual, manter o manifesto `draft` e bloquear apenas o planejamento visual correspondente. Screenshot inventado ou vazio não é evidência. Usar no máximo uma correção visual antes do aceite. Preferência estética tardia não autoriza reiniciar o conceito.

## Paradas

Parar somente quando faltar conteúdo obrigatório, identidade visual contratada, asset indispensável protegido, decisão material contraditória ou aprovação exigida que não foi delegada.

## Saída

Informar escopo usado, profundidade, adaptador opcional, superfícies, protótipo, manifesto, hashes, aprovação e limitações. Não implementar frontend de produção e não iniciar `/sdd-planning` com manifesto inválido.
