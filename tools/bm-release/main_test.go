package main

import (
	"archive/tar"
	"bytes"
	"compress/gzip"
	"io"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestReleaseArchiveIsDeterministicAndContainsNativeCLI(t *testing.T) {
	root, err := filepath.Abs(filepath.Join("..", ".."))
	if err != nil {
		t.Fatal(err)
	}
	temporary := t.TempDir()
	binary := filepath.Join(temporary, "bm")
	if err := os.WriteFile(binary, []byte("native-binary\n"), 0o755); err != nil {
		t.Fatal(err)
	}
	epoch := time.Unix(1_700_000_000, 0).UTC()
	first := filepath.Join(temporary, "first.tar.gz")
	second := filepath.Join(temporary, "second.tar.gz")
	for _, output := range []string{first, second} {
		if err := createReleaseArchive(root, output, "bianchini-method_0.4.6_darwin-arm64", binary, "bm", epoch); err != nil {
			t.Fatal(err)
		}
	}
	firstBytes, err := os.ReadFile(first)
	if err != nil {
		t.Fatal(err)
	}
	secondBytes, err := os.ReadFile(second)
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(firstBytes, secondBytes) {
		t.Fatal("mesmos inputs produziram archives diferentes")
	}

	entries := readReleaseArchive(t, first)
	prefix := "bianchini-method_0.4.6_darwin-arm64/"
	for _, required := range []string{
		prefix + "skills/_shared/VERSION",
		prefix + "skills/_shared/bin/bm",
		prefix + "THIRD_PARTY_NOTICES.md",
	} {
		entry, ok := entries[required]
		if !ok {
			t.Fatalf("entrada obrigatória ausente: %s", required)
		}
		if entry.modTime != epoch.Unix() || entry.uid != 0 || entry.gid != 0 {
			t.Fatalf("metadata não reproduzível em %s: %#v", required, entry)
		}
	}
	if string(entries[prefix+"skills/_shared/bin/bm"].content) != "native-binary\n" {
		t.Fatal("binário empacotado divergiu")
	}
	if entries[prefix+"skills/_shared/bin/bm"].mode&0o111 == 0 {
		t.Fatal("binário Unix perdeu modo executável")
	}
	for name := range entries {
		if strings.Contains(name, ".planning") || strings.Contains(name, "__pycache__") {
			t.Fatalf("entrada não rastreada vazou para release: %s", name)
		}
	}
}

func TestReleaseTargetsAreClosedAndDeduplicated(t *testing.T) {
	targets, err := parseReleaseTargets("darwin-arm64,linux-amd64,darwin-arm64")
	if err != nil {
		t.Fatal(err)
	}
	if strings.Join(targets, ",") != "darwin-arm64,linux-amd64" {
		t.Fatalf("targets=%v", targets)
	}
	if _, err := parseReleaseTargets("freebsd-amd64"); err == nil {
		t.Fatal("target não distribuído foi aceito")
	}
}

type archivedReleaseEntry struct {
	content []byte
	mode    int64
	modTime int64
	uid     int
	gid     int
}

func readReleaseArchive(t *testing.T, path string) map[string]archivedReleaseEntry {
	t.Helper()
	file, err := os.Open(path)
	if err != nil {
		t.Fatal(err)
	}
	defer file.Close()
	compressed, err := gzip.NewReader(file)
	if err != nil {
		t.Fatal(err)
	}
	defer compressed.Close()
	reader := tar.NewReader(compressed)
	entries := map[string]archivedReleaseEntry{}
	for {
		header, err := reader.Next()
		if err == io.EOF {
			break
		}
		if err != nil {
			t.Fatal(err)
		}
		if _, duplicate := entries[header.Name]; duplicate {
			t.Fatalf("entrada duplicada: %s", header.Name)
		}
		content, err := io.ReadAll(reader)
		if err != nil {
			t.Fatal(err)
		}
		entries[header.Name] = archivedReleaseEntry{
			content: content, mode: header.Mode, modTime: header.ModTime.Unix(), uid: header.Uid, gid: header.Gid,
		}
	}
	return entries
}
