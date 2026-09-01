package gokernel

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestPlanCompleteFrozenActualDeltaRequirement(t *testing.T) {
	repo := t.TempDir()
	code, stdout, stderr := runCLI(t, "plan", "complete", "--repo", repo, "--change", "fixture", "--plan", "P01", "--result", "done")
	if code != 2 || stdout != "" || stderr != "plan complete exige --actual-delta\n" {
		t.Fatalf("code=%d stdout=%q stderr=%q", code, stdout, stderr)
	}
}

func TestPlanCompleteSchemaOneWritesResultAndPendingCloseState(t *testing.T) {
	repo := t.TempDir()
	if err := os.Mkdir(filepath.Join(repo, ".git"), 0o755); err != nil {
		t.Fatal(err)
	}
	if code, _, stderr := runCLI(t, "model", "init", "--repo", repo); code != 0 {
		t.Fatal(stderr)
	}
	code, stdout, stderr := runCLI(t, "model", "init", "--repo", repo, "--change", "plan complete")
	if code != 0 || stderr != "" {
		t.Fatalf("code=%d stderr=%q", code, stderr)
	}
	var created map[string]any
	if err := json.Unmarshal([]byte(stdout), &created); err != nil {
		t.Fatal(err)
	}
	change := stateString(created["change"])
	directory := filepath.Join(repo, ".bianchini", "changes", change)
	delta := map[string]any{"contracts": map[string]any{"add": []any{map[string]any{"id": "health_checked"}}}}
	planValue := map[string]any{
		"id": "P01", "depends_on": []any{}, "provides": []any{"health_checked"},
		"consumes": []any{}, "owns": []any{}, "touches": []any{}, "requirements": []any{},
		"acceptance": []any{"saúde entregue"}, "verifications": []any{"go test ./..."},
		"model_delta": delta, "migrations": []any{}, "external_effects": []any{}, "future_constraints": []any{},
	}
	planDocument, _ := frontmatterDocument(planValue, "# P01", false)
	if err := os.WriteFile(filepath.Join(directory, "plans", "P01.md"), planDocument, 0o600); err != nil {
		t.Fatal(err)
	}
	current, err := loadProjectModel(filepath.Join(repo, ".bianchini", "current", "SYSTEM_MODEL.md"))
	if err != nil {
		t.Fatal(err)
	}
	expected, err := current.applyDelta(delta)
	if err != nil {
		t.Fatal(err)
	}
	expectedDocument, _ := frontmatterDocument(expected.mapping(), "# Modelo esperado", false)
	if err := os.WriteFile(filepath.Join(directory, "SYSTEM_MODEL.md"), expectedDocument, 0o600); err != nil {
		t.Fatal(err)
	}
	coherenceDocument, _ := frontmatterDocument(map[string]any{
		"schema_version": 1, "planning_contract": 1, "status": "approved", "digest": strings.Repeat("a", 64),
	}, "# Coerência", false)
	if err := os.WriteFile(filepath.Join(directory, "COHERENCE.md"), coherenceDocument, 0o600); err != nil {
		t.Fatal(err)
	}
	deltaPath := filepath.Join(repo, "actual-delta.json")
	deltaBytes, _ := json.Marshal(delta)
	if err := os.WriteFile(deltaPath, deltaBytes, 0o600); err != nil {
		t.Fatal(err)
	}
	code, stdout, stderr = runCLI(t, "plan", "complete", "--repo", repo, "--change", change, "--plan", "P01", "--actual-delta", deltaPath, "--result", "saúde entregue", "--verification", "go test ./...")
	if code != 0 || stderr != "" {
		t.Fatalf("code=%d stdout=%q stderr=%q", code, stdout, stderr)
	}
	var result map[string]any
	if err := json.Unmarshal([]byte(stdout), &result); err != nil {
		t.Fatal(err)
	}
	if result["status"] != "completed" || result["model_digest"] != expected.digest() || result["next_plan"] != nil {
		t.Fatalf("result=%#v", result)
	}
	payload, err := readStructuredFrontmatter(filepath.Join(directory, "results", "P01.md"))
	if err != nil {
		t.Fatal(err)
	}
	if payload["actual_delta_digest"] != waveStableDigest(delta) || payload["model_after_digest"] != expected.digest() {
		t.Fatalf("payload=%#v", payload)
	}
	workspace := newMethodWorkspace(repo)
	state, err := workspace.readState()
	if err != nil {
		t.Fatal(err)
	}
	if state["status"] != "pending_close" || state["current_unit"] != nil {
		t.Fatalf("state=%#v", state)
	}
}
