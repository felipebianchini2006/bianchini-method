package gokernel

import (
	"bytes"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestScopeSchemaTransition(t *testing.T) {
	repo := goGitRoot(t)
	if _, err := initializeModelWorkspace(repo); err != nil {
		t.Fatal(err)
	}
	created, err := createModelChange(repo, "scope transition")
	if err != nil {
		t.Fatal(err)
	}
	change := stateString(created["change"])
	path := filepath.Join(repo, ".bianchini", "changes", change, "SCOPE.md")
	// Historical document without a manifest must be diagnosed, never sealed.
	legacy, _ := frontmatterDocument(map[string]any{"schema_version": 1, "document": "bianchini-scope"}, "# Scope", false)
	if err := os.WriteFile(path, legacy, 0600); err != nil {
		t.Fatal(err)
	}
	if _, err := verifyScope(repo, change, ""); err == nil || !strings.Contains(err.Error(), "WORKSPACE_UPGRADE_REQUIRED") {
		t.Fatalf("legacy scope not diagnosed: %v", err)
	}
	after, _ := os.ReadFile(path)
	if string(after) != string(legacy) {
		t.Fatal("legacy scope rewritten")
	}
	inputs := t.TempDir()
	source, draft := filepath.Join(inputs, "scope.pdf"), filepath.Join(inputs, "draft.md")
	if err := os.WriteFile(source, scopePDF(), 0600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(draft, []byte(scopeDraft(false)), 0600); err != nil {
		t.Fatal(err)
	}
	code, _, stderr := runCLI(t, "scope", "seal", "--repo", repo, "--change", change, "--source", source, "--draft", draft, "--pages", "2", "--extraction", "native", "--page-manifest", scopeTestManifest(t, source, inputs))
	if code != 0 {
		t.Fatal(stderr)
	}
	metadata, err := readStructuredFrontmatter(path)
	if err != nil {
		t.Fatal(err)
	}
	if stateInt(metadata["schema_version"]) != 2 {
		t.Fatal("new scope did not use schema 2")
	}
	if _, err := verifyScope(repo, change, source); err != nil {
		t.Fatal(err)
	}
	// Construct a valid historical fixture. Production never re-signs old approvals.
	content, _ := os.ReadFile(path)
	body := string(scopeFrontmatter.FindSubmatch(content)[1])
	metadata["schema_version"] = 1
	delete(metadata, "scope_digest")
	metadata["scope_digest"] = scopeDigest(metadata, body)
	old, _ := scopeDocument(metadata, body)
	if err := os.WriteFile(path, old, 0600); err != nil {
		t.Fatal(err)
	}
	workspace := newMethodWorkspace(repo)
	state, err := workspace.readState()
	if err != nil {
		t.Fatal(err)
	}
	state["digest"] = metadata["scope_digest"]
	if err := workspace.writeState(state, "# Historical fixture"); err != nil {
		t.Fatal(err)
	}
	if _, err := verifyScope(repo, change, source); err != nil {
		t.Fatalf("1.1.0 scope rejected: %v", err)
	}
	after, _ = os.ReadFile(path)
	if !bytes.Equal(old, after) {
		t.Fatal("historical scope was rewritten")
	}
}
