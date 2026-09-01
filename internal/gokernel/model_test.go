package gokernel

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func goGitRoot(t *testing.T) string {
	t.Helper()
	repo := t.TempDir()
	if err := os.Mkdir(filepath.Join(repo, ".git"), 0o755); err != nil {
		t.Fatal(err)
	}
	return repo
}

func TestModelInitAndValidateWorkspace(t *testing.T) {
	repo := goGitRoot(t)
	code, stdout, stderr := runCLI(t, "model", "init", "--repo", repo)
	if code != 0 || stderr != "" {
		t.Fatalf("code=%d stderr=%q", code, stderr)
	}
	var initialized map[string]any
	if err := json.Unmarshal([]byte(stdout), &initialized); err != nil {
		t.Fatal(err)
	}
	if initialized["method"] != "0.4" || initialized["status"] != "idle" || initialized["created"] != true {
		t.Fatalf("initialized=%#v", initialized)
	}
	for _, relative := range []string{
		".bianchini/STATE.md", ".bianchini/PROJECT.md", ".bianchini/.gitignore",
		".bianchini/current/ARCHITECTURE.md", ".bianchini/current/SYSTEM_MODEL.md",
		".bianchini/current/specs/MANIFEST.json", ".bianchini/debug/KNOWLEDGE.md",
	} {
		if info, err := os.Lstat(filepath.Join(repo, relative)); err != nil || !info.Mode().IsRegular() {
			t.Fatalf("missing regular %s: %v", relative, err)
		}
	}
	code, stdout, stderr = runCLI(t, "model", "validate", "--repo", repo)
	if code != 0 || stderr != "" {
		t.Fatalf("validate code=%d stderr=%q", code, stderr)
	}
	var validated map[string]any
	if err := json.Unmarshal([]byte(stdout), &validated); err != nil {
		t.Fatal(err)
	}
	if validated["valid"] != true || validated["method"] != "0.4" || validated["status"] != "idle" {
		t.Fatalf("validated=%#v", validated)
	}
}

func TestModelInitIsIdempotent(t *testing.T) {
	repo := goGitRoot(t)
	code, _, stderr := runCLI(t, "model", "init", "--repo", repo)
	if code != 0 || stderr != "" {
		t.Fatal(stderr)
	}
	state := filepath.Join(repo, ".bianchini", "STATE.md")
	before, err := os.ReadFile(state)
	if err != nil {
		t.Fatal(err)
	}
	infoBefore, err := os.Stat(state)
	if err != nil {
		t.Fatal(err)
	}
	code, stdout, stderr := runCLI(t, "model", "init", "--repo", repo)
	if code != 0 || stderr != "" {
		t.Fatalf("code=%d stderr=%q", code, stderr)
	}
	var result map[string]any
	if err := json.Unmarshal([]byte(stdout), &result); err != nil {
		t.Fatal(err)
	}
	if result["created"] != false {
		t.Fatalf("result=%#v", result)
	}
	after, err := os.ReadFile(state)
	if err != nil {
		t.Fatal(err)
	}
	infoAfter, err := os.Stat(state)
	if err != nil {
		t.Fatal(err)
	}
	if string(after) != string(before) || infoAfter.ModTime() != infoBefore.ModTime() {
		t.Fatal("idempotent init rewrote state")
	}
}

func TestModelInitCreatesManagedChange(t *testing.T) {
	repo := goGitRoot(t)
	code, _, stderr := runCLI(t, "model", "init", "--repo", repo)
	if code != 0 || stderr != "" {
		t.Fatal(stderr)
	}
	code, stdout, stderr := runCLI(t, "model", "init", "--repo", repo, "--change", "Checkout seguro")
	if code != 0 || stderr != "" {
		t.Fatalf("code=%d stderr=%q", code, stderr)
	}
	var result map[string]any
	if err := json.Unmarshal([]byte(stdout), &result); err != nil {
		t.Fatal(err)
	}
	if result["change"] != "C001-checkout-seguro" || result["spec_contract"] != float64(1) {
		t.Fatalf("result=%#v", result)
	}
	directory := filepath.Join(repo, ".bianchini", "changes", "C001-checkout-seguro")
	for _, relative := range []string{
		"SCOPE.md", "RESEARCH.md", "ARCHITECTURE.md", "SYSTEM_MODEL.md", "ROADMAP.md",
		"SUMMARY.md", "COHERENCE.md", "specs/MANIFEST.json",
	} {
		if info, err := os.Lstat(filepath.Join(directory, relative)); err != nil || !info.Mode().IsRegular() {
			t.Fatalf("missing regular %s: %v", relative, err)
		}
	}
	coherence, err := readJSONFrontmatter(filepath.Join(directory, "COHERENCE.md"), "COHERENCE.md")
	if err != nil {
		t.Fatal(err)
	}
	if stateInt(coherence["schema_version"]) != 2 || stateInt(coherence["planning_contract"]) != 2 || stateInt(coherence["spec_contract"]) != 1 {
		t.Fatalf("coherence=%#v", coherence)
	}
}

