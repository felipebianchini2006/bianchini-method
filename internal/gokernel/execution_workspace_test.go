package gokernel

import (
	"encoding/json"
	"errors"
	"os"
	"os/exec"
	"path/filepath"
	"reflect"
	"strings"
	"testing"
)

func executionWorkspaceGit(t *testing.T, repo string, args ...string) string {
	t.Helper()
	command := exec.Command("git", args...)
	command.Dir = repo
	command.Env = append(os.Environ(),
		"GIT_AUTHOR_DATE=2000-01-01T00:00:00Z",
		"GIT_COMMITTER_DATE=2000-01-01T00:00:00Z",
	)
	output, err := command.CombinedOutput()
	if err != nil {
		t.Fatalf("git %v: %v\n%s", args, err, output)
	}
	return strings.TrimSpace(string(output))
}

func executionWorkspacePlanFixture(dependsOn, consumes []string) map[string]any {
	return map[string]any{
		"id": "P01", "schema_version": 1, "model_delta": map[string]any{},
		"depends_on": dependsOn, "consumes": consumes, "provides": []string{},
		"acceptance":    []string{"workspace criado"},
		"verifications": []string{"go test ./..."},
	}
}

func executionWorkspaceRepository(t *testing.T, plan map[string]any) (string, string) {
	t.Helper()
	repo := filepath.Join(t.TempDir(), "repo")
	if err := os.MkdirAll(repo, 0o755); err != nil {
		t.Fatal(err)
	}
	repo, err := filepath.EvalSymlinks(repo)
	if err != nil {
		t.Fatal(err)
	}
	executionWorkspaceGit(t, repo, "init", "-q", "-b", "main")
	executionWorkspaceGit(t, repo, "config", "user.name", "BM Fixture")
	executionWorkspaceGit(t, repo, "config", "user.email", "fixture@example.invalid")
	if _, err := initializeModelWorkspace(repo); err != nil {
		t.Fatal(err)
	}
	created, err := createModelChange(repo, "health journey")
	if err != nil {
		t.Fatal(err)
	}
	change := stateString(created["change"])
	directory := filepath.Join(repo, ".bianchini", "changes", change)
	planDocument, err := frontmatterDocument(plan, "# P01", false)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(directory, "plans", "P01.md"), planDocument, 0o644); err != nil {
		t.Fatal(err)
	}
	workspace, _, plans, err := loadRoadmapPackage(repo, change)
	if err != nil {
		t.Fatal(err)
	}
	current, err := loadProjectModel(workspace.currentMod)
	if err != nil {
		t.Fatal(err)
	}
	expected, err := loadProjectModel(filepath.Join(directory, "SYSTEM_MODEL.md"))
	if err != nil {
		t.Fatal(err)
	}
	manifest, err := coherenceArtifactManifest(workspace, directory)
	if err != nil {
		t.Fatal(err)
	}
	findings := []any{}
	semantic := map[string]any{"available": true, "findings": []any{}, "sources": []any{"fixture"}}
	coherence := map[string]any{
		"schema_version": 1, "planning_contract": 2, "status": "approved",
		"change": change, "findings": findings, "semantic": semantic,
		"artifact_manifest":   manifest,
		"review_input_digest": coherenceReviewDigest(2, manifest, nil),
		"digest":              coherencePackageDigest(current, expected, plans, findings, semantic, 2, manifest, nil),
		"stale_plans":         []any{},
	}
	coherenceDocument, err := frontmatterDocument(coherence, "# Coerência\n\nStatus: approved.", false)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(directory, "COHERENCE.md"), coherenceDocument, 0o644); err != nil {
		t.Fatal(err)
	}
	state, err := workspace.readState()
	if err != nil {
		t.Fatal(err)
	}
	state["status"], state["digest"] = "approved", coherence["digest"]
	stateObject(state["active_work"])["status"] = "approved"
	if err := workspace.writeState(state, "# Estado atual"); err != nil {
		t.Fatal(err)
	}
	executionWorkspaceGit(t, repo, "add", ".")
	executionWorkspaceGit(t, repo, "commit", "-q", "-m", "approved package")
	return repo, change
}

