package gokernel

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func legacyWriteFixtureFile(t *testing.T, root, relative, content string) {
	t.Helper()
	path := filepath.Join(root, filepath.FromSlash(relative))
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, []byte(content), 0o600); err != nil {
		t.Fatal(err)
	}
}

func legacyQualityV2Fixture(t *testing.T) (string, string, string) {
	t.Helper()
	root := t.TempDir()
	const (
		changeRoot = "docs/bianchini/changes/v1"
		scopeRel   = changeRoot + "/inputs/APPROVED_SCOPE.md"
		research   = changeRoot + "/STACK_RESEARCH.md"
		readiness  = changeRoot + "/READINESS.md"
		actions    = changeRoot + "/USER_ACTIONS.md"
		spec       = changeRoot + "/specs/system-change.md"
		delta      = changeRoot + "/spec-deltas/system.md"
		review     = changeRoot + "/PLANNING_REVIEW.md"
		planRel    = changeRoot + "/plans/P01-system.md"
	)
	legacyWriteFixtureFile(t, root, scopeRel, "# Scope\n\nApproved behavior.\n")
	legacyWriteFixtureFile(t, root, research,
		"# Stack Research\n\nResearch mode: repo_only\nMotivo: stack local estável e sem integração nova.\n\n"+
			"## Stack detectada\n\n- Go.\n\n## Inventário local\n\n- Manifests: go.mod.\n- Lockfiles: nenhum.\n- CI: go test.\n- Testes: go test.\n- Padrões locais: stdlib.\n\n"+
			"## Decisões aplicadas\n\n- D-001 usa sessão.\n\n## Riscos e lacunas\n\n- P-001 cobre restart.\n")
	legacyWriteFixtureFile(t, root, actions, "# User Actions\n\n## U-001\n\nProvide sandbox credential.\n")
	legacyWriteFixtureFile(t, root, spec,
		"# Change Spec\n\n## Contracts\n\nD-001 A-001 P-001 U-001 SD-001 define the current behavior.\n\n## Unrelated\n\nDo not hydrate this section.\n")
	legacyWriteFixtureFile(t, root, delta, "# Delta\n\nSD-001 updates the persisted contract.\n")
	legacyWriteFixtureFile(t, root, review, "```json\n{\"verdict\":\"passed\",\"findings\":[]}\n```\n")
	legacyWriteFixtureFile(t, root, planRel,
		"# P01\n\n### Task T01\n\n**Execution:** slice\n**Review:** per_slice\n**Change:** state-machine\n"+
			"**Readiness refs:** D-001, A-001, P-001, U-001, SD-001\n**Test seams:** session\n"+
			"**Spec refs:** specs/system-change.md#contracts\n**Files:** internal/session.go\n"+
			"**Contract:** login persists a valid session\n**Verification:** `go test ./...` exits zero\n"+
			"**Done when:** restart recovery passes\n")
	ledgerRel := "artifacts/bianchini/v1/ledgers/P01.md"
	legacyWriteFixtureFile(t, root, ledgerRel, "old\nlatest\n")
	if err := os.MkdirAll(filepath.Join(root, "docs/bianchini/current/specs"), 0o755); err != nil {
		t.Fatal(err)
	}
	scopeDigest, _ := legacyFileDigest(filepath.Join(root, filepath.FromSlash(scopeRel)))
	readinessValue := map[string]any{
		"schema_version": 1, "status": "ready", "scope_digest": scopeDigest,
		"repository_revision": "new-project", "design_required": false,
		"impact_map": map[string]any{
			"applications": []string{"web"}, "modules": []string{"auth"},
			"contracts": []string{"session"}, "data": []string{"users"}, "platforms": []string{"browser"},
		},
		"decisions": []map[string]any{{
			"id": "D-001", "statement": "Use authenticated sessions.", "evidence": "scope",
			"destinations": []string{spec, planRel},
		}},
		"assumptions": []map[string]any{{
			"id": "A-001", "statement": "Local session is enough.", "impact": "high", "status": "bounded",
			"evidence": "research", "fallback": "Block external release.", "destinations": []string{spec, planRel},
		}},
		"pitfalls": []map[string]any{{
			"id": "P-001", "statement": "Restart loses session.", "impact": "high", "prevention": "Persist.",
			"recovery": "Return to login.", "verification": "Restart test.", "destinations": []string{spec, planRel},
		}},
		"user_actions": []map[string]any{{
			"id": "U-001", "action": "Provide credential.", "needed_by": "P01", "can_continue_without": true,
			"fallback": "Local fixture.", "evidence_required": "Credential present.", "destinations": []string{actions, planRel},
		}},
		"spikes": []map[string]any{}, "design_surfaces": []map[string]any{},
		"spec_deltas": []map[string]any{{
			"id": "SD-001", "domain": "system", "source": delta,
			"target": "docs/bianchini/current/specs/system.md", "destinations": []string{spec, planRel, delta},
		}},
	}
	readinessJSON, _ := json.MarshalIndent(readinessValue, "", "  ")
	legacyWriteFixtureFile(t, root, readiness, "# Readiness\n\n```json\n"+string(readinessJSON)+"\n```\n")

	fixture, err := os.ReadFile("../../tests/fixtures/project-state-v2.json")
	if err != nil {
		t.Fatal(err)
	}
	var state map[string]any
	if err := json.Unmarshal(fixture, &state); err != nil {
		t.Fatal(err)
	}
	state["planning_status"] = "in_progress"
	state["assurance_profile"] = "standard"
	state["scope"] = map[string]any{"status": "approved", "source": scopeRel, "approved_at": "2026-09-01T10:00:00Z"}
	state["planning"] = map[string]any{
		"quality_version": 2, "research_mode": "repo_only", "research": research,
		"readiness": readiness, "user_actions": actions, "spec": spec, "review": review,
		"checker":         map[string]any{"status": "pending", "rounds": 0, "history_path": "artifacts/bianchini/v1/checker.jsonl", "package_digest": nil, "report_digest": nil},
		"design_manifest": nil, "change_root": changeRoot, "current_specs": "docs/bianchini/current/specs",
	}
	state["complexity_review"] = map[string]any{
		"decision": "within_budget", "justification": nil, "deferred_scope": []string{},
		"scope_split_approved": false, "scope_split_approved_by": nil, "scope_split_approved_at": nil,
	}
	state["approval"] = map[string]any{
		"status": "pending", "approved_at": nil, "approved_by": nil, "approved_plans": []string{},
		"package": map[string]any{"algorithm": "sha256-manifest-v1", "manifest_path": "artifacts/bianchini/v1/manifest.sha256", "manifest_digest": nil, "files": []string{scopeRel, research, readiness, actions, spec, delta, review, planRel}},
	}
	state["plans"] = []map[string]any{{
		"id": "P01", "path": planRel, "status": "planned", "risk": "medium", "execution": "slice", "review": "per_slice",
		"test_seams": []string{"session"}, "depends_on": []string{}, "ledger": ledgerRel, "gates": []string{"test"},
	}}
	state["verification"] = map[string]any{
		"fast":    map[string]any{"commands": []string{"go test ./internal/session"}, "status": "pending"},
		"plan":    map[string]any{"commands": []string{"go test ./..."}, "status": "pending"},
		"release": map[string]any{"commands": []string{"go test ./..."}, "status": "pending"},
	}
	statePath := filepath.Join(root, "PROJECT_STATE.json")
	encoded, _ := legacyJSONBytes(state, true)
	if err := os.WriteFile(statePath, encoded, 0o600); err != nil {
		t.Fatal(err)
	}
	return root, statePath, planRel
}