func TestModelRejectsNonGitAndSymlinkRoot(t *testing.T) {
	repo := t.TempDir()
	code, stdout, stderr := runCLI(t, "model", "init", "--repo", repo)
	if code != 3 || stdout != "" || stderr != "DIRTY_WORKSPACE: o diretório não é uma raiz Git\n" {
		t.Fatalf("code=%d stdout=%q stderr=%q", code, stdout, stderr)
	}
	real := goGitRoot(t)
	link := filepath.Join(t.TempDir(), "repo")
	if err := os.Symlink(real, link); err != nil {
		t.Fatal(err)
	}
	code, stdout, stderr = runCLI(t, "model", "init", "--repo", link)
	if code != 3 || stdout != "" || !strings.Contains(stderr, "DIRTY_WORKSPACE") {
		t.Fatalf("code=%d stdout=%q stderr=%q", code, stdout, stderr)
	}
}

func TestModelValidateSimulatesPlans(t *testing.T) {
	repo := goGitRoot(t)
	if code, _, stderr := runCLI(t, "model", "init", "--repo", repo); code != 0 {
		t.Fatal(stderr)
	}
	if code, _, stderr := runCLI(t, "model", "init", "--repo", repo, "--change", "Contrato de saude"); code != 0 {
		t.Fatal(stderr)
	}
	directory := filepath.Join(repo, ".bianchini", "changes", "C001-contrato-de-saude")
	expected := `---
schema_version: 1
modules: []
interfaces: []
capabilities: []
contracts:
  - id: health_checked
    owner: api
ownership: []
data: []
integrations: []
journeys: []
invariants: []
effects: []
---
# Modelo esperado
`
	if err := os.WriteFile(filepath.Join(directory, "SYSTEM_MODEL.md"), []byte(expected), 0o600); err != nil {
		t.Fatal(err)
	}
	plan := `---
id: P01
model_delta:
  contracts:
    add:
      - id: health_checked
        owner: api
---
# Plano
`
	if err := os.WriteFile(filepath.Join(directory, "plans", "P01.md"), []byte(plan), 0o600); err != nil {
		t.Fatal(err)
	}
	coherence := `---
{"schema_version":1,"planning_contract":1,"change":"C001-contrato-de-saude","status":"pending"}
---
# Coerencia
`
	if err := os.WriteFile(filepath.Join(directory, "COHERENCE.md"), []byte(coherence), 0o600); err != nil {
		t.Fatal(err)
	}
	code, stdout, stderr := runCLI(t, "model", "validate", "--repo", repo, "--change", "C001")
	if code != 0 || stderr != "" {
		t.Fatalf("code=%d stderr=%q", code, stderr)
	}
	var result map[string]any
	if err := json.Unmarshal([]byte(stdout), &result); err != nil {
		t.Fatal(err)
	}
	if result["valid"] != true || result["change"] != "C001-contrato-de-saude" {
		t.Fatalf("result=%#v", result)
	}
	if result["current_digest"] == "" || result["calculated_digest"] != result["expected_digest"] {
		t.Fatalf("digests=%#v", result)
	}
	if differences, ok := result["differences"].(map[string]any); !ok || len(differences) != 0 {
		t.Fatalf("differences=%#v", result["differences"])
	}
}

