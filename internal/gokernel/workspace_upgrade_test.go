package gokernel

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestLegacyWorkspaceReportsUpgradeBeforePlanning(t *testing.T) {
	repo := goGitRoot(t)
	workspace := newMethodWorkspace(repo)
	if err := workspace.initialize(); err != nil {
		t.Fatal(err)
	}
	state := workspace.initialState()
	state["method"] = "0.4"
	document, _ := frontmatterDocument(state, "# Historical state", false)
	path := filepath.Join(repo, ".bianchini", "STATE.md")
	if err := os.WriteFile(path, document, 0600); err != nil {
		t.Fatal(err)
	}
	code, _, stderr := runCLI(t, "roadmap", "sync", "--repo", repo, "--change", "C001")
	if code != 3 || !strings.Contains(stderr, "WORKSPACE_UPGRADE_REQUIRED") || !strings.Contains(stderr, "UPGRADING.md") {
		t.Fatalf("legacy-entry-regression: code=%d error=%s", code, stderr)
	}
	after, _ := os.ReadFile(path)
	if string(document) != string(after) {
		t.Fatal("historical state changed")
	}
}
