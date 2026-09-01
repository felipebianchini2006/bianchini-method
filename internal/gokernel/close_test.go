package gokernel

import (
	"errors"
	"os"
	"path/filepath"
	"testing"
)

func TestCycleCloseFrozenRepositoryError(t *testing.T) {
	repo := t.TempDir()
	code, stdout, stderr := runCLI(t, "cycle-close", "--repo", repo, "--change", "fixture")
	if code != 3 || stdout != "" || stderr != "DIRTY_WORKSPACE: o diretório não é uma raiz Git\n" {
		t.Fatalf("code=%d stdout=%q stderr=%q", code, stdout, stderr)
	}
}

func TestCrashRecoverableCloseContinuesFromPromotedCurrent(t *testing.T) {
	root := t.TempDir()
	current := filepath.Join(root, ".bianchini", "current")
	change := filepath.Join(root, ".bianchini", "changes", "C001-recovery")
	for _, directory := range []string{
		filepath.Join(current, "specs"), filepath.Join(change, "specs", "expected"),
		filepath.Join(root, ".bianchini", "archive"), filepath.Join(root, ".bianchini", ".runtime"),
	} {
		if err := os.MkdirAll(directory, 0o755); err != nil {
			t.Fatal(err)
		}
	}
	write := func(path, value string) {
		t.Helper()
		if err := os.WriteFile(path, []byte(value), 0o600); err != nil {
			t.Fatal(err)
		}
	}
	write(filepath.Join(current, "ARCHITECTURE.md"), "old architecture\n")
	write(filepath.Join(current, "SYSTEM_MODEL.md"), "old model\n")
	write(filepath.Join(current, "specs", "MANIFEST.json"), "{}\n")
	write(filepath.Join(change, "ARCHITECTURE.md"), "new architecture\n")
	write(filepath.Join(change, "SYSTEM_MODEL.md"), "new model\n")
	write(filepath.Join(change, "specs", "expected", "system.md"), "new spec\n")
	write(filepath.Join(change, "specs", "MANIFEST.json"), "{\"schema_version\":1}\n")
	write(filepath.Join(root, ".bianchini", "STATE.md"), "old state\n")
	_, err := crashRecoverableClose(root, "C001-recovery", filepath.Join(change, "specs", "expected"), filepath.Join(change, "specs", "MANIFEST.json"), []byte("summary\n"), []byte("new state\n"), "CURRENT_PROMOTED")
	var crash closeCrash
	if !errors.As(err, &crash) || crash.phase != "CURRENT_PROMOTED" {
		t.Fatalf("err=%v", err)
	}
	if _, statErr := os.Stat(filepath.Join(root, ".bianchini", ".runtime", "cycle-close.json")); statErr != nil {
		t.Fatalf("journal ausente: %v", statErr)
	}
	journalPath := filepath.Join(root, ".bianchini", ".runtime", "cycle-close.json")
	journalBytes, readErr := os.ReadFile(journalPath)
	if readErr != nil {
		t.Fatal(readErr)
	}
	if err := os.WriteFile(journalPath, append(append([]byte(nil), journalBytes...), []byte("trailing-garbage")...), 0o600); err != nil {
		t.Fatal(err)
	}
	if _, err := recoverPendingClose(root); err == nil {
		t.Fatal("recovery aceitou journal JSON seguido de lixo")
	}
	if err := os.WriteFile(journalPath, journalBytes, 0o600); err != nil {
		t.Fatal(err)
	}
	result, err := recoverPendingClose(root)
	if err != nil {
		t.Fatal(err)
	}
	if result["status"] != "completed" || result["recovered"] != true {
		t.Fatalf("result=%#v", result)
	}
	if _, statErr := os.Stat(filepath.Join(root, ".bianchini", "archive", "C001-recovery", "SUMMARY.md")); statErr != nil {
		t.Fatalf("archive incompleto: %v", statErr)
	}
	if content, readErr := os.ReadFile(filepath.Join(current, "specs", "system.md")); readErr != nil || string(content) != "new spec\n" {
		t.Fatalf("spec promovida content=%q err=%v", content, readErr)
	}
	for _, path := range []string{
		filepath.Join(root, ".bianchini", ".runtime", "cycle-close.json"),
		filepath.Join(root, ".bianchini", ".runtime", "cycle-close-C001-recovery"),
	} {
		if _, statErr := os.Lstat(path); !os.IsNotExist(statErr) {
			t.Fatalf("staging residual: %s err=%v", path, statErr)
		}
	}
}

func TestCloseTreeDigestRejectsSymlink(t *testing.T) {
	root := t.TempDir()
	outside := filepath.Join(t.TempDir(), "outside.txt")
	if err := os.WriteFile(outside, []byte("outside"), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(outside, filepath.Join(root, "escape")); err != nil {
		t.Skipf("symlink indisponível: %v", err)
	}
	if _, err := closeTreeDigest(root); err == nil {
		t.Fatal("closeTreeDigest aceitou symlink")
	}
}
