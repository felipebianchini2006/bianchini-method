package gokernel

import (
	"encoding/json"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

func TestRunTaskBriefGroupedAndReport(t *testing.T) {
	root := t.TempDir()
	plan := filepath.Join(root, "P01.md")
	content := "# Plan\n\n### Task 1\n\n**Execution:** grouped\n\nFirst.\n\n### Task 2\n\n**Execution:** grouped\n\nSecond.\n"
	if err := os.WriteFile(plan, []byte(content), 0o640); err != nil {
		t.Fatal(err)
	}
	brief := filepath.Join(root, "brief.md")
	result, err := runTaskBrief([]string{"--plan", plan, "--tasks", "1-2,2", "--output", brief})
	if err != nil {
		t.Fatalf("task brief: %v", err)
	}
	value := result.(map[string]any)
	if value["kind"] != "group" || len(value["unit_digests"].([]string)) != 2 {
		t.Fatalf("unexpected task brief result: %#v", result)
	}
	written, _ := os.ReadFile(brief)
	if !strings.Contains(string(written), "### Task 1") || !strings.Contains(string(written), "### Task 2") {
		t.Fatalf("brief omitted selected units: %s", written)
	}
	report := filepath.Join(root, "report.md")
	if _, err := runReport([]string{"--brief", brief, "--output", report}); err != nil {
		t.Fatalf("report: %v", err)
	}
	if data, _ := os.ReadFile(report); !strings.Contains(string(data), "Status: IN_PROGRESS") {
		t.Fatalf("unexpected report: %s", data)
	}
}

func TestRunTaskBriefRejectsUngroupedMultiSelection(t *testing.T) {
	root := t.TempDir()
	plan := filepath.Join(root, "P01.md")
	content := "### Tarefa 1\n\n**Execution:** isolated\n\nA\n\n### Tarefa 2\n\n**Execution:** grouped\n\nB\n"
	if err := os.WriteFile(plan, []byte(content), 0o600); err != nil {
		t.Fatal(err)
	}
	_, err := runTaskBrief([]string{"--plan", plan, "--tasks", "1,2", "--output", filepath.Join(root, "brief.md")})
	if err == nil || !strings.Contains(err.Error(), "Execution: grouped") {
		t.Fatalf("expected grouped failure, got %v", err)
	}
}

func TestRunReviewPackageRedactsSecrets(t *testing.T) {
	repo := t.TempDir()
	legacyGit(t, repo, "init", "-q")
	legacyGit(t, repo, "config", "user.email", "test@example.invalid")
	legacyGit(t, repo, "config", "user.name", "Test")
	if err := os.WriteFile(filepath.Join(repo, "app.txt"), []byte("safe\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	legacyGit(t, repo, "add", "app.txt")
	legacyGit(t, repo, "commit", "-qm", "base")
	base := strings.TrimSpace(legacyGit(t, repo, "rev-parse", "HEAD"))
	if err := os.WriteFile(filepath.Join(repo, "app.txt"), []byte("api_key=supersecret\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	legacyGit(t, repo, "commit", "-qam", "change")
	brief := filepath.Join(repo, "brief.md")
	report := filepath.Join(repo, "report.md")
	_ = os.WriteFile(brief, []byte("brief\n"), 0o600)
	_ = os.WriteFile(report, []byte("report\n"), 0o600)
	output := filepath.Join(repo, "review.md")
	result, err := runReviewPackage([]string{"--cwd", repo, "--base", base, "--head", "HEAD", "--brief", brief, "--report", report, "--output", output})
	if err != nil {
		t.Fatalf("review package: %v", err)
	}
	if result.(map[string]any)["redactions"].(int) != 1 {
		t.Fatalf("expected one redaction: %#v", result)
	}
	data, _ := os.ReadFile(output)
	if strings.Contains(string(data), "supersecret") || !strings.Contains(string(data), "[REDACTED]") {
		t.Fatalf("secret was not redacted: %s", data)
	}
}

func TestRunCheckpointAndProofMap(t *testing.T) {
	repo := t.TempDir()
	legacyGit(t, repo, "init", "-q")
	legacyGit(t, repo, "config", "user.email", "test@example.invalid")
	legacyGit(t, repo, "config", "user.name", "Test")
	if err := os.WriteFile(filepath.Join(repo, "tracked"), []byte("x\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	legacyGit(t, repo, "add", "tracked")
	legacyGit(t, repo, "commit", "-qm", "base")
	statePath := legacyStateFixture(t, repo)
	ledger := filepath.Join(repo, "ledger.txt")
	_ = os.WriteFile(ledger, []byte("one\ntwo\n"), 0o600)
	checkpoint := filepath.Join(repo, "checkpoint.json")
	if _, err := runCheckpoint([]string{"--state", statePath, "--ledger", ledger, "--cwd", repo, "--output", checkpoint}); err != nil {
		t.Fatalf("checkpoint: %v", err)
	}

	stateBytes, _ := os.ReadFile(statePath)
	var state map[string]any
	_ = json.Unmarshal(stateBytes, &state)
	release := stateObject(state["release"])
	release["candidate"] = map[string]any{"id": "RC-1", "revision": "abc", "build": "build-1", "checksum": "sha256:1"}
	encoded, _ := legacyJSONBytes(state, true)
	_ = os.WriteFile(statePath, encoded, 0o600)
	evidence := filepath.Join(repo, "evidence.json")
	items := []map[string]any{
		{"type": "automated", "command": "pytest -q", "result": "passed", "rc": "RC-1", "revision": "abc", "build": "build-1", "checksum": "sha256:1", "evidence": "pytest.log"},
		{"type": "manual_gap", "journey": "payment"},
	}
	evidenceBytes, _ := legacyJSONBytes(items, true)
	_ = os.WriteFile(evidence, evidenceBytes, 0o600)
	proof := filepath.Join(repo, "proof.json")
	result, err := runProofMap([]string{"--state", statePath, "--evidence", evidence, "--output", proof})
	if err != nil {
		t.Fatalf("proof map: %v", err)
	}
	value := result.(map[string]any)
	if value["automated_total"] != 2 || value["automated_proven"] != 1 {
		t.Fatalf("unexpected proof map: %#v", value)
	}
}

func legacyGit(t *testing.T, directory string, args ...string) string {
	t.Helper()
	command := exec.Command("git", args...)
	command.Dir = directory
	output, err := command.CombinedOutput()
	if err != nil {
		t.Fatalf("git %v: %v: %s", args, err, output)
	}
	return string(output)
}
