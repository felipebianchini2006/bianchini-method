package gokernel

import (
	"bytes"
	"encoding/json"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"syscall"
	"testing"
)

func runCLI(t *testing.T, args ...string) (int, string, string) {
	t.Helper()
	var stdout, stderr bytes.Buffer
	code := Run(args, &stdout, &stderr)
	return code, stdout.String(), stderr.String()
}

func assertJSONEqual(t *testing.T, got, want string) {
	t.Helper()
	var gotValue, wantValue any
	if err := json.Unmarshal([]byte(got), &gotValue); err != nil {
		t.Fatalf("stdout is not JSON: %v\n%s", err, got)
	}
	if err := json.Unmarshal([]byte(want), &wantValue); err != nil {
		t.Fatalf("invalid expected JSON: %v", err)
	}
	if !reflect.DeepEqual(gotValue, wantValue) {
		t.Fatalf("JSON mismatch\n got: %s\nwant: %s", got, want)
	}
}

func TestVersionJSONIdentifiesOfficialBackend(t *testing.T) {
	code, stdout, stderr := runCLI(t, "version", "--json")
	if code != 0 || stderr != "" {
		t.Fatalf("code=%d stderr=%q", code, stderr)
	}
	var result struct {
		Engine              string   `json:"engine"`
		ContractVersion     string   `json:"contract_version"`
		BuildCommit         string   `json:"build_commit"`
		ImplementedSurfaces []string `json:"implemented_surfaces"`
		Official            bool     `json:"official"`
		Preview             bool     `json:"preview"`
		Version             string   `json:"version"`
	}
	if err := json.Unmarshal([]byte(stdout), &result); err != nil {
		t.Fatal(err)
	}
	if result.Engine != "go" || result.ContractVersion != "0.4" || !result.Official || result.Preview || result.Version != "0.5.0" {
		t.Fatalf("unexpected version identity: %+v", result)
	}
	if result.BuildCommit == "" || len(result.ImplementedSurfaces) != 58 {
		t.Fatalf("missing build metadata: %+v", result)
	}
}

func TestChangePolicyFixtures(t *testing.T) {
	tests := []struct {
		name string
		args []string
		want string
	}{
		{
			name: "read only",
			args: []string{"change-policy"},
			want: `{"action":"decide_reversibly_record_if_material_and_continue","classification":"implementation_detail","extra_review_required":false,"plan_files_mutable":false,"plan_invalidating":false,"reapproval_required":false,"redesign_allowed":false}`,
		},
		{
			name: "material scope",
			args: []string{"change-policy", "--scope-change"},
			want: `{"action":"invalidate_package_and_replan_affected_scope","classification":"material_change","extra_review_required":true,"plan_files_mutable":false,"plan_invalidating":true,"reapproval_required":true,"redesign_allowed":true}`,
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			code, stdout, stderr := runCLI(t, tt.args...)
			if code != 0 || stderr != "" {
				t.Fatalf("code=%d stderr=%q", code, stderr)
			}
			assertJSONEqual(t, stdout, tt.want)
		})
	}
}

func TestDirectClassifyFixtures(t *testing.T) {
	repo := t.TempDir()
	tests := []struct {
		name string
		args []string
		want string
	}{
		{
			name: "default",
			args: []string{"direct", "classify", "--repo", repo},
			want: `{"additional_guards":[],"declared_score":0,"derived_floor":0,"diff_floor":0,"dimensions":{"concurrency":0,"external_effect":0,"migration":0,"money":0,"scope":0},"effective_score":0,"initial_floor":0,"overrides":[],"phase":"start","reasons":[],"reclassified":false,"risk_contract":"quick-risk-floor-v1","risk_inputs":{"declared_paths":[],"flags":{"concurrency":0,"external_effect":0,"migration":0,"money":0,"payment":false,"scope":0,"webhook":false}},"route":"normal","schema_version":1,"score":0,"workflow":"quick"}`,
		},
		{
			name: "protected",
			args: []string{"direct", "classify", "--repo", repo, "--scope-score", "2", "--payment-flow", "--production-authorized"},
			want: `{"additional_guards":["idempotency","persistence","reconciliation","source_of_truth","timeout_recovery"],"declared_score":2,"derived_floor":3,"diff_floor":0,"dimensions":{"concurrency":0,"external_effect":0,"migration":0,"money":0,"scope":2},"effective_score":3,"initial_floor":3,"overrides":["multiple_objectives"],"phase":"start","reasons":["declared_below_floor:2<3","flag:payment=true","flag:scope=2","flags:dimension_total=2","override:multiple_objectives","scope=2"],"reclassified":false,"risk_contract":"quick-risk-floor-v1","risk_inputs":{"declared_paths":[],"flags":{"concurrency":0,"external_effect":0,"migration":0,"money":0,"payment":true,"scope":2,"webhook":false}},"route":"protected","schema_version":1,"score":3,"workflow":"quick"}`,
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			code, stdout, stderr := runCLI(t, tt.args...)
			if code != 0 || stderr != "" {
				t.Fatalf("code=%d stderr=%q", code, stderr)
			}
			assertJSONEqual(t, stdout, tt.want)
		})
	}
}

