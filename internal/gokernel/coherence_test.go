package gokernel

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestCoherenceAndImpactFrozenInputErrors(t *testing.T) {
	tests := []struct {
		name   string
		args   []string
		stderr string
	}{
		{
			name:   "check missing workspace",
			args:   []string{"coherence", "check", "--repo", "REPO", "--change", "fixture"},
			stderr: "erro de entrada/IO: STATE.md ausente: {state}\n",
		},
		{
			name:   "approve requires authority",
			args:   []string{"coherence", "approve", "--repo", "REPO", "--change", "fixture"},
			stderr: "coherence approve exige --digest e --approved-by\n",
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			repo := t.TempDir()
			args := append([]string(nil), test.args...)
			for index, value := range args {
				if value == "REPO" {
					args[index] = repo
				}
			}
			expected := strings.ReplaceAll(test.stderr, "{state}", filepath.Join(repo, ".bianchini", "STATE.md"))
			code, stdout, stderr := runCLI(t, args...)
			if code != 2 || stdout != "" || stderr != expected {
				t.Fatalf("code=%d stdout=%q stderr=%q", code, stdout, stderr)
			}
		})
	}
}

func TestCoherenceSchemaOneStructuralCheckAndApproval(t *testing.T) {
	repo := t.TempDir()
	if err := os.Mkdir(filepath.Join(repo, ".git"), 0o755); err != nil {
		t.Fatal(err)
	}
	code, stdout, stderr := runCLI(t, "model", "init", "--repo", repo, "--change", "legacy package")
	if code != 0 || stderr != "" {
		t.Fatalf("change code=%d stderr=%q", code, stderr)
	}
	var created map[string]any
	if err := json.Unmarshal([]byte(stdout), &created); err != nil {
		t.Fatal(err)
	}
	change := stateString(created["change"])
	directory := filepath.Join(repo, ".bianchini", "changes", change)
	coherence := map[string]any{"schema_version": 1, "planning_contract": 1, "status": "pending"}
	document, _ := frontmatterDocument(coherence, "# Coerência", false)
	if err := os.WriteFile(filepath.Join(directory, "COHERENCE.md"), document, 0o644); err != nil {
		t.Fatal(err)
	}
	plan := map[string]any{
		"id": "P01", "acceptance": []any{"Pacote validado."},
		"verifications": []any{"go test ./..."}, "model_delta": map[string]any{},
	}
	planDocument, _ := frontmatterDocument(plan, "# P01", false)
	if err := os.WriteFile(filepath.Join(directory, "plans", "P01.md"), planDocument, 0o644); err != nil {
		t.Fatal(err)
	}
	code, stdout, stderr = runCLI(t, "coherence", "check", "--repo", repo, "--change", change, "--structural-only")
	if code != 0 || stderr != "" {
		t.Fatalf("check code=%d stderr=%q", code, stderr)
	}
	var checked map[string]any
	if err := json.Unmarshal([]byte(stdout), &checked); err != nil {
		t.Fatal(err)
	}
	if checked["status"] != "structurally_valid" || stateInt(checked["structural_findings"]) != 0 {
		t.Fatalf("checked=%#v", checked)
	}
}

