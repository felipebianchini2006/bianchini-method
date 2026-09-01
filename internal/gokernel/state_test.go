package gokernel

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestValidateStateVerticalParity(t *testing.T) {
	fixture := filepath.Join("..", "..", "tests", "fixtures", "project-state-v2.json")
	code, stdout, stderr := runCLI(t, "validate-state", fixture)
	if code != 0 || stderr != "" {
		t.Fatalf("code=%d stderr=%q", code, stderr)
	}
	assertJSONEqual(t, stdout, `{"method_version":2,"valid":true}`)
}

func TestEmbeddedStateSchemaMatchesCanonicalSource(t *testing.T) {
	canonical, err := os.ReadFile(filepath.Join("..", "..", "skills", "_shared", "schemas", "project-state.schema.json"))
	if err != nil {
		t.Fatal(err)
	}
	if string(defaultStateSchema) != string(canonical) {
		t.Fatal("embedded state schema diverged from canonical source")
	}
}

func TestValidateStateErrorsAreFailClosed(t *testing.T) {
	tests := []struct {
		name       string
		content    string
		code       int
		stderrPart string
	}{
		{"legacy", "method_version: 1\n", 2, "schema v2 não deve validar projeto legado"},
		{"corrupt fenced", "# State\n\n```json\n{\"method_version\": 2,\n```\n", 3, "BLOQUEADO: PROJECT_STATE inválido"},
		{"not object", "[]\n", 2, "PROJECT_STATE deve ser um objeto"},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			path := filepath.Join(t.TempDir(), "STATE.md")
			if err := os.WriteFile(path, []byte(test.content), 0o644); err != nil {
				t.Fatal(err)
			}
			code, stdout, stderr := runCLI(t, "validate-state", path)
			if code != test.code || stdout != "" || !strings.Contains(stderr, test.stderrPart) {
				t.Fatalf("code=%d stdout=%q stderr=%q", code, stdout, stderr)
			}
		})
	}
}

func TestValidateStateRejectsSemanticDrift(t *testing.T) {
	fixture := filepath.Join("..", "..", "tests", "fixtures", "project-state-v2.json")
	content, err := os.ReadFile(fixture)
	if err != nil {
		t.Fatal(err)
	}
	var state map[string]any
	if err := json.Unmarshal(content, &state); err != nil {
		t.Fatal(err)
	}
	approval := state["approval"].(map[string]any)
	approval["approved_plans"] = []any{}
	path := filepath.Join(t.TempDir(), "STATE.md")
	mutated, err := json.Marshal(state)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, mutated, 0o644); err != nil {
		t.Fatal(err)
	}
	code, stdout, stderr := runCLI(t, "validate-state", path)
	if code != 2 || stdout != "" || !strings.Contains(stderr, "aprovação deve cobrir todos os planos") {
		t.Fatalf("code=%d stdout=%q stderr=%q", code, stdout, stderr)
	}
}

func TestValidateStateRejectsMissingAndSymlink(t *testing.T) {
	repo := t.TempDir()
	missing := filepath.Join(repo, "missing.json")
	code, stdout, stderr := runCLI(t, "validate-state", missing)
	if code != 2 || stdout != "" || stderr != "estado não encontrado: "+missing+"\n" {
		t.Fatalf("code=%d stdout=%q stderr=%q", code, stdout, stderr)
	}
	target := filepath.Join(repo, "state.json")
	if err := os.WriteFile(target, []byte(`{"method_version":2}`), 0o644); err != nil {
		t.Fatal(err)
	}
	link := filepath.Join(repo, "link.json")
	if err := os.Symlink(target, link); err != nil {
		t.Fatal(err)
	}
	code, stdout, stderr = runCLI(t, "validate-state", link)
	if code != 3 || stdout != "" || !strings.Contains(stderr, "PATH_SAFETY") {
		t.Fatalf("code=%d stdout=%q stderr=%q", code, stdout, stderr)
	}
}
