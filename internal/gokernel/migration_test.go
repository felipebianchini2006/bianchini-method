package gokernel

import (
	"errors"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
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

func TestMigrationRejectsSymlinkAncestorBeforeReadingLegacyTree(t *testing.T) {
	root := t.TempDir()
	runGitMigration(t, root, "init")
	runGitMigration(t, root, "config", "user.name", "BM Test")
	runGitMigration(t, root, "config", "user.email", "test@example.invalid")
	outside := t.TempDir()
	for relative, content := range map[string][]byte{
		"living/PROJECT_STATE.md":           []byte("{\"planning_status\":\"idle\"}\n"),
		"bianchini/current/specs/system.md": []byte("outside\n"),
	} {
		path := filepath.Join(outside, filepath.FromSlash(relative))
		if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(path, content, 0o640); err != nil {
			t.Fatal(err)
		}
	}
	if err := os.Symlink(outside, filepath.Join(root, "docs")); err != nil {
		t.Skipf("symlink indisponível: %v", err)
	}
	runGitMigration(t, root, "add", "docs")
	runGitMigration(t, root, "commit", "-m", "legacy symlink")

	_, err := migrationCheck(root)
	if err == nil || !strings.Contains(err.Error(), "symlink") {
		t.Fatalf("ancestral symlink deveria bloquear antes da leitura: %v", err)
	}
	if content, readErr := os.ReadFile(filepath.Join(outside, "bianchini", "current", "specs", "system.md")); readErr != nil || string(content) != "outside\n" {
		t.Fatalf("conteúdo externo alterado: %q err=%v", content, readErr)
	}
	if _, statErr := os.Lstat(filepath.Join(root, ".bianchini")); !os.IsNotExist(statErr) {
		t.Fatalf("migração bloqueada alterou workspace: %v", statErr)
	}
}

func TestMigrationIgnoresForeignPlanningNamespaceAtAnyDepth(t *testing.T) {
	root := t.TempDir()
	runGitMigration(t, root, "init")
	runGitMigration(t, root, "config", "user.name", "BM Test")
	runGitMigration(t, root, "config", "user.email", "test@example.invalid")
	legacy := filepath.Join(root, "docs", "bianchini", "result.json")
	foreign := filepath.Join(root, "docs", "bianchini", ".Planning", "sentinel.txt")
	for path, content := range map[string][]byte{legacy: []byte("{}\n"), foreign: []byte("foreign\n")} {
		if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(path, content, 0o640); err != nil {
			t.Fatal(err)
		}
	}
	runGitMigration(t, root, "add", ".")
	runGitMigration(t, root, "commit", "-m", "legacy")

	report, err := migrationCheck(root)
	if err != nil {
		t.Fatal(err)
	}
	for _, raw := range stateArray(report["entries"]) {
		entry := stateObject(raw)
		if strings.Contains(strings.ToLower(stateString(entry["source"])), "/.planning/") {
			t.Fatalf("namespace estrangeiro entrou no mapa: %#v", entry)
		}
	}
	if _, err := migrationApply(root); err != nil {
		t.Fatal(err)
	}
	if content, readErr := os.ReadFile(foreign); readErr != nil || string(content) != "foreign\n" {
		t.Fatalf("namespace estrangeiro foi alterado: %q err=%v", content, readErr)
	}
}

func TestMigrationRollbackRetainsOnlyRecoverableCopyWhenRestoreFails(t *testing.T) {
	root := t.TempDir()
	workspace := filepath.Join(root, ".bianchini")
	target := filepath.Join(workspace, "archive", "legacy.txt")
	if err := os.MkdirAll(filepath.Dir(target), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(target, []byte("preserve\n"), 0o640); err != nil {
		t.Fatal(err)
	}
	blockedParent := filepath.Join(root, "blocked")
	if err := os.WriteFile(blockedParent, []byte("not a directory\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	removed := []migrationCopyPair{{source: filepath.Join(blockedParent, "legacy.txt"), target: target}}

	err := rollbackMigration(workspace, removed)
	if err == nil || !strings.Contains(err.Error(), "rollback incompleto") {
		t.Fatalf("falha de restauração deveria ficar explícita: %v", err)
	}
	if content, readErr := os.ReadFile(target); readErr != nil || string(content) != "preserve\n" {
		t.Fatalf("única cópia recuperável foi apagada: %q err=%v", content, readErr)
	}
	if !errors.Is(err, errMigrationRollbackIncomplete) {
		t.Fatalf("erro não classifica rollback incompleto: %v", err)
	}
}

func TestCopyMigrationFilePreservesExactMode(t *testing.T) {
	root := t.TempDir()
	source := filepath.Join(root, "source")
	target := filepath.Join(root, "target")
	if err := os.WriteFile(source, []byte("mode\n"), 0o751); err != nil {
		t.Fatal(err)
	}
	if err := os.Chmod(source, 0o751); err != nil {
		t.Fatal(err)
	}
	if err := copyMigrationFile(source, target); err != nil {
		t.Fatal(err)
	}
	info, err := os.Stat(target)
	if err != nil {
		t.Fatal(err)
	}
	if got := info.Mode().Perm(); got != 0o751 {
		t.Fatalf("mode=%#o, esperado %#o", got, 0o751)
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
