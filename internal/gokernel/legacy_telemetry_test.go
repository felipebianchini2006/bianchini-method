package gokernel

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func legacyTelemetryFixture(t *testing.T, enabled bool) (string, string) {
	t.Helper()
	root := t.TempDir()
	statePath := legacyStateFixture(t, root)
	data, _ := os.ReadFile(statePath)
	var state map[string]any
	_ = json.Unmarshal(data, &state)
	state["telemetry"] = map[string]any{"enabled": enabled, "path": "artifacts/telemetry.jsonl"}
	encoded, _ := legacyJSONBytes(state, true)
	if err := os.WriteFile(statePath, encoded, 0o600); err != nil {
		t.Fatal(err)
	}
	return root, statePath
}

func TestRunTelemetryDisabled(t *testing.T) {
	root, state := legacyTelemetryFixture(t, false)
	result, err := runTelemetry([]string{"record", "--state", state, "--root", root, "--duration-ms", "10"})
	if err != nil {
		t.Fatalf("disabled telemetry: %v", err)
	}
	if result.(map[string]any)["recorded"] != false {
		t.Fatalf("disabled telemetry recorded: %#v", result)
	}
}

func TestRunTelemetryRecordAndSummary(t *testing.T) {
	root, state := legacyTelemetryFixture(t, true)
	for _, args := range [][]string{
		{"record", "--state", state, "--root", root, "--plan", "P01", "--phase", "execution", "--at", "2026-09-01T12:00:00Z", "--input-tokens", "5", "--duration-ms", "10"},
		{"record", "--state", state, "--root", root, "--phase", "gate", "--output-tokens", "3", "--gate-failures", "1"},
	} {
		if _, err := runTelemetry(args); err != nil {
			t.Fatalf("record telemetry: %v", err)
		}
	}
	result, err := runTelemetry([]string{"summary", "--state", state, "--root", root})
	if err != nil {
		t.Fatalf("summary telemetry: %v", err)
	}
	value := result.(map[string]any)
	if value["records"] != 2 || stateInt(stateObject(value["totals"])["duration_ms"]) != 10 {
		t.Fatalf("unexpected telemetry summary: %#v", value)
	}
	plans := stateObject(value["plans"])
	if _, ok := plans["P01"]; !ok {
		t.Fatalf("plan totals missing: %#v", value)
	}
	if _, ok := plans["_release"]; !ok {
		t.Fatalf("release totals missing: %#v", value)
	}
}

func TestRunTelemetryRejectsInvalidJournalAndNegativeMetric(t *testing.T) {
	root, state := legacyTelemetryFixture(t, true)
	_, err := runTelemetry([]string{"record", "--state", state, "--root", root, "--duration-ms", "-1"})
	if err == nil || !strings.Contains(err.Error(), "não podem ser negativas") {
		t.Fatalf("expected negative rejection, got %v", err)
	}
	path := filepath.Join(root, "artifacts", "telemetry.jsonl")
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, []byte("{truncated\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	_, err = runTelemetry([]string{"summary", "--state", state, "--root", root})
	if err == nil || !strings.Contains(err.Error(), "telemetria inválida na linha 1") {
		t.Fatalf("expected invalid journal failure, got %v", err)
	}
}
