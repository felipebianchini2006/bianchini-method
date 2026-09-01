package gokernel

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func legacyMutationFixture(t *testing.T) (string, string, string) {
	t.Helper()
	repo := t.TempDir()
	legacyGit(t, repo, "init", "-q")
	legacyGit(t, repo, "config", "user.email", "test@example.invalid")
	legacyGit(t, repo, "config", "user.name", "Test")
	statePath := legacyStateFixture(t, repo)
	stateBytes, _ := os.ReadFile(statePath)
	var state map[string]any
	_ = json.Unmarshal(stateBytes, &state)
	plan := stateObject(stateArray(state["plans"])[0])
	plan["risk"] = "high"
	plan["execution"] = "strict"
	plan["review"] = "per_task"
	planPath := filepath.Join(repo, filepath.FromSlash(stateString(plan["path"])))
	planContent := "# Plan\n\n### Task T01\n\n**Change:** business-rule\n\nTest the rule.\n"
	if err := os.WriteFile(planPath, []byte(planContent), 0o600); err != nil {
		t.Fatal(err)
	}
	legacyGit(t, repo, "add", ".")
	legacyGit(t, repo, "commit", "-qm", "fixture")
	revision := strings.TrimSpace(legacyGit(t, repo, "rev-parse", "HEAD"))
	release := stateObject(state["release"])
	release["candidate"] = map[string]any{"id": "RC-1", "revision": revision, "build": "build-1", "checksum": "sha256:1"}
	encoded, _ := legacyJSONBytes(state, true)
	if err := os.WriteFile(statePath, encoded, 0o600); err != nil {
		t.Fatal(err)
	}
	legacyGit(t, repo, "add", filepath.Base(statePath))
	legacyGit(t, repo, "commit", "-qm", "bind candidate")
	// O candidato pode apontar para uma revisão anterior; esse é o contrato do RC.
	return repo, statePath, revision
}

func TestRunMutationEvidenceNormalizedPassed(t *testing.T) {
	repo, state, revision := legacyMutationFixture(t)
	report := filepath.Join(repo, "mutation.json")
	reportValue := map[string]any{
		"schema_version": 1,
		"mutants": []map[string]any{
			{"id": "M1", "status": "Killed", "file": "rule.go"},
			{"id": "M2", "status": "Survived", "file": "rule.go", "classification": "equivalent", "justification": "same branch"},
		},
	}
	data, _ := legacyJSONBytes(reportValue, true)
	_ = os.WriteFile(report, data, 0o600)
	output := filepath.Join(repo, "mutation-evidence.json")
	result, err := runMutationEvidence([]string{
		"verify", "--state", state, "--root", repo, "--plan", "P01", "--risk-seam", "rule",
		"--tool", "normalized", "--command", "mutation-test", "--report", report,
		"--revision", revision, "--output", output,
	})
	if err != nil {
		t.Fatalf("mutation verify: %v", err)
	}
	value := result.(map[string]any)
	if value["status"] != "passed" || stateInt(stateObject(value["mutants"])["accepted_survivors"]) != 1 {
		t.Fatalf("unexpected mutation result: %#v", value)
	}
}

func TestRunMutationEvidenceWritesBlockedStaleResult(t *testing.T) {
	repo, state, _ := legacyMutationFixture(t)
	report := filepath.Join(repo, "mutation.json")
	data, _ := legacyJSONBytes(map[string]any{"schema_version": 1, "mutants": []map[string]any{{"id": "M1", "status": "Killed"}}}, true)
	_ = os.WriteFile(report, data, 0o600)
	output := filepath.Join(repo, "mutation-evidence.json")
	_, err := runMutationEvidence([]string{
		"verify", "--state", state, "--root", repo, "--plan", "P01", "--risk-seam", "rule",
		"--tool", "normalized", "--command", "mutation-test", "--report", report,
		"--revision", "stale", "--output", output,
	})
	if err == nil || !strings.Contains(err.Error(), "mutation evidence bloqueada") {
		t.Fatalf("expected blocked error, got %v", err)
	}
	written, readErr := os.ReadFile(output)
	if readErr != nil || !strings.Contains(string(written), "revision-mismatch") {
		t.Fatalf("blocked evidence was not persisted: %v %s", readErr, written)
	}
}

func TestRunMutationEvidenceRejectsUnrelatedDirtyFile(t *testing.T) {
	repo, state, revision := legacyMutationFixture(t)
	report := filepath.Join(repo, "mutation.json")
	data, _ := legacyJSONBytes(map[string]any{"schema_version": 1, "mutants": []map[string]any{{"id": "M1", "status": "Killed"}}}, true)
	_ = os.WriteFile(report, data, 0o600)
	_ = os.WriteFile(filepath.Join(repo, "unrelated.txt"), []byte("dirty"), 0o600)
	_, err := runMutationEvidence([]string{
		"verify", "--state", state, "--root", repo, "--plan", "P01", "--risk-seam", "rule",
		"--tool", "normalized", "--command", "mutation-test", "--report", report,
		"--revision", revision, "--output", filepath.Join(repo, "evidence.json"),
	})
	if err == nil || !strings.Contains(err.Error(), "alterações alheias") {
		t.Fatalf("expected dirty tree rejection, got %v", err)
	}
}
