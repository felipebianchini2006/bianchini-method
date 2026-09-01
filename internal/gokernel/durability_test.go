package gokernel

import (
	"errors"
	"os"
	"path/filepath"
	"testing"
)

func TestDurableMetadataTransitionsPropagateDirectorySyncFailure(t *testing.T) {
	want := errors.New("fsync directory failed")
	failSync := func(string) error { return want }

	t.Run("close atomic write", func(t *testing.T) {
		root := t.TempDir()
		if err := os.Mkdir(filepath.Join(root, ".bianchini"), 0o755); err != nil {
			t.Fatal(err)
		}
		path := filepath.Join(root, ".bianchini", "STATE.md")
		if err := closeAtomicWriteWithSync(path, []byte("state\n"), failSync); !errors.Is(err, want) {
			t.Fatalf("fsync não foi exigido após replace: %v", err)
		}
	})

	t.Run("close rename", func(t *testing.T) {
		root := t.TempDir()
		source := filepath.Join(root, "source")
		target := filepath.Join(root, "destination", "target")
		if err := os.Mkdir(source, 0o755); err != nil {
			t.Fatal(err)
		}
		if err := closeRenameWithSync(source, target, failSync); !errors.Is(err, want) {
			t.Fatalf("fsync não foi exigido após rename: %v", err)
		}
	})

	t.Run("update journal", func(t *testing.T) {
		root := t.TempDir()
		transaction := updateTransaction{SchemaVersion: 1, SkillsRoot: filepath.Join(root, "skills")}
		if err := writeUpdateJournalWithSync(transaction, failSync); !errors.Is(err, want) {
			t.Fatalf("journal não propagou falha de fsync do diretório: %v", err)
		}
	})
}

func TestDurableMetadataRetryRepeatsDirectorySyncAfterMutation(t *testing.T) {
	t.Run("atomic write with identical bytes", func(t *testing.T) {
		root := t.TempDir()
		if err := os.Mkdir(filepath.Join(root, ".bianchini"), 0o755); err != nil {
			t.Fatal(err)
		}
		path := filepath.Join(root, ".bianchini", "STATE.md")
		calls := 0
		syncOnce := func(string) error {
			calls++
			if calls == 1 {
				return errors.New("first sync failed")
			}
			return nil
		}
		if err := closeAtomicWriteWithSync(path, []byte("state\n"), syncOnce); err == nil {
			t.Fatal("primeiro fsync deveria falhar depois do rename")
		}
		if err := closeAtomicWriteWithSync(path, []byte("state\n"), syncOnce); err != nil {
			t.Fatalf("retry não repetiu fsync: %v", err)
		}
		if calls != 2 {
			t.Fatalf("fsync deveria ser repetido no retry; calls=%d", calls)
		}
	})

	t.Run("rename already applied", func(t *testing.T) {
		root := t.TempDir()
		source := filepath.Join(root, "transaction", "stage")
		target := filepath.Join(root, "current")
		if err := os.MkdirAll(source, 0o755); err != nil {
			t.Fatal(err)
		}
		calls := 0
		syncOnce := func(string) error {
			calls++
			if calls == 1 {
				return errors.New("first sync failed")
			}
			return nil
		}
		if err := closeRenameWithSync(source, target, syncOnce); err == nil {
			t.Fatal("primeiro fsync deveria falhar depois do rename")
		}
		if _, err := os.Stat(target); err != nil {
			t.Fatalf("rename deveria ter sido efetivado: %v", err)
		}
		if err := syncRenameDirectories(source, target, syncOnce); err != nil {
			t.Fatalf("retry não repetiu fsync dos parents: %v", err)
		}
		if calls < 2 {
			t.Fatalf("fsync deveria ser repetido no retry; calls=%d", calls)
		}
	})
}