func executionWorkspaceResult(t *testing.T, value any) map[string]any {
	t.Helper()
	result, ok := value.(map[string]any)
	if !ok {
		t.Fatalf("resultado inválido: %#v", value)
	}
	return result
}

func TestExecutionWorkspaceCreateLocateResumeAndCheck(t *testing.T) {
	repo, change := executionWorkspaceRepository(t, executionWorkspacePlanFixture(nil, nil))
	target := filepath.Join(filepath.Dir(repo), "execution-worktree")
	createdValue, err := runExecutionWorkspace([]string{
		"create", "--repo", repo, "--change", change, "--plan", "P01", "--target", target,
	})
	if err != nil {
		t.Fatal(err)
	}
	created := executionWorkspaceResult(t, createdValue)
	head := executionWorkspaceGit(t, repo, "rev-parse", "HEAD")
	wantCreated := map[string]any{
		"workspace": target, "branch": "bm/c001-p01", "change": change,
		"plan": "P01", "base_commit": head,
	}
	if !reflect.DeepEqual(created, wantCreated) {
		t.Fatalf("create=%#v want=%#v", created, wantCreated)
	}

	locatedValue, err := runExecutionWorkspace([]string{
		"locate", "--repo", repo, "--change", change, "--plan", "P01",
	})
	if err != nil {
		t.Fatal(err)
	}
	located := executionWorkspaceResult(t, locatedValue)
	if located["workspace"] != target || located["branch"] != "bm/c001-p01" {
		t.Fatalf("locate=%#v", located)
	}
	if _, exists := located["metadata"]; exists {
		t.Fatalf("locate não deve carregar metadata: %#v", located)
	}

	resumedValue, err := runExecutionWorkspace([]string{
		"resume", "--repo", repo, "--change", change, "--plan", "P01",
	})
	if err != nil {
		t.Fatal(err)
	}
	resumed := executionWorkspaceResult(t, resumedValue)
	metadata := stateObject(resumed["metadata"])
	if stateInt(metadata["schema_version"]) != 1 || stateString(metadata["source_repo"]) != repo ||
		stateString(metadata["change"]) != change || stateString(metadata["plan"]) != "P01" ||
		stateString(metadata["branch"]) != "bm/c001-p01" || stateString(metadata["base_commit"]) != head ||
		stateString(metadata["coherence_digest"]) == "" || stateString(metadata["created_at"]) == "" {
		t.Fatalf("metadata=%#v", metadata)
	}

	checkedValue, err := runExecutionWorkspace([]string{"check", "--repo", target})
	if err != nil {
		t.Fatal(err)
	}
	checked := executionWorkspaceResult(t, checkedValue)
	if checked["valid"] != true || checked["branch"] != "bm/c001-p01" || checked["workspace"] != target || !reflect.DeepEqual(checked["metadata"], metadata) {
		t.Fatalf("check=%#v", checked)
	}
	state, err := newMethodWorkspace(target).readState()
	if err != nil {
		t.Fatal(err)
	}
	if state["status"] != "executing" || state["current_unit"] != "P01" || stateString(stateObject(state["active_work"])["id"]) != change {
		t.Fatalf("target state=%#v", state)
	}
}

func TestExecutionWorkspaceFrozenMissingGitErrors(t *testing.T) {
	tests := [][]string{
		{"create", "--change", "fixture", "--plan", "P01"},
		{"check"},
		{"locate", "--change", "fixture", "--plan", "P01"},
		{"resume", "--change", "fixture", "--plan", "P01"},
	}
	for _, arguments := range tests {
		t.Run(arguments[0], func(t *testing.T) {
			repo := t.TempDir()
			args := append(append([]string(nil), arguments...), "--repo", repo)
			_, err := runExecutionWorkspace(args)
			if err == nil || err.Error() != "DIRTY_WORKSPACE: o diretório não é uma raiz Git" {
				t.Fatalf("err=%v", err)
			}
		})
	}
}

