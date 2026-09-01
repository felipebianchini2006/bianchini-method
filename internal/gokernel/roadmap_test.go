package gokernel

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func roadmapPlan(identifier string, dependsOn []string, tasks ...map[string]any) map[string]any {
	if len(tasks) == 0 {
		tasks = []map[string]any{{
			"id": "T01", "name": "Entregar", "result": "Resultado observável",
			"covers": []any{"REQ-001"}, "depends_on": []any{}, "files": []any{"src/core.go"},
			"action": "Implementar seam.", "verify": map[string]any{"kind": "command", "run": "go test ./...", "proves": "resultado"},
			"done": "Resultado validado.", "risk_seam": "roadmap",
		}}
	}
	rawDepends := make([]any, len(dependsOn))
	for index, value := range dependsOn {
		rawDepends[index] = value
	}
	rawTasks := make([]any, len(tasks))
	for index, value := range tasks {
		rawTasks[index] = value
	}
	return map[string]any{
		"schema_version": 2, "id": identifier, "status": "planned", "result": "Resultado " + identifier,
		"requirements": []any{"REQ-001"}, "acceptance": []any{"Aceite " + identifier}, "depends_on": rawDepends,
		"provides": []any{}, "consumes": []any{}, "modules": []any{}, "interfaces": []any{}, "ownership": []any{}, "data": []any{},
		"model_delta": map[string]any{}, "migrations": []any{}, "effects": []any{}, "rollback": "Reverter " + identifier,
		"verifications": []any{"go test ./..."}, "future_constraints": []any{}, "execution": "slice", "review": "per_slice", "tasks": rawTasks,
	}
}

func TestRoadmapSyncRendersCanonicalPlans(t *testing.T) {
	repo := goGitRoot(t)
	if code, _, stderr := runCLI(t, "model", "init", "--repo", repo); code != 0 {
		t.Fatal(stderr)
	}
	code, stdout, stderr := runCLI(t, "model", "init", "--repo", repo, "--change", "Roadmap")
	if code != 0 {
		t.Fatal(stderr)
	}
	var created map[string]any
	_ = json.Unmarshal([]byte(stdout), &created)
	change := stateString(created["change"])
	directory := filepath.Join(repo, ".bianchini", "changes", change)
	for _, plan := range []map[string]any{roadmapPlan("P01", nil), roadmapPlan("P02", []string{"P01"})} {
		document, err := frontmatterDocument(plan, "# "+stateString(plan["id"]), false)
		if err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(filepath.Join(directory, "plans", stateString(plan["id"])+".md"), document, 0o600); err != nil {
			t.Fatal(err)
		}
	}
	code, stdout, stderr = runCLI(t, "roadmap", "sync", "--repo", repo, "--change", "C001")
	if code != 0 || stderr != "" {
		t.Fatalf("code=%d stderr=%q", code, stderr)
	}
	var result map[string]any
	if err := json.Unmarshal([]byte(stdout), &result); err != nil {
		t.Fatal(err)
	}
	if result["change"] != change || result["planning_contract"] != float64(2) || result["digest"] == "" {
		t.Fatalf("result=%#v", result)
	}
	roadmap := filepath.Join(directory, "ROADMAP.md")
	metadata, err := readStructuredFrontmatter(roadmap)
	if err != nil {
		t.Fatal(err)
	}
	phases := stateArray(metadata["phases"])
	if len(phases) != 2 || stateString(stateObject(phases[1])["id"]) != "P02" {
		t.Fatalf("metadata=%#v", metadata)
	}
	content, _ := os.ReadFile(roadmap)
	if !strings.Contains(string(content), "## P02 — Resultado P02") || !strings.Contains(string(content), "- Depende de: P01") {
		t.Fatalf("roadmap=%s", content)
	}
	before, _ := os.Stat(roadmap)
	code, _, stderr = runCLI(t, "roadmap", "sync", "--repo", repo, "--change", change)
	if code != 0 || stderr != "" {
		t.Fatal(stderr)
	}
	after, _ := os.Stat(roadmap)
	if before.ModTime() != after.ModTime() {
		t.Fatal("idempotent roadmap sync rewrote identical document")
	}
}

func TestRoadmapSyncRequiresV2Plans(t *testing.T) {
	repo := goGitRoot(t)
	if code, _, stderr := runCLI(t, "model", "init", "--repo", repo); code != 0 {
		t.Fatal(stderr)
	}
	code, stdout, stderr := runCLI(t, "model", "init", "--repo", repo, "--change", "Roadmap")
	if code != 0 {
		t.Fatal(stderr)
	}
	var created map[string]any
	_ = json.Unmarshal([]byte(stdout), &created)
	directory := filepath.Join(repo, ".bianchini", "changes", stateString(created["change"]))
	if err := os.WriteFile(filepath.Join(directory, "plans", "P01.md"), []byte("---\n{\"id\":\"P01\",\"model_delta\":{}}\n---\n# P01\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	code, stdout, stderr = runCLI(t, "roadmap", "sync", "--repo", repo, "--change", "C001")
	if code != 3 || stdout != "" || !strings.Contains(stderr, "roadmap v2 exige") {
		t.Fatalf("code=%d stdout=%q stderr=%q", code, stdout, stderr)
	}
}