func legacyStateFixture(t *testing.T, root string) string {
	t.Helper()
	raw, err := os.ReadFile(filepath.Join("..", "..", "tests", "fixtures", "project-state-v2.json"))
	if err != nil {
		t.Fatalf("read state fixture: %v", err)
	}
	var state map[string]any
	if err := json.Unmarshal(raw, &state); err != nil {
		t.Fatalf("decode state fixture: %v", err)
	}
	approval := state["approval"].(map[string]any)
	pack := approval["package"].(map[string]any)
	for _, rawPath := range pack["files"].([]any) {
		path := filepath.Join(root, filepath.FromSlash(rawPath.(string)))
		if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
			t.Fatal(err)
		}
		content := []byte("# Fixture\n")
		if strings.Contains(path, "P01-crud.md") {
			content = []byte("# P01\n\n### Tarefa 1 — Entrega\n\n**Execution:** grouped\n**Review:** plan_gate\n**Test seams:** unit\n**Spec refs:** specs/system.md#behavior\n**Files:** src/app.py\n**Contract:** input produces output\n**Verification:** `python3 -m unittest` exits zero\n**Done when:** behavior passes\n")
		}
		if err := os.WriteFile(path, content, 0o644); err != nil {
			t.Fatal(err)
		}
	}
	statePath := filepath.Join(root, "PROJECT_STATE.json")
	encoded, err := json.Marshal(state)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(statePath, encoded, 0o644); err != nil {
		t.Fatal(err)
	}
	return statePath
}