func TestDirectReopenTerminalIsImmutable(t *testing.T) {
	code, stdout, stderr := runCLI(t, "direct", "reopen", "--repo", t.TempDir(), "--slug", "Q001-terminal", "--next-action", "continuar")
	if code != 2 || stdout != "" || stderr != "ORDER_VIOLATION: quick 0.4 terminal é imutável\n" {
		t.Fatalf("code=%d stdout=%q stderr=%q", code, stdout, stderr)
	}
}

func TestDirectReopenValidatesArgumentsBeforeTerminalError(t *testing.T) {
	code, stdout, stderr := runCLI(t, "direct", "reopen", "--bogus")
	if code != 2 || stdout != "" || !strings.Contains(stderr, "unrecognized arguments: --bogus") {
		t.Fatalf("code=%d stdout=%q stderr=%q", code, stdout, stderr)
	}
}

func TestDirectClassifyRejectsUnsafeRiskPathsLikePython(t *testing.T) {
	tests := []struct {
		name string
		path string
		want string
	}{
		{"non NFC", "src/cafe\u0301.go", "RISK_PATH_INVALID: declared_paths não está em NFC"},
		{"foreign namespace", "src/.planning/x", "RISK_PATH_INVALID: declared_paths usa namespace estrangeiro"},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			code, stdout, stderr := runCLI(
				t,
				"direct",
				"classify",
				"--changed-file",
				test.path,
			)
			if code != 3 || stdout != "" || !strings.Contains(stderr, test.want) {
				t.Fatalf("code=%d stdout=%q stderr=%q", code, stdout, stderr)
			}
		})
	}
}

func TestRetiredCommandsRemainInvalid(t *testing.T) {
	for _, command := range []string{"legacy-transition", "repo-hygiene", "route"} {
		t.Run(command, func(t *testing.T) {
			code, stdout, stderr := runCLI(t, command)
			if code != 2 || stdout != "" {
				t.Fatalf("code=%d stdout=%q", code, stdout)
			}
			want := "bm: error: argument command: invalid choice: '" + command + "'\n"
			if !strings.Contains(stderr, "usage: bm") || !strings.HasSuffix(stderr, want) {
				t.Fatalf("unexpected stderr: %q", stderr)
			}
		})
	}
}

func TestWorkspaceRejectsRetiredCompanionFlags(t *testing.T) {
	repo := t.TempDir()
	state := filepath.Join(repo, "legacy-state.json")
	code, stdout, stderr := runCLI(t, "workspace", "create", "--repo", repo, "--plan", "P01", "--planning-version", "v2", "--state", state)
	want := "bm: error: unrecognized arguments: --planning-version v2 --state " + state + "\n"
	if code != 2 || stdout != "" || !strings.Contains(stderr, "usage: bm") || !strings.HasSuffix(stderr, want) {
		t.Fatalf("code=%d stdout=%q stderr=%q", code, stdout, stderr)
	}
}

