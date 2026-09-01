package gokernel

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestStatusV2ReportsActiveExecutionAndRelease(t *testing.T) {
	state := filepath.Join("..", "..", "tests", "fixtures", "project-state-v2.json")
	result, err := runStatus([]string{state, "--format", "json"})
	if err != nil {
		t.Fatal(err)
	}
	payload := stateObject(result)
	if stateInt(payload["method_version"]) != 2 || stateString(payload["method_mode"]) != "standalone-adaptive" {
		t.Fatalf("identidade v2 divergente: %#v", payload)
	}
	if stateString(payload["approval"]) != "approved" || stateString(payload["approval_digest"]) != "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" {
		t.Fatalf("aprovação divergente: %#v", payload)
	}
	plans := stateObject(payload["plans"])
	if stateString(plans["P01"]) != "approved" || stateString(payload["next_plan"]) != "P01" {
		t.Fatalf("planos divergentes: %#v", payload)
	}
	active := stateObject(payload["active_execution"])
	if active["plan"] != nil || active["unit"] != nil || active["workspace"] != nil {
		t.Fatalf("execução ativa divergente: %#v", active)
	}
	if stateString(stateObject(payload["release"])["status"]) != "pending" {
		t.Fatalf("release divergente: %#v", payload["release"])
	}
}

func TestStatusV2UsesDeclaredActiveExecution(t *testing.T) {
	fixture := filepath.Join("..", "..", "tests", "fixtures", "project-state-v2.json")
	content, err := os.ReadFile(fixture)
	if err != nil {
		t.Fatal(err)
	}
	state := map[string]any{}
	if err := json.Unmarshal(content, &state); err != nil {
		t.Fatal(err)
	}
	stateObject(stateArray(state["plans"])[0])["status"] = "in_progress"
	state["active_execution"] = map[string]any{
		"plan_id": "P01", "unit": "Tarefas 1-2", "gate": "verification.fast", "workspace": "/tmp/bm-p01",
	}
	encoded, err := json.Marshal(state)
	if err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(t.TempDir(), "state.json")
	if err := os.WriteFile(path, encoded, 0o644); err != nil {
		t.Fatal(err)
	}
	result, err := runStatus([]string{path})
	if err != nil {
		t.Fatal(err)
	}
	payload := stateObject(result)
	active := stateObject(payload["active_execution"])
	for key, expected := range map[string]string{
		"plan": "P01", "unit": "Tarefas 1-2", "mode": "grouped", "gate": "verification.fast", "workspace": "/tmp/bm-p01",
	} {
		if stateString(active[key]) != expected {
			t.Fatalf("active_execution.%s=%#v, esperado %q", key, active[key], expected)
		}
	}
}

func TestStatusV2TextMatchesPublicShape(t *testing.T) {
	state := filepath.Join("..", "..", "tests", "fixtures", "project-state-v2.json")
	result, err := runStatus([]string{state, "--format", "text"})
	if err != nil {
		t.Fatal(err)
	}
	text, ok := result.(string)
	if !ok {
		t.Fatalf("status textual retornou %T", result)
	}
	for _, expected := range []string{
		"# Status do projeto\n\n",
		"- Método: v2 standalone-adaptive / planejamento v1\n",
		"- Perfil: lean\n",
		"- Plano ativo: nenhum / unidade nenhuma / modo n/a\n",
		"- Release: pending / homologação pending / revisão pending / entrega pending\n",
		"- Próxima ação: Executar P01.\n",
	} {
		if !strings.Contains(text, expected) {
			t.Fatalf("status textual não contém %q:\n%s", expected, text)
		}
	}
}