func TestExecutionWorkspaceCreateGates(t *testing.T) {
	tests := []struct {
		name      string
		plan      map[string]any
		prepare   func(*testing.T, string, string)
		wantError string
	}{
		{
			name: "dirty repository", plan: executionWorkspacePlanFixture(nil, nil),
			prepare: func(t *testing.T, repo, _ string) {
				if err := os.WriteFile(filepath.Join(repo, "dirty.txt"), []byte("dirty\n"), 0o644); err != nil {
					t.Fatal(err)
				}
			},
			wantError: "DIRTY_WORKSPACE: workspace de execução exige Git limpo",
		},
		{
			name: "missing dependency", plan: executionWorkspacePlanFixture([]string{"P00"}, nil),
			wantError: "MISSING_PROVIDER: dependências ainda não concluídas: P00",
		},
		{
			name: "missing consumed contract", plan: executionWorkspacePlanFixture(nil, []string{"session"}),
			wantError: "MISSING_PROVIDER: contratos consumidos ainda ausentes: session",
		},
		{
			name: "stale plan", plan: executionWorkspacePlanFixture(nil, nil),
			prepare: func(t *testing.T, repo, change string) {
				path := filepath.Join(repo, ".bianchini", "changes", change, "COHERENCE.md")
				coherence, err := readStructuredFrontmatter(path)
				if err != nil {
					t.Fatal(err)
				}
				coherence["status"], coherence["stale_plans"] = "approved_with_stale", []any{"P01"}
				document, err := frontmatterDocument(coherence, "# Coerência", false)
				if err != nil {
					t.Fatal(err)
				}
				if err := os.WriteFile(path, document, 0o644); err != nil {
					t.Fatal(err)
				}
				executionWorkspaceGit(t, repo, "add", filepath.ToSlash(filepath.Join(".bianchini", "changes", change, "COHERENCE.md")))
				executionWorkspaceGit(t, repo, "commit", "-q", "-m", "mark plan stale")
			},
			wantError: "IMPACT_STALE: P01 está stale",
		},
		{
			name: "completed plan", plan: executionWorkspacePlanFixture(nil, nil),
			prepare: func(t *testing.T, repo, change string) {
				result := map[string]any{"schema_version": 1, "change": change, "plan": "P01", "status": "completed", "actual_delta": map[string]any{}}
				document, err := frontmatterDocument(result, "# Resultado P01", false)
				if err != nil {
					t.Fatal(err)
				}
				path := filepath.Join(repo, ".bianchini", "changes", change, "results", "P01.md")
				if err := os.WriteFile(path, document, 0o644); err != nil {
					t.Fatal(err)
				}
				executionWorkspaceGit(t, repo, "add", filepath.ToSlash(filepath.Join(".bianchini", "changes", change, "results", "P01.md")))
				executionWorkspaceGit(t, repo, "commit", "-q", "-m", "complete plan")
			},
			wantError: "COHERENCE_ERROR: P01 já foi concluído",
		},
		{
			name: "approved package drift", plan: executionWorkspacePlanFixture(nil, nil),
			prepare: func(t *testing.T, repo, change string) {
				path := filepath.Join(repo, ".bianchini", "changes", change, "RESEARCH.md")
				if err := os.WriteFile(path, []byte("# drift\n"), 0o644); err != nil {
					t.Fatal(err)
				}
				executionWorkspaceGit(t, repo, "update-index", "--assume-unchanged", filepath.ToSlash(filepath.Join(".bianchini", "changes", change, "RESEARCH.md")))
			},
			wantError: "STALE_EVIDENCE: pacote aprovado mudou depois do checkpoint",
		},
		{
			name: "package differs from head", plan: executionWorkspacePlanFixture(nil, nil),
			prepare: func(t *testing.T, repo, change string) {
				path := filepath.Join(repo, ".bianchini", "changes", change, "COHERENCE.md")
				content, err := os.ReadFile(path)
				if err != nil {
					t.Fatal(err)
				}
				if err := os.WriteFile(path, append(content, []byte("\n<!-- drift -->\n")...), 0o644); err != nil {
					t.Fatal(err)
				}
				executionWorkspaceGit(t, repo, "update-index", "--assume-unchanged", filepath.ToSlash(filepath.Join(".bianchini", "changes", change, "COHERENCE.md")))
			},
			wantError: "COHERENCE_ERROR: pacote diverge do HEAD: .bianchini/changes/C001-health-journey/COHERENCE.md",
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			repo, change := executionWorkspaceRepository(t, test.plan)
			if test.prepare != nil {
				test.prepare(t, repo, change)
			}
			target := filepath.Join(filepath.Dir(repo), "execution-worktree")
			_, err := runExecutionWorkspace([]string{"create", "--repo", repo, "--change", change, "--plan", "P01", "--target", target})
			if err == nil || err.Error() != test.wantError {
				t.Fatalf("err=%v want=%q", err, test.wantError)
			}
		})
	}
}