func TestCoherenceSchemaTwoCheckReviewApproveAndStartDescriptivePlan(t *testing.T) {
	repo := t.TempDir()
	if err := os.Mkdir(filepath.Join(repo, ".git"), 0o755); err != nil {
		t.Fatal(err)
	}
	if code, _, stderr := runCLI(t, "model", "init", "--repo", repo); code != 0 {
		t.Fatal(stderr)
	}
	code, stdout, stderr := runCLI(t, "model", "init", "--repo", repo, "--change", "typed package")
	if code != 0 || stderr != "" {
		t.Fatalf("change code=%d stderr=%q", code, stderr)
	}
	var created map[string]any
	if err := json.Unmarshal([]byte(stdout), &created); err != nil {
		t.Fatal(err)
	}
	change := stateString(created["change"])
	directory := filepath.Join(repo, ".bianchini", "changes", change)
	if err := os.WriteFile(filepath.Join(directory, "SCOPE.md"), []byte("# Escopo\n\n### REQ-001 Requisito\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	planDocument, _ := frontmatterDocument(roadmapPlan("P01", nil), "# P01", false)
	if err := os.WriteFile(filepath.Join(directory, "plans", "P01-fundacao.md"), planDocument, 0o600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(directory, "specs", "expected", "api.md"), []byte("# API\n\n## API-001: Responde saúde\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	manifest := []byte("{\n  \"schema_version\": 1,\n  \"spec_contract\": 1,\n  \"specs\": [\n    {\"id\": \"api\", \"path\": \"api.md\", \"requirements\": [{\"id\": \"API-001\", \"scope\": [\"REQ-001\"]}]}\n  ],\n  \"risk_coverage\": []\n}\n")
	manifestPath := filepath.Join(directory, "specs", "MANIFEST.json")
	if err := os.WriteFile(manifestPath, manifest, 0o600); err != nil {
		t.Fatal(err)
	}
	_, diff, err := deriveManagedSpecDiff(repo, filepath.Join(repo, ".bianchini", "current", "specs"), filepath.Join(directory, "specs", "expected"), manifestPath)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(directory, "specs", "diff.md"), diff, 0o600); err != nil {
		t.Fatal(err)
	}
	if code, _, stderr := runCLI(t, "roadmap", "sync", "--repo", repo, "--change", change); code != 0 {
		t.Fatal(stderr)
	}
	code, stdout, stderr = runCLI(t, "coherence", "check", "--repo", repo, "--change", change, "--structural-only")
	if code != 0 || stderr != "" {
		t.Fatalf("structural code=%d stderr=%q", code, stderr)
	}
	var structural map[string]any
	if err := json.Unmarshal([]byte(stdout), &structural); err != nil {
		t.Fatal(err)
	}
	if structural["status"] != "structurally_valid" || stateInt(structural["structural_findings"]) != 0 || structural["spec_contract"] != float64(1) {
		t.Fatalf("structural=%#v", structural)
	}
	report := filepath.Join(repo, "semantic.json")
	reportValue := map[string]any{"prompt": "review", "inputs": structural["review_input_digest"], "sources": []any{"scope"}, "findings": []any{}}
	reportBytes, _ := json.Marshal(reportValue)
	if err := os.WriteFile(report, reportBytes, 0o600); err != nil {
		t.Fatal(err)
	}
	code, stdout, stderr = runCLI(t, "coherence", "check", "--repo", repo, "--change", change, "--semantic-report", report)
	if code != 0 || stderr != "" {
		t.Fatalf("review code=%d stderr=%q", code, stderr)
	}
	var reviewed map[string]any
	if err := json.Unmarshal([]byte(stdout), &reviewed); err != nil {
		t.Fatal(err)
	}
	digest := stateString(reviewed["digest"])
	code, stdout, stderr = runCLI(t, "coherence", "approve", "--repo", repo, "--change", change, "--digest", digest, "--approved-by", "human:test")
	if code != 0 || stderr != "" {
		t.Fatalf("approve code=%d stderr=%q", code, stderr)
	}
	var approved map[string]any
	if err := json.Unmarshal([]byte(stdout), &approved); err != nil {
		t.Fatal(err)
	}
	if approved["status"] != "approved" || approved["digest"] != digest || approved["approved_by"] != "human:test" {
		t.Fatalf("approved=%#v", approved)
	}
	code, stdout, stderr = runCLI(t, "roadmap", "next-wave", "--repo", repo, "--change", change)
	if code != 0 || stderr != "" {
		t.Fatalf("next-wave code=%d stderr=%q", code, stderr)
	}
	var wave map[string]any
	if err := json.Unmarshal([]byte(stdout), &wave); err != nil {
		t.Fatal(err)
	}
	eligible := stateArray(wave["eligible_wave"])
	if len(eligible) != 1 || stateString(eligible[0]) != "C001/P01/T01" {
		t.Fatalf("wave=%#v", wave)
	}
}