func TestProjectModelYAMLAndPlanValidationTable(t *testing.T) {
	tests := []struct {
		name    string
		content string
		wantErr string
	}{
		{
			name: "yaml mapping and sequence",
			content: `---
schema_version: 1
modules:
  core:
    owner: platform
interfaces:
  - id: health
capabilities: []
contracts: []
ownership: []
data: []
integrations: []
journeys: []
invariants: []
effects: []
---
`,
		},
		{
			name: "unknown section",
			content: `---
schema_version: 1
unknown: []
---
`,
			wantErr: "seção desconhecida",
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			path := filepath.Join(t.TempDir(), "SYSTEM_MODEL.md")
			if err := os.WriteFile(path, []byte(test.content), 0o600); err != nil {
				t.Fatal(err)
			}
			model, err := loadProjectModel(path)
			if test.wantErr != "" {
				if err == nil || !strings.Contains(err.Error(), test.wantErr) {
					t.Fatalf("err=%v", err)
				}
				return
			}
			if err != nil {
				t.Fatal(err)
			}
			if model.sections["modules"]["core"]["owner"] != "platform" || model.sections["interfaces"]["health"]["id"] != "health" {
				t.Fatalf("model=%#v", model.mapping())
			}
		})
	}
}

func TestModelValidateManagedSpecPackage(t *testing.T) {
	repo := goGitRoot(t)
	if code, _, stderr := runCLI(t, "model", "init", "--repo", repo); code != 0 {
		t.Fatal(stderr)
	}
	if code, _, stderr := runCLI(t, "model", "init", "--repo", repo, "--change", "Spec gerenciada"); code != 0 {
		t.Fatal(stderr)
	}
	directory := filepath.Join(repo, ".bianchini", "changes", "C001-spec-gerenciada")
	if err := os.WriteFile(filepath.Join(directory, "SCOPE.md"), []byte("# Escopo\n\n### REQ-001 Requisito\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(directory, "plans", "P01.md"), []byte("---\n{\"id\":\"P01\",\"model_delta\":{}}\n---\n# Plano\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	specPath := filepath.Join(directory, "specs", "expected", "api.md")
	if err := os.WriteFile(specPath, []byte("# API\n\n## API-001: Responde saude\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	manifest := `{
  "schema_version": 1,
  "spec_contract": 1,
  "specs": [
    {"id": "api", "path": "api.md", "requirements": [{"id": "API-001", "scope": ["REQ-001"]}]}
  ],
  "risk_coverage": []
}
`
	manifestPath := filepath.Join(directory, "specs", "MANIFEST.json")
	if err := os.WriteFile(manifestPath, []byte(manifest), 0o600); err != nil {
		t.Fatal(err)
	}
	metadata, rendered, err := deriveManagedSpecDiff(repo, filepath.Join(repo, ".bianchini", "current", "specs"), filepath.Join(directory, "specs", "expected"), manifestPath)
	if err != nil {
		t.Fatal(err)
	}
	if metadata["mode"] != "directory" || metadata["target_digest"] == "" {
		t.Fatalf("metadata=%#v", metadata)
	}
	expectedDigests := map[string]string{
		"base_digest":            "2c3effa6cac92be128ed68e7733b5ed057b027c01006219120d6ba2d177c335f",
		"target_digest":          "a934db2c5762e07fa1b70f31b74346fdd08ac836d042005f60edfbe882b0ff81",
		"base_manifest_digest":   "8fe693a685236415f33fea34c70ddc1ce4516e1a02f2df031c3cdf4c972f1be3",
		"target_manifest_digest": "8e8826f90eee8ea7c4ce4baeaa0c6b3ea03120663fd48de506c26e9ec20793b7",
	}
	for key, expected := range expectedDigests {
		if metadata[key] != expected {
			t.Fatalf("%s=%v want=%s", key, metadata[key], expected)
		}
	}
	if digest := sha256Bytes(rendered); digest != "767a0a63ca2f99dcdfbb393a2a70d7054baff41a4e7ab16b44a7b476543807b7" {
		t.Fatalf("rendered digest=%s", digest)
	}
	if err := os.WriteFile(filepath.Join(directory, "specs", "diff.md"), rendered, 0o600); err != nil {
		t.Fatal(err)
	}
	code, stdout, stderr := runCLI(t, "model", "validate", "--repo", repo, "--change", "C001")
	if code != 0 || stderr != "" {
		t.Fatalf("code=%d stderr=%q", code, stderr)
	}
	var result map[string]any
	if err := json.Unmarshal([]byte(stdout), &result); err != nil {
		t.Fatal(err)
	}
	if result["valid"] != true || result["spec_contract"] != float64(1) {
		t.Fatalf("result=%#v", result)
	}
	for _, key := range []string{"spec_base_digest", "spec_target_digest", "spec_manifest_digest", "spec_diff_digest"} {
		if result[key] == "" {
			t.Fatalf("missing %s: %#v", key, result)
		}
	}
}
