package gokernel

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestDebugLifecycleMatchesFrozenSuccess(t *testing.T) {
	repo := workflowTestRepo(t, false)
	startedValue, err := runDebug([]string{
		"start", "--repo", repo,
		"--objective", "Eliminar processamento duplicado do webhook",
		"--expected", "Evento duplicado não altera o estado novamente",
		"--actual", "Evento duplicado cria uma segunda transição",
		"--environment", "pytest local",
	})
	if err != nil {
		t.Fatal(err)
	}
	started := startedValue.(map[string]any)
	id := stateString(started["id"])
	if id != "D001-eliminar-processamento-duplicado-do-webhook" || stateString(started["stage"]) != "intake" {
		t.Fatalf("started=%#v", started)
	}
	listedValue, err := runDebug([]string{"list", "--repo", repo})
	if err != nil {
		t.Fatal(err)
	}
	if len(stateArray(listedValue.(map[string]any)["items"])) != 1 {
		t.Fatalf("listed=%#v", listedValue)
	}

	steps := []struct {
		event string
		extra []string
	}{
		{"reproduced", nil},
		{"diagnosed", []string{"--root-cause", "provider_event_id não era persistido como chave única"}},
		{"red", nil},
		{"fixing", nil},
	}
	for _, step := range steps {
		args := []string{"checkpoint", "--repo", repo, "--id", id, "--event", step.event, "--evidence", "evidência " + step.event}
		args = append(args, step.extra...)
		if _, err := runDebug(args); err != nil {
			t.Fatalf("%s: %v", step.event, err)
		}
	}
	if err := os.WriteFile(filepath.Join(repo, "fix.py"), []byte("DEDUPLICATION = True\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	for _, args := range [][]string{
		{"checkpoint", "--repo", repo, "--id", id, "--event", "green", "--evidence", "regressão focal passou no patch"},
		{"checkpoint", "--repo", repo, "--id", id, "--event", "regression_checked", "--evidence", "fluxos vizinhos passaram", "--neighbor-regression", "webhook válido continua atualizando o pedido"},
		{"checkpoint", "--repo", repo, "--id", id, "--event", "documented", "--evidence", "causa e contrato registrados", "--residual-risk", "nenhum risco conhecido no escopo testado"},
	} {
		if _, err := runDebug(args); err != nil {
			t.Fatalf("args=%v: %v", args, err)
		}
	}
	spec := filepath.Join(repo, ".bianchini", "current", "specs", "webhook.md")
	if err := os.WriteFile(spec, []byte("# Webhook\n\n## WHK-001: Deduplicação por provider_event_id\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	finishedValue, err := runDebug([]string{
		"finish", "--repo", repo, "--id", id,
		"--docviva-kind", "behavioral", "--docviva-outcome", "updated",
		"--docviva-artifact", ".bianchini/current/specs/webhook.md",
		"--docviva-justification", "O contrato de deduplicação corrigido foi registrado.",
	})
	if err != nil {
		t.Fatal(err)
	}
	finished := finishedValue.(map[string]any)
	if stateString(finished["status"]) != "resolved" || stateString(finished["stage"]) != "documented" {
		t.Fatalf("finished=%#v", finished)
	}
	if _, err := os.Lstat(filepath.Join(repo, ".bianchini", "debug", "active", id+".md")); !os.IsNotExist(err) {
		t.Fatalf("active debug remains: %v", err)
	}
	if _, err := os.Lstat(filepath.Join(repo, ".bianchini", "debug", "resolved", id+".md")); err != nil {
		t.Fatal(err)
	}
}

func TestDebugRejectsOutOfOrderAndStaleGreen(t *testing.T) {
	repo := workflowTestRepo(t, false)
	started, err := runDebug([]string{
		"start", "--repo", repo, "--objective", "Falha", "--expected", "esperado", "--actual", "atual", "--environment", "local",
	})
	if err != nil {
		t.Fatal(err)
	}
	id := stateString(started.(map[string]any)["id"])
	for _, test := range []struct {
		event string
		want  string
	}{
		{"green", "ORDER_VIOLATION"},
		{"reproduced", ""},
		{"diagnosed", "STALE_EVIDENCE"},
	} {
		_, err := runDebug([]string{"checkpoint", "--repo", repo, "--id", id, "--event", test.event, "--evidence", "prova"})
		if test.want == "" && err != nil {
			t.Fatalf("%s: %v", test.event, err)
		}
		if test.want != "" && (err == nil || !strings.Contains(err.Error(), test.want)) {
			t.Fatalf("%s err=%v", test.event, err)
		}
	}
}