func TestExecutionWorkspaceIdentityValidation(t *testing.T) {
	tests := []struct {
		change, plan, want string
	}{
		{"change", "P01", "MODEL_MISMATCH: change exige C seguido de três dígitos"},
		{"C001-health", "plan", "MODEL_MISMATCH: plan exige P seguido de ao menos dois dígitos"},
	}
	for _, test := range tests {
		_, _, err := executionWorkspaceIdentity(test.change, test.plan)
		if err == nil || err.Error() != test.want {
			t.Fatalf("change=%q plan=%q err=%v want=%q", test.change, test.plan, err, test.want)
		}
	}
}

func TestExecutionWorkspaceRejectsNestedDestination(t *testing.T) {
	repo, change := executionWorkspaceRepository(t, executionWorkspacePlanFixture(nil, nil))
	_, err := runExecutionWorkspace([]string{
		"create", "--repo", repo, "--change", change, "--plan", "P01", "--target", filepath.Join(repo, "nested"),
	})
	want := "DIRTY_WORKSPACE: destino do worktree deve ficar fora do repo"
	if err == nil || err.Error() != want {
		t.Fatalf("err=%v want=%q", err, want)
	}
}

func TestExecutionWorkspaceRejectsExistingTargetAndBranch(t *testing.T) {
	t.Run("target", func(t *testing.T) {
		repo, change := executionWorkspaceRepository(t, executionWorkspacePlanFixture(nil, nil))
		target := filepath.Join(filepath.Dir(repo), "execution-worktree")
		if err := os.MkdirAll(target, 0o755); err != nil {
			t.Fatal(err)
		}
		_, err := runExecutionWorkspace([]string{"create", "--repo", repo, "--change", change, "--plan", "P01", "--target", target})
		want := "DIRTY_WORKSPACE: destino já existe: " + target
		if err == nil || err.Error() != want {
			t.Fatalf("err=%v want=%q", err, want)
		}
	})
	t.Run("branch", func(t *testing.T) {
		repo, change := executionWorkspaceRepository(t, executionWorkspacePlanFixture(nil, nil))
		executionWorkspaceGit(t, repo, "branch", "bm/c001-p01")
		_, err := runExecutionWorkspace([]string{"create", "--repo", repo, "--change", change, "--plan", "P01", "--target", filepath.Join(filepath.Dir(repo), "execution-worktree")})
		want := "DIRTY_WORKSPACE: branch já existe: bm/c001-p01"
		if err == nil || err.Error() != want {
			t.Fatalf("err=%v want=%q", err, want)
		}
	})
}

