package gokernel

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func scopeDraft(unsourced bool) string {
	source := "- Fonte: PDF p. 1\n"
	if unsourced {
		source = ""
	}
	return `# Escopo — Portal

## Objetivo

Permitir que clientes registrem solicitações completas com segurança.

## Resultados esperados

Solicitações são registradas e consultadas com identidade estável.

## Atores e perfis

### ACT-001 — Cliente
` + source + `
## Fluxos

### FLW-001 — Registrar
- Ator: Cliente.
- Gatilho: envio.
- Pré-condições: sessão válida.
- Caminho principal: preencher e enviar.
- Resultado: registro criado.
- Falhas: entrada inválida é recusada.
` + source + `
## Requisitos funcionais

### REQ-001 — Registrar
` + source + `- Aceite:
  - GIVEN cliente autenticado.
  - WHEN confirmar envio.
  - THEN criar solicitação.

## Requisitos não funcionais

Não especificado no PDF.

## Regras de negócio

Não especificado no PDF.

## Dados e estados

Não especificado no PDF.

## Integrações e efeitos externos

Não aplicável: o PDF não exige integração externa.

## Critérios gerais de aceite

O cliente registra e consulta uma solicitação sem dados parciais.

## Comportamentos de erro

Não especificado no PDF.

## Riscos e casos para o planejamento

Não especificado no PDF.

## Dentro do escopo

Cadastro e consulta segura das solicitações do cliente responsável.

## Fora do escopo

Chat em tempo real e integração com mensageria permanecem excluídos.

## Decisões consolidadas

Nenhuma.

## Questões abertas

Nenhuma.

## Decisões bloqueantes

Nenhuma.

## Contradições

Nenhuma.

## Proveniência e cobertura

Será substituída pelo selo.
`
}

func scopePDF() []byte {
	return []byte("%PDF-1.4\nminimal scope fixture\n%%EOF\n")
}

func TestScopeSealVerifyAndTamper(t *testing.T) {
	repo := goGitRoot(t)
	if code, _, stderr := runCLI(t, "model", "init", "--repo", repo); code != 0 {
		t.Fatal(stderr)
	}
	code, stdout, stderr := runCLI(t, "model", "init", "--repo", repo, "--change", "Portal")
	if code != 0 {
		t.Fatal(stderr)
	}
	var created map[string]any
	if err := json.Unmarshal([]byte(stdout), &created); err != nil {
		t.Fatal(err)
	}
	change := stateString(created["change"])
	inputs := t.TempDir()
	source := filepath.Join(inputs, "escopo.pdf")
	draft := filepath.Join(inputs, "draft.md")
	if err := os.WriteFile(source, scopePDF(), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(draft, []byte(scopeDraft(false)), 0o600); err != nil {
		t.Fatal(err)
	}
	code, stdout, stderr = runCLI(t, "scope", "seal", "--repo", repo, "--change", change, "--source", source, "--draft", draft, "--pages", "2", "--extraction", "native")
	if code != 0 || stderr != "" {
		t.Fatalf("code=%d stderr=%q", code, stderr)
	}
	var sealed map[string]any
	if err := json.Unmarshal([]byte(stdout), &sealed); err != nil {
		t.Fatal(err)
	}
	if sealed["status"] != "ready_for_sdd" || sealed["next_action"] != "/sdd-planning" {
		t.Fatalf("sealed=%#v", sealed)
	}
	code, stdout, stderr = runCLI(t, "scope", "verify", "--repo", repo, "--change", change, "--source", source)
	if code != 0 || stderr != "" {
		t.Fatalf("verify code=%d stderr=%q", code, stderr)
	}
	var verified map[string]any
	if err := json.Unmarshal([]byte(stdout), &verified); err != nil {
		t.Fatal(err)
	}
	if verified["verified"] != true || verified["scope_digest"] != sealed["scope_digest"] {
		t.Fatalf("verified=%#v", verified)
	}
	scope := filepath.Join(repo, ".bianchini", "changes", change, "SCOPE.md")
	content, err := os.ReadFile(scope)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(scope, []byte(strings.Replace(string(content), "Cadastro e consulta segura", "Cadastro e consulta auditável", 1)), 0o600); err != nil {
		t.Fatal(err)
	}
	code, stdout, stderr = runCLI(t, "scope", "verify", "--repo", repo, "--change", change)
	if code != 3 || stdout != "" || !strings.Contains(stderr, "SCOPE_STALE") {
		t.Fatalf("tamper code=%d stdout=%q stderr=%q", code, stdout, stderr)
	}
	code, stdout, stderr = runCLI(t, "model", "validate", "--repo", repo, "--change", change)
	if code != 3 || stdout != "" || !strings.Contains(stderr, "STALE_EVIDENCE: SCOPE_STALE") {
		t.Fatalf("model stale code=%d stdout=%q stderr=%q", code, stdout, stderr)
	}
}

func TestScopeSealRejectsInvalidInputWithoutMutation(t *testing.T) {
	tests := []struct {
		name      string
		unsourced bool
		pages     string
		want      string
	}{
		{name: "unsourced", unsourced: true, pages: "2", want: "item sem fonte"},
		{name: "page count", pages: "0", want: "quantidade de páginas inválida"},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			repo := goGitRoot(t)
			if code, _, stderr := runCLI(t, "model", "init", "--repo", repo); code != 0 {
				t.Fatal(stderr)
			}
			code, stdout, stderr := runCLI(t, "model", "init", "--repo", repo, "--change", "Portal")
			if code != 0 {
				t.Fatal(stderr)
			}
			var result map[string]any
			_ = json.Unmarshal([]byte(stdout), &result)
			change := stateString(result["change"])
			scope := filepath.Join(repo, ".bianchini", "changes", change, "SCOPE.md")
			before, _ := os.ReadFile(scope)
			inputs := t.TempDir()
			source, draft := filepath.Join(inputs, "scope.pdf"), filepath.Join(inputs, "draft.md")
			_ = os.WriteFile(source, scopePDF(), 0o600)
			_ = os.WriteFile(draft, []byte(scopeDraft(test.unsourced)), 0o600)
			code, stdout, stderr = runCLI(t, "scope", "seal", "--repo", repo, "--change", change, "--source", source, "--draft", draft, "--pages", test.pages, "--extraction", "native")
			if code != 3 || stdout != "" || !strings.Contains(stderr, test.want) {
				t.Fatalf("code=%d stdout=%q stderr=%q", code, stdout, stderr)
			}
			after, _ := os.ReadFile(scope)
			if string(after) != string(before) {
				t.Fatal("scope changed after rejected seal")
			}
		})
	}
}
