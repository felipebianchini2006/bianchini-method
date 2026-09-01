package gokernel

import (
	"os"
	"os/exec"
	"path/filepath"
	"testing"
)

func TestMigrationCheckAndApplyPreserveKnownLegacyBytes(t *testing.T) {
	root := t.TempDir()
	runGitMigration(t, root, "init")
	runGitMigration(t, root, "config", "user.name", "BM Test")
	runGitMigration(t, root, "config", "user.email", "test@example.invalid")
	files := map[string][]byte{
		"keep.txt":                               []byte("preservar\n"),
		".planning/sentinel.txt":                 []byte("foreign\n"),
		"docs/living/PROJECT_STATE.md":           []byte("{\"planning_status\":\"idle\"}\n"),
		"docs/bianchini/current/specs/system.md": []byte("# Sistema\n"),
		"artifacts/bianchini/C001/result.json":   []byte("{}\n"),
		"docs/design/foreign/notes.md":           []byte("foreign design\n"),
		"docs/design/C001/DESIGN_MANIFEST.json":  []byte("{\"schema_version\":1,\"status\":\"approved\"}\n"),
		"docs/design/C001/prototype.html":        []byte("<main>approved</main>\n"),
	}
	for relative, content := range files {
		path := filepath.Join(root, filepath.FromSlash(relative))
		if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(path, content, 0o644); err != nil {
			t.Fatal(err)
		}
	}
	runGitMigration(t, root, "add", ".")
	runGitMigration(t, root, "commit", "-m", "legacy")

	checked, err := migrationCheck(root)
	if err != nil {
		t.Fatal(err)
	}
	if checked["eligible"] != true || len(stateArray(checked["entries"])) != 5 {
		t.Fatalf("resultado de check inesperado: %#v", checked)
	}

	applied, err := migrationApply(root)
	if err != nil {
		t.Fatal(err)
	}
	if applied["status"] != "migrated" {
		t.Fatalf("resultado de apply inesperado: %#v", applied)
	}
	for relative, expected := range map[string][]byte{
		"keep.txt":                           files["keep.txt"],
		".planning/sentinel.txt":             files[".planning/sentinel.txt"],
		"docs/design/foreign/notes.md":       files["docs/design/foreign/notes.md"],
		".bianchini/current/specs/system.md": files["docs/bianchini/current/specs/system.md"],
	} {
		content, readErr := os.ReadFile(filepath.Join(root, filepath.FromSlash(relative)))
		if readErr != nil || string(content) != string(expected) {
			t.Fatalf("bytes não preservados em %s: %v %q", relative, readErr, content)
		}
	}
	if _, err := os.Stat(filepath.Join(root, "docs", "living", "PROJECT_STATE.md")); !os.IsNotExist(err) {
		t.Fatalf("fonte antiga não removida: %v", err)
	}
	if _, err := os.Stat(stateString(applied["manifest"])); err != nil {
		t.Fatalf("manifesto ausente: %v", err)
	}
	if _, err := os.Stat(stateString(applied["state"])); err != nil {
		t.Fatalf("estado ausente: %v", err)
	}
}

func TestMigrationRejectsSymlinkBeforeMutation(t *testing.T) {
	root := t.TempDir()
	runGitMigration(t, root, "init")
	if err := os.MkdirAll(filepath.Join(root, "docs", "bianchini"), 0o755); err != nil {
		t.Fatal(err)
	}
	outside := filepath.Join(t.TempDir(), "outside.txt")
	if err := os.WriteFile(outside, []byte("secret\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(outside, filepath.Join(root, "docs", "bianchini", "unsafe")); err != nil {
		t.Fatal(err)
	}
	_, err := migrationCheck(root)
	if err == nil || err.Error() == "" {
		t.Fatal("symlink deveria bloquear migração")
	}
	if _, statErr := os.Stat(filepath.Join(root, ".bianchini")); !os.IsNotExist(statErr) {
		t.Fatalf("migração bloqueada alterou workspace: %v", statErr)
	}
}

func runGitMigration(t *testing.T, root string, args ...string) {
	t.Helper()
	command := exec.Command("git", args...)
	command.Dir = root
	if output, err := command.CombinedOutput(); err != nil {
		t.Fatalf("git %v: %v\n%s", args, err, output)
	}
}
