package gokernel

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func legacyStateFixture(t *testing.T, root string) string {
	t.Helper()
	raw, err := os.ReadFile(filepath.Join("..", "..", "tests", "fixtures", "project-state-v2.json"))
	if err != nil {
		t.Fatalf("read state fixture: %v", err)
	}
	var state map[string]any
	if err := json.Unmarshal(raw, &state); err != nil {
		t.Fatalf("decode state fixture: %v", err)
	}
	approval := state["approval"].(map[string]any)
	pack := approval["package"].(map[string]any)
	for _, rawPath := range pack["files"].([]any) {
		path := filepath.Join(root, filepath.FromSlash(rawPath.(string)))
		if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
			t.Fatal(err)
		}
		content := []byte("# Fixture\n")
		if strings.Contains(path, "P01-crud.md") {
			content = []byte("# P01\n\n### Tarefa 1 — Entrega\n\n**Execution:** grouped\n")
		}
		if err := os.WriteFile(path, content, 0o644); err != nil {
			t.Fatal(err)
		}
	}
	statePath := filepath.Join(root, "PROJECT_STATE.json")
	encoded, err := json.Marshal(state)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(statePath, encoded, 0o644); err != nil {
		t.Fatal(err)
	}
	return statePath
}

func TestRunSnapshotCreateAndVerify(t *testing.T) {
	root := t.TempDir()
	state := legacyStateFixture(t, root)

	created, err := runSnapshot([]string{"create", state, "--root", root})
	if err != nil {
		t.Fatalf("create snapshot: %v", err)
	}
	result := created.(map[string]any)
	if result["algorithm"] != "sha256-manifest-v1" {
		t.Fatalf("algorithm = %v", result["algorithm"])
	}
	manifest := result["manifest"].(string)
	content, err := os.ReadFile(manifest)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(content), "  docs/scope.md\n") {
		t.Fatalf("manifest missing normalized path: %s", content)
	}

	var value map[string]any
	raw, _ := os.ReadFile(state)
	_ = json.Unmarshal(raw, &value)
	value["approval"].(map[string]any)["package"].(map[string]any)["manifest_digest"] = result["digest"]
	raw, _ = json.Marshal(value)
	_ = os.WriteFile(state, raw, 0o644)
	verified, err := runSnapshot([]string{"verify", state, "--root", root})
	if err != nil {
		t.Fatalf("verify snapshot: %v", err)
	}
	if verified.(map[string]any)["digest"] != result["digest"] {
		t.Fatal("verify returned another digest")
	}
}

func TestRunDesignAuditSealVerifyAndRejectSymlink(t *testing.T) {
	root := t.TempDir()
	scope := filepath.Join(root, "scope.md")
	design := filepath.Join(root, "design")
	if err := os.MkdirAll(design, 0o755); err != nil {
		t.Fatal(err)
	}
	_ = os.WriteFile(scope, []byte("# Scope\n"), 0o644)
	files := []string{"design/contract.md", "design/prototype.html", "design/tokens.css", "design/screen.png"}
	for _, relative := range files {
		_ = os.WriteFile(filepath.Join(root, relative), []byte("fixture\n"), 0o644)
	}
	manifestPath := filepath.Join(design, "manifest.json")
	manifest := map[string]any{
		"schema_version": 1, "status": "draft", "source": "imported",
		"scope_source": nil, "scope_digest": nil, "design_digest": nil,
		"contract": files[0], "prototype": files[1], "tokens": files[2],
		"screenshots": []string{files[3]}, "surfaces": []string{"checkout"},
		"breakpoints": []string{"mobile"}, "files": files,
	}
	raw, _ := json.Marshal(manifest)
	_ = os.WriteFile(manifestPath, raw, 0o644)

	sealed, err := runDesignAudit([]string{"seal", "--root", root, "--scope", scope, "--manifest", manifestPath})
	if err != nil {
		t.Fatalf("seal design: %v", err)
	}
	sealedResult := sealed.(map[string]any)
	if len(sealedResult["design_digest"].(string)) != 64 {
		t.Fatalf("invalid design digest: %v", sealedResult["design_digest"])
	}
	raw, _ = os.ReadFile(manifestPath)
	_ = json.Unmarshal(raw, &manifest)
	manifest["status"] = "approved"
	raw, _ = json.Marshal(manifest)
	_ = os.WriteFile(manifestPath, raw, 0o644)
	verified, err := runDesignAudit([]string{"verify", "--root", root, "--scope", scope, "--manifest", manifestPath})
	if err != nil {
		t.Fatalf("verify design: %v", err)
	}
	if verified.(map[string]any)["design_digest"] != sealedResult["design_digest"] {
		t.Fatal("design digest changed after approval")
	}

	outside := filepath.Join(t.TempDir(), "outside.md")
	_ = os.WriteFile(outside, []byte("outside"), 0o644)
	link := filepath.Join(design, "escape.md")
	if err := os.Symlink(outside, link); err != nil {
		t.Fatal(err)
	}
	manifest["files"] = append(files, "design/escape.md")
	raw, _ = json.Marshal(manifest)
	_ = os.WriteFile(manifestPath, raw, 0o644)
	if _, err := runDesignAudit([]string{"seal", "--root", root, "--scope", scope, "--manifest", manifestPath}); err == nil {
		t.Fatal("expected symlink escape to fail")
	}
}

func TestRunPlanningAuditLegacyCompatible(t *testing.T) {
	root := t.TempDir()
	state := legacyStateFixture(t, root)
	result, err := runPlanningAudit([]string{state, "--root", root})
	if err != nil {
		t.Fatalf("planning audit: %v", err)
	}
	value := result.(map[string]any)
	if value["valid"] != true || value["quality_contract"] != "legacy-compatible" {
		t.Fatalf("unexpected audit: %#v", value)
	}
}

func TestRunPlanningCheckMissingStateFailsBeforeMutation(t *testing.T) {
	root := t.TempDir()
	_, err := runPlanningCheck([]string{
		"record", "--state", filepath.Join(root, "missing.json"),
		"--root", root, "--report", filepath.Join(root, "report.json"),
	})
	if err == nil || !strings.Contains(err.Error(), "estado não encontrado") {
		t.Fatalf("unexpected error: %v", err)
	}
	if _, statErr := os.Stat(filepath.Join(root, "report.json")); !os.IsNotExist(statErr) {
		t.Fatal("missing-state check mutated report")
	}
}