func TestExecutionWorkspaceLocateAndCheckFailClosed(t *testing.T) {
	repo, change := executionWorkspaceRepository(t, executionWorkspacePlanFixture(nil, nil))
	if _, err := runExecutionWorkspace([]string{"locate", "--repo", repo, "--change", change, "--plan", "P01"}); err == nil || err.Error() != "DIRTY_WORKSPACE: workspace não localizado para c001-p01" {
		t.Fatalf("locate err=%v", err)
	}
	if _, err := runExecutionWorkspace([]string{"check", "--repo", repo}); err == nil || err.Error() != "DIRTY_WORKSPACE: branch de execução 0.4 inválida" {
		t.Fatalf("check err=%v", err)
	}
}

func TestExecutionWorkspaceRollbackRemovesWorktreeAndBranch(t *testing.T) {
	repo, change := executionWorkspaceRepository(t, executionWorkspacePlanFixture(nil, nil))
	target := filepath.Join(filepath.Dir(repo), "execution-worktree")
	dependencies := defaultExecutionWorkspaceDependencies()
	dependencies.persist = func(methodWorkspace, string, map[string]any, string) error {
		return errors.New("injected persistence failure")
	}
	_, err := runExecutionWorkspaceWithDependencies([]string{
		"create", "--repo", repo, "--change", change, "--plan", "P01", "--target", target,
	}, dependencies)
	if err == nil || err.Error() != "injected persistence failure" {
		t.Fatalf("err=%v", err)
	}
	if _, statErr := os.Lstat(target); !os.IsNotExist(statErr) {
		t.Fatalf("target deveria ser removido: %v", statErr)
	}
	if branches := executionWorkspaceGit(t, repo, "for-each-ref", "--format=%(refname:short)", "refs/heads"); strings.Contains(branches, "bm/c001-p01") {
		t.Fatalf("branch residual: %s", branches)
	}
}

func TestExecutionWorkspaceResumeAndCheckRejectUnsafeMetadata(t *testing.T) {
	repo, change := executionWorkspaceRepository(t, executionWorkspacePlanFixture(nil, nil))
	target := filepath.Join(filepath.Dir(repo), "execution-worktree")
	if _, err := runExecutionWorkspace([]string{"create", "--repo", repo, "--change", change, "--plan", "P01", "--target", target}); err != nil {
		t.Fatal(err)
	}
	metadataPath := filepath.Join(target, ".bianchini", ".runtime", "workspace-c001-p01.json")
	if err := os.Remove(metadataPath); err != nil {
		t.Fatal(err)
	}
	outside := filepath.Join(t.TempDir(), "metadata.json")
	if err := os.WriteFile(outside, []byte(`{"schema_version":1}`), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(outside, metadataPath); err != nil {
		t.Fatal(err)
	}
	for _, args := range [][]string{
		{"resume", "--repo", repo, "--change", change, "--plan", "P01"},
		{"check", "--repo", target},
	} {
		_, err := runExecutionWorkspace(args)
		if err == nil || !strings.Contains(err.Error(), "DIRTY_WORKSPACE") {
			t.Fatalf("args=%v err=%v", args, err)
		}
	}
}

func TestExecutionWorkspaceMetadataIsJSON(t *testing.T) {
	repo, change := executionWorkspaceRepository(t, executionWorkspacePlanFixture(nil, nil))
	target := filepath.Join(filepath.Dir(repo), "execution-worktree")
	if _, err := runExecutionWorkspace([]string{"create", "--repo", repo, "--change", change, "--plan", "P01", "--target", target}); err != nil {
		t.Fatal(err)
	}
	content, err := os.ReadFile(filepath.Join(target, ".bianchini", ".runtime", "workspace-c001-p01.json"))
	if err != nil {
		t.Fatal(err)
	}
	var metadata map[string]any
	if err := json.Unmarshal(content, &metadata); err != nil {
		t.Fatal(err)
	}
	if stateInt(metadata["schema_version"]) != 1 {
		t.Fatalf("metadata=%#v", metadata)
	}
}
