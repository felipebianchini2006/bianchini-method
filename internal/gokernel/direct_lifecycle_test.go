package gokernel

import (
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

func workflowTestRepo(t *testing.T, commit bool) string {
	t.Helper()
	repo := t.TempDir()
	command := exec.Command("git", "init", "-q")
	command.Dir = repo
	if output, err := command.CombinedOutput(); err != nil {
		t.Fatalf("git init: %v: %s", err, output)
	}
	if err := os.WriteFile(filepath.Join(repo, "keep.txt"), []byte("preservar\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	if commit {
		for _, args := range [][]string{{"add", "keep.txt"}, {"-c", "user.name=Fixture", "-c", "user.email=fixture@example.test", "commit", "-qm", "initial"}} {
			command = exec.Command("git", args...)
			command.Dir = repo
			command.Env = append(os.Environ(), "GIT_AUTHOR_DATE=2020-01-01T00:00:00Z", "GIT_COMMITTER_DATE=2020-01-01T00:00:00Z")
			if output, err := command.CombinedOutput(); err != nil {
				t.Fatalf("git %v: %v: %s", args, err, output)
			}
		}
	}
	if _, err := initializeModelWorkspace(repo); err != nil {
		t.Fatal(err)
	}
	return repo
}

func TestDirectLifecycleMatchesFrozenSuccess(t *testing.T) {
	repo := workflowTestRepo(t, false)
	started, err := runDirectLifecycle("start", []string{
		"--repo", repo,
		"--objective", "Renomear variável interna",
		"--scope", "Refactor sem efeito observável",
		"--acceptance", "Testes existentes continuam verdes",
		"--verification", "python3 -m unittest",
	})
	if err != nil {
		t.Fatal(err)
	}
	start := started.(map[string]any)
	id := stateString(start["id"])
	if id != "Q001-renomear-variavel-interna" || stateString(start["status"]) != "active" {
		t.Fatalf("start=%#v", start)
	}
	for _, name := range []string{"BRIEF.md", "PROGRESS.md"} {
		if info, err := os.Lstat(filepath.Join(repo, ".bianchini", "quick", id, name)); err != nil || !info.Mode().IsRegular() {
			t.Fatalf("missing %s: %v", name, err)
		}
	}

	statusValue, err := runDirectLifecycle("status", []string{"--repo", repo, "--slug", id})
	if err != nil {
		t.Fatal(err)
	}
	status := statusValue.(map[string]any)
	if stateString(status["route"]) != "normal" || stateString(status["status"]) != "active" {
		t.Fatalf("status=%#v", status)
	}

	checkpointValue, err := runDirectLifecycle("checkpoint", []string{
		"--repo", repo, "--slug", id, "--checkpoint", "Refactor verificado",
		"--next-action", "Finalizar", "--command", "python3 -m unittest", "--evidence", "suíte verde",
	})
	if err != nil {
		t.Fatal(err)
	}
	checkpoint := checkpointValue.(map[string]any)
	if stateInt(checkpoint["checkpoint"]) != 1 || stateString(stateObject(checkpoint["risk"])["phase"]) != "finish" {
		t.Fatalf("checkpoint=%#v", checkpoint)
	}

	finishedValue, err := runDirectLifecycle("finish", []string{
		"--repo", repo, "--slug", id, "--status", "completed", "--next-action", "Concluído",
		"--verification", "suíte verde", "--docviva-kind", "internal", "--docviva-outcome", "not_applicable",
		"--docviva-justification", "Somente nomes internos mudaram; comportamento e contratos ficaram iguais.",
	})
	if err != nil {
		t.Fatal(err)
	}
	finished := finishedValue.(map[string]any)
	if stateString(finished["status"]) != "completed" || stateString(stateObject(finished["docviva"])["status"]) != "verified" {
		t.Fatalf("finish=%#v", finished)
	}
	if _, err := os.Lstat(filepath.Join(repo, ".bianchini", "quick", id, "RESULT.md")); err != nil {
		t.Fatal(err)
	}
}

func TestDirectLifecycleFailsClosedOnTamperedBrief(t *testing.T) {
	repo := workflowTestRepo(t, false)
	started, err := runDirectLifecycle("start", []string{
		"--repo", repo, "--objective", "Ajuste interno", "--scope", "Sem efeito",
		"--acceptance", "aceite", "--verification", "gate",
	})
	if err != nil {
		t.Fatal(err)
	}
	id := stateString(started.(map[string]any)["id"])
	if _, err := runDirectLifecycle("checkpoint", []string{
		"--repo", repo, "--slug", id, "--checkpoint", "checado", "--next-action", "finalizar", "--evidence", "verde",
	}); err != nil {
		t.Fatal(err)
	}
	brief := filepath.Join(repo, ".bianchini", "quick", id, "BRIEF.md")
	content, err := os.ReadFile(brief)
	if err != nil {
		t.Fatal(err)
	}
	tampered := strings.Replace(string(content), `"objective": "Ajuste interno"`, `"objective": "Adulterado"`, 1)
	if err := os.WriteFile(brief, []byte(tampered), 0o644); err != nil {
		t.Fatal(err)
	}
	_, err = runDirectLifecycle("finish", []string{
		"--repo", repo, "--slug", id, "--status", "completed", "--next-action", "fim", "--verification", "verde",
		"--docviva-kind", "internal", "--docviva-outcome", "not_applicable", "--docviva-justification", "sem mudança",
	})
	if err == nil || !strings.Contains(err.Error(), "STALE_EVIDENCE") {
		t.Fatalf("err=%v", err)
	}
}