func TestRunSnapshotCreateAndVerify(t *testing.T) {
	root := t.TempDir()
	state := legacyStateFixture(t, root)

	created, err := runSnapshot([]string{"create", state, "--root", root})
	if err != nil {
		t.Fatalf("create snapshot: %v", err)
	}
	result := created.(map[string]any)
	if result["algorithm"] != "sha256-manifest-v1" {
		t.Fatalf("algorithm = %v", result["algorithm"])
	}
	manifest := result["manifest"].(string)
	content, err := os.ReadFile(manifest)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(content), "  docs/scope.md\n") {
		t.Fatalf("manifest missing normalized path: %s", content)
	}

	var value map[string]any
	raw, _ := os.ReadFile(state)
	_ = json.Unmarshal(raw, &value)
	value["approval"].(map[string]any)["package"].(map[string]any)["manifest_digest"] = result["digest"]
	raw, _ = json.Marshal(value)
	_ = os.WriteFile(state, raw, 0o644)
	verified, err := runSnapshot([]string{"verify", state, "--root", root})
	if err != nil {
		t.Fatalf("verify snapshot: %v", err)
	}
	if verified.(map[string]any)["digest"] != result["digest"] {
		t.Fatal("verify returned another digest")
	}
}

func TestRunDesignAuditSealVerifyAndRejectSymlink(t *testing.T) {
	root := t.TempDir()
	scope := filepath.Join(root, "scope.md")
	design := filepath.Join(root, "design")
	if err := os.MkdirAll(design, 0o755); err != nil {
		t.Fatal(err)
	}
	_ = os.WriteFile(scope, []byte("# Scope\n"), 0o644)
	files := []string{"design/contract.md", "design/prototype.html", "design/tokens.css", "design/screen.png"}
	for _, relative := range files {
		_ = os.WriteFile(filepath.Join(root, relative), []byte("fixture\n"), 0o644)
	}
	manifestPath := filepath.Join(design, "manifest.json")
	manifest := map[string]any{
		"schema_version": 1, "status": "draft", "source": "imported",
		"scope_source": nil, "scope_digest": nil, "design_digest": nil,
		"contract": files[0], "prototype": files[1], "tokens": files[2],
		"screenshots": []string{files[3]}, "surfaces": []string{"checkout"},
		"breakpoints": []string{"mobile"}, "files": files,
	}
	raw, _ := json.Marshal(manifest)
	_ = os.WriteFile(manifestPath, raw, 0o644)

	sealed, err := runDesignAudit([]string{"seal", "--root", root, "--scope", scope, "--manifest", manifestPath})
	if err != nil {
		t.Fatalf("seal design: %v", err)
	}
	sealedResult := sealed.(map[string]any)
	if len(sealedResult["design_digest"].(string)) != 64 {
		t.Fatalf("invalid design digest: %v", sealedResult["design_digest"])
	}
	raw, _ = os.ReadFile(manifestPath)
	_ = json.Unmarshal(raw, &manifest)
	manifest["status"] = "approved"
	raw, _ = json.Marshal(manifest)
	_ = os.WriteFile(manifestPath, raw, 0o644)
	verified, err := runDesignAudit([]string{"verify", "--root", root, "--scope", scope, "--manifest", manifestPath})
	if err != nil {
		t.Fatalf("verify design: %v", err)
	}
	if verified.(map[string]any)["design_digest"] != sealedResult["design_digest"] {
		t.Fatal("design digest changed after approval")
	}

	outside := filepath.Join(t.TempDir(), "outside.md")
	_ = os.WriteFile(outside, []byte("outside"), 0o644)
	link := filepath.Join(design, "escape.md")
	if err := os.Symlink(outside, link); err != nil {
		t.Fatal(err)
	}
	manifest["files"] = append(files, "design/escape.md")
	raw, _ = json.Marshal(manifest)
	_ = os.WriteFile(manifestPath, raw, 0o644)
	if _, err := runDesignAudit([]string{"seal", "--root", root, "--scope", scope, "--manifest", manifestPath}); err == nil {
		t.Fatal("expected symlink escape to fail")
	}
}

func TestRunPlanningAuditLegacyCompatible(t *testing.T) {
	root := t.TempDir()
	state := legacyStateFixture(t, root)
	result, err := runPlanningAudit([]string{state, "--root", root})
	if err != nil {
		t.Fatalf("planning audit: %v", err)
	}
	value := result.(map[string]any)
	if value["valid"] != true || value["quality_contract"] != "legacy-compatible" {
		t.Fatalf("unexpected audit: %#v", value)
	}
}

func TestRunPlanningCheckMissingStateFailsBeforeMutation(t *testing.T) {
	root := t.TempDir()
	_, err := runPlanningCheck([]string{
		"record", "--state", filepath.Join(root, "missing.json"),
		"--root", root, "--report", filepath.Join(root, "report.json"),
	})
	if err == nil || !strings.Contains(err.Error(), "estado não encontrado") {
		t.Fatalf("unexpected error: %v", err)
	}
	if _, statErr := os.Stat(filepath.Join(root, "report.json")); !os.IsNotExist(statErr) {
		t.Fatal("missing-state check mutated report")
	}
}