func TestStatusLegacyFixtures(t *testing.T) {
	repo := t.TempDir()
	state := filepath.Join(repo, "legacy.md")
	if err := os.WriteFile(state, []byte("method_version: 1\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	code, stdout, stderr := runCLI(t, "status", state, "--format", "json")
	if code != 0 || stderr != "" {
		t.Fatalf("code=%d stderr=%q", code, stderr)
	}
	assertJSONEqual(t, stdout, `{"implicit_legacy":false,"method_mode":"legacy-superpowers","method_version":1,"mode":"legacy-superpowers","status":"legacy"}`)

	code, stdout, stderr = runCLI(t, "status", state, "--root", repo)
	if code != 0 || stderr != "" {
		t.Fatalf("default json with root: code=%d stderr=%q", code, stderr)
	}
	assertJSONEqual(t, stdout, `{"implicit_legacy":false,"method_mode":"legacy-superpowers","method_version":1,"mode":"legacy-superpowers","status":"legacy"}`)

	code, stdout, stderr = runCLI(t, "status", state, "--format", "text")
	want := "# Status do projeto\n\n- Método: v1 legado (Superpowers)\n- Marcador implícito: não\n"
	if code != 0 || stderr != "" || stdout != want {
		t.Fatalf("code=%d stdout=%q stderr=%q", code, stdout, stderr)
	}
}

func TestSpecDiffFixtureAndPathSafety(t *testing.T) {
	repo := t.TempDir()
	base := filepath.Join(repo, "base.md")
	target := filepath.Join(repo, "target.md")
	output := filepath.Join(repo, "diff.md")
	baseData := "# Sistema\n\n## REQ-001 Antes\n\nAntes.\n"
	targetData := "# Sistema\n\n## REQ-001 Depois\n\nDepois.\n\n## REQ-002 Novo\n\nNovo.\n"
	if err := os.WriteFile(base, []byte(baseData), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(target, []byte(targetData), 0o644); err != nil {
		t.Fatal(err)
	}
	code, stdout, stderr := runCLI(t, "spec-diff", "--root", repo, "--base", base, "--target", target, "--output", output)
	if code != 0 || stderr != "" {
		t.Fatalf("code=%d stderr=%q", code, stderr)
	}
	assertJSONEqual(t, stdout, `{"added":["REQ-002"],"base":"base.md","base_digest":"5976dc433f17bf6128fcc0474a1ae15fccac2573db3756c62dc39f77c0a88994","modified":["REQ-001"],"output":"diff.md","output_digest":"76e176197148ee71621746b939ef6d6f7dcb1d559607bdb37f0c8dec7162d6c0","removed":[],"schema_version":1,"target":"target.md","target_digest":"5db96862e6f1a7ac687de5e76de77c155506554bd53e0aed815466343f6bbe33"}`)
	data, err := os.ReadFile(output)
	if err != nil {
		t.Fatal(err)
	}
	wantOutput := "# Spec Diff\n\nEsta é uma projeção derivada. A spec target completa permanece a fonte de verdade.\n\n```json\n{\n  \"added\": [\n    \"REQ-002\"\n  ],\n  \"base\": \"base.md\",\n  \"base_digest\": \"5976dc433f17bf6128fcc0474a1ae15fccac2573db3756c62dc39f77c0a88994\",\n  \"modified\": [\n    \"REQ-001\"\n  ],\n  \"removed\": [],\n  \"schema_version\": 1,\n  \"target\": \"target.md\",\n  \"target_digest\": \"5db96862e6f1a7ac687de5e76de77c155506554bd53e0aed815466343f6bbe33\"\n}\n```\n\n## ADDED\n\n### REQ-002\n\n## REQ-002 Novo\n\nNovo.\n\n\n## MODIFIED\n\n### REQ-001\n\n## REQ-001 Depois\n\nDepois.\n\n\n## REMOVED\n\nNenhum.\n"
	if string(data) != wantOutput {
		t.Fatalf("diff mismatch\n--- got ---\n%s\n--- want ---\n%s", data, wantOutput)
	}
	if err := os.Chmod(output, 0o755); err != nil {
		t.Fatal(err)
	}
	code, _, stderr = runCLI(t, "spec-diff", "--root", repo, "--base", base, "--target", target, "--output", output)
	if code != 0 || stderr != "" {
		t.Fatalf("rewrite code=%d stderr=%q", code, stderr)
	}
	info, err := os.Stat(output)
	if err != nil {
		t.Fatal(err)
	}
	if info.Mode().Perm() != 0o755 {
		t.Fatalf("output mode=%o want=755", info.Mode().Perm())
	}
	restrictedOutput := filepath.Join(repo, "restricted.md")
	oldUmask := syscall.Umask(0o077)
	code, _, stderr = runCLI(t, "spec-diff", "--root", repo, "--base", base, "--target", target, "--output", restrictedOutput)
	syscall.Umask(oldUmask)
	if code != 0 || stderr != "" {
		t.Fatalf("restricted umask code=%d stderr=%q", code, stderr)
	}
	restrictedInfo, err := os.Stat(restrictedOutput)
	if err != nil {
		t.Fatal(err)
	}
	if restrictedInfo.Mode().Perm() != 0o600 {
		t.Fatalf("restricted output mode=%o want=600", restrictedInfo.Mode().Perm())
	}

	code, _, stderr = runCLI(t, "spec-diff", "--root", repo, "--base", filepath.Join(repo, ".planning", "base.md"), "--target", target, "--output", filepath.Join(repo, "unsafe.md"))
	if code != 2 || stderr != "SPEC_PATH_INVALID: spec base usa namespace estrangeiro\n" {
		t.Fatalf("expected .planning rejection, code=%d stderr=%q", code, stderr)
	}
}

func TestStatusRejectsSymlink(t *testing.T) {
	repo := t.TempDir()
	realState := filepath.Join(repo, "real.md")
	linkState := filepath.Join(repo, "link.md")
	if err := os.WriteFile(realState, []byte("method_version: 1\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(realState, linkState); err != nil {
		t.Fatal(err)
	}
	code, _, stderr := runCLI(t, "status", linkState, "--format", "json")
	if code != 2 || !strings.Contains(stderr, "PATH_SAFETY") {
		t.Fatalf("expected symlink rejection, code=%d stderr=%q", code, stderr)
	}
}
