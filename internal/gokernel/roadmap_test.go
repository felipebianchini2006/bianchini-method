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
		"scenarios": []any{map[string]any{"id": "S01", "requirements": []any{"REQ-001"}, "platform": "cli", "profile": "default", "state": "success", "expected": "Resultado observável", "risk": "regressão do contrato declarado", "evidence_kinds": []any{"observation", "log"}}},
	}
}

func writePlanTest(t *testing.T, changeDirectory, slug string, document []byte) string {
	t.Helper()
	directory := filepath.Join(changeDirectory, "plans", slug)
	if err := os.MkdirAll(directory, 0o755); err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(directory, "PLAN.md")
	if err := os.WriteFile(path, document, 0o600); err != nil {
		t.Fatal(err)
	}
	return path
}

func writeManagedSpecTest(t *testing.T, repo, changeDirectory string) {
	t.Helper()
	if err := os.WriteFile(filepath.Join(changeDirectory, "SCOPE.md"), []byte("# Escopo\n\n### REQ-001 Resultado esperado\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(changeDirectory, "specs", "expected", "contract.md"), []byte("# Contrato\n\n## CT-001: Resultado esperado\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	manifest, _ := json.MarshalIndent(map[string]any{
		"schema_version": 1, "spec_contract": 1,
		"specs":         []any{map[string]any{"id": "contract", "path": "contract.md", "requirements": []any{map[string]any{"id": "CT-001", "scope": []any{"REQ-001"}}}}},
		"risk_coverage": []any{},
	}, "", "  ")
	if err := os.WriteFile(filepath.Join(changeDirectory, "specs", "MANIFEST.json"), append(manifest, '\n'), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := syncPlanningSpecs(newMethodWorkspace(repo), changeDirectory, map[string]any{"schema_version": 2, "spec_contract": 1}); err != nil {
		t.Fatal(err)
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
		writePlanTest(t, directory, stateString(plan["id"]), document)
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
	writePlanTest(t, directory, "P01", []byte("---\n{\"id\":\"P01\",\"model_delta\":{}}\n---\n# P01\n"))
	code, stdout, stderr = runCLI(t, "roadmap", "sync", "--repo", repo, "--change", "C001")
	if code != 3 || stdout != "" || !strings.Contains(stderr, "schema_version exige 2") {
		t.Fatalf("code=%d stdout=%q stderr=%q", code, stdout, stderr)
	}
}

func TestRoadmapSyncRejectsDuplicatePlanFileIdentity(t *testing.T) {
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
	document, err := frontmatterDocument(roadmapPlan("P01", nil), "# P01", false)
	if err != nil {
		t.Fatal(err)
	}
	for _, name := range []string{"P01", "P01-fundacao"} {
		writePlanTest(t, directory, name, document)
	}
	code, stdout, stderr = runCLI(t, "roadmap", "sync", "--repo", repo, "--change", "C001")
	if code != 3 || stdout != "" || !strings.Contains(stderr, "arquivos de plano duplicam identidade: P01") {
		t.Fatalf("code=%d stdout=%q stderr=%q", code, stdout, stderr)
	}
}
