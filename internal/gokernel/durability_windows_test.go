//go:build windows

package gokernel

import (
	"os"
	"path/filepath"
	"testing"
)

func TestWindowsDurableMoveFlags(t *testing.T) {
	if got := windowsMoveFlags(false); got != windowsMoveFileWriteThrough {
		t.Fatalf("move flags=%#x", got)
	}
	want := uint32(windowsMoveFileReplaceExisting | windowsMoveFileWriteThrough)
	if got := windowsMoveFlags(true); got != want {
		t.Fatalf("replace flags=%#x want=%#x", got, want)
	}
}

func TestWindowsDurableReplaceAndDirectoryMove(t *testing.T) {
	root := t.TempDir()
	fileTarget := filepath.Join(root, "target.txt")
	fileSource := filepath.Join(root, "source.txt")
	if err := os.WriteFile(fileTarget, []byte("old"), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(fileSource, []byte("new"), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := replacePath(fileSource, fileTarget); err != nil {
		t.Fatal(err)
	}
	if content, err := os.ReadFile(fileTarget); err != nil || string(content) != "new" {
		t.Fatalf("content=%q err=%v", content, err)
	}

	left := filepath.Join(root, "left")
	right := filepath.Join(root, "right")
	if err := os.MkdirAll(filepath.Join(left, "source"), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.Mkdir(right, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := windowsMovePath(filepath.Join(left, "source"), filepath.Join(right, "target"), false); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(filepath.Join(right, "target")); err != nil {
		t.Fatal(err)
	}
}

func TestWindowsDurableRemovalUsesRecoverableTombstone(t *testing.T) {
	root := t.TempDir()
	path := filepath.Join(root, "journal.json")
	sentinel := filepath.Join(root, ".journal.json.bianchini-delete")
	if err := os.WriteFile(sentinel, []byte("third-party"), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, []byte("journal"), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := removeFileDurably(path); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Lstat(path); !os.IsNotExist(err) {
		t.Fatalf("origem ainda existe: %v", err)
	}
	if content, err := os.ReadFile(sentinel); err != nil || string(content) != "third-party" {
		t.Fatalf("colisão de terceiro alterada: content=%q err=%v", content, err)
	}
	if err := removeFileDurably(path); err != nil {
		t.Fatalf("retry de remoção falhou: %v", err)
	}
	if content, err := os.ReadFile(sentinel); err != nil || string(content) != "third-party" {
		t.Fatalf("retry alterou colisão de terceiro: content=%q err=%v", content, err)
	}
}