func TestRunPlanningAuditQualityV2DeepContract(t *testing.T) {
	root, state, _ := legacyQualityV2Fixture(t)
	review := filepath.Join(root, "docs/bianchini/changes/v1/PLANNING_REVIEW.md")
	if _, err := runPlanningCheck([]string{"record", "--state", state, "--root", root, "--report", review}); err != nil {
		t.Fatalf("record checker: %v", err)
	}
	result, err := runPlanningAudit([]string{state, "--root", root, "--strict"})
	if err != nil {
		t.Fatalf("deep planning audit: %v", err)
	}
	value := result.(map[string]any)
	if value["quality_contract"] != "planning-quality-v2" || value["research_mode"] != "repo_only" {
		t.Fatalf("unexpected contract: %#v", value)
	}
	readiness := stateObject(value["readiness"])
	counts, _ := readiness["counts"].(map[string]int)
	gaps, _ := readiness["coverage_gaps"].([]string)
	if counts["spec_deltas"] != 1 || len(gaps) != 0 {
		t.Fatalf("unexpected readiness summary: %#v", readiness)
	}
	if _, ok := value["budget_exceeded"].([]string); !ok {
		t.Fatalf("budget_exceeded must be a list: %#v", value["budget_exceeded"])
	}
}

func TestRunPlanningAuditRejectsResearchReadinessAndComplexityDrift(t *testing.T) {
	tests := []struct {
		name   string
		mutate func(root, state string)
		want   string
	}{
		{
			name: "research",
			mutate: func(root, _ string) {
				path := filepath.Join(root, "docs/bianchini/changes/v1/STACK_RESEARCH.md")
				_ = os.WriteFile(path, []byte("# opinion only\n"), 0o600)
			},
			want: "pesquisa repo_only: inventário ausente",
		},
		{
			name: "readiness destination",
			mutate: func(root, _ string) {
				path := filepath.Join(root, "docs/bianchini/changes/v1/specs/system-change.md")
				data, _ := os.ReadFile(path)
				_ = os.WriteFile(path, []byte(strings.ReplaceAll(string(data), "D-001", "D-REMOVED")), 0o600)
			},
			want: "readiness D-001: ID ausente no destino",
		},
		{
			name: "unauthorized split",
			mutate: func(_ string, statePath string) {
				data, _ := os.ReadFile(statePath)
				var state map[string]any
				_ = json.Unmarshal(data, &state)
				complexity := stateObject(state["complexity_review"])
				complexity["decision"] = "split"
				complexity["deferred_scope"] = []string{"payment"}
				encoded, _ := legacyJSONBytes(state, true)
				_ = os.WriteFile(statePath, encoded, 0o600)
			},
			want: "escopo aprovado não pode ser adiado",
		},
		{
			name: "duplicated readiness ref",
			mutate: func(root, _ string) {
				path := filepath.Join(root, "docs/bianchini/changes/v1/plans/P01-system.md")
				data, _ := os.ReadFile(path)
				updated := strings.Replace(string(data), "D-001, A-001, P-001, U-001, SD-001", "D-001, D-001, A-001, P-001, U-001, SD-001", 1)
				_ = os.WriteFile(path, []byte(updated), 0o600)
			},
			want: "Readiness refs contém duplicatas",
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			root, state, _ := legacyQualityV2Fixture(t)
			test.mutate(root, state)
			_, err := legacyPlanningAudit(state, root, true, false)
			if err == nil || !strings.Contains(err.Error(), test.want) {
				t.Fatalf("expected %q, got %v", test.want, err)
			}
		})
	}
}

func TestRunPlanningAuditRejectsCheckerDigestAfterPackageDrift(t *testing.T) {
	root, state, _ := legacyQualityV2Fixture(t)
	review := filepath.Join(root, "docs/bianchini/changes/v1/PLANNING_REVIEW.md")
	if _, err := runPlanningCheck([]string{"record", "--state", state, "--root", root, "--report", review}); err != nil {
		t.Fatalf("record checker: %v", err)
	}
	spec := filepath.Join(root, "docs/bianchini/changes/v1/specs/system-change.md")
	stream, err := os.OpenFile(spec, os.O_APPEND|os.O_WRONLY, 0)
	if err != nil {
		t.Fatal(err)
	}
	_, _ = stream.WriteString("\nMaterial change after review.\n")
	_ = stream.Close()
	_, err = runPlanningAudit([]string{state, "--root", root, "--strict"})
	if err == nil || !strings.Contains(err.Error(), "planning.checker.package_digest: pacote mudou após a revisão") {
		t.Fatalf("expected stale checker rejection, got %v", err)
	}
}
