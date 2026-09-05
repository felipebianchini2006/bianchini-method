package main

import (
	"archive/tar"
	"bytes"
	"compress/gzip"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
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
		if err := createReleaseArchive(root, output, "bianchini-method_0.6.0_darwin-arm64", binary, "bm", epoch); err != nil {
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
	prefix := "bianchini-method_0.6.0_darwin-arm64/"
	for _, required := range []string{
		prefix + "skills/_shared/VERSION",
		prefix + "skills/_shared/bin/bm",
		prefix + "skills/_shared/LICENSE",
		prefix + "skills/_shared/THIRD_PARTY_NOTICES.md",
		prefix + "LICENSE",
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

func TestReleaseVersionMustMatchCompiledKernel(t *testing.T) {
	if err := validateReleaseVersionContract("0.6.0", "0.6.0", "0.6.0"); err != nil {
		t.Fatal(err)
	}
	for _, test := range []struct {
		name       string
		packaged   string
		requested  string
		kernel     string
		wantDetail string
	}{
		{"package diverges", "0.4.9", "0.4.9", "0.6.0", "kernel version 0.6.0"},
		{"requested diverges", "0.6.0", "0.4.9", "0.6.0", "release 0.4.9"},
	} {
		t.Run(test.name, func(t *testing.T) {
			err := validateReleaseVersionContract(test.packaged, test.requested, test.kernel)
			if err == nil || !strings.Contains(err.Error(), test.wantDetail) {
				t.Fatalf("err=%v", err)
			}
		})
	}
}

func TestReleaseCommitMustResolveToCurrentHead(t *testing.T) {
	root, err := filepath.Abs(filepath.Join("..", ".."))
	if err != nil {
		t.Fatal(err)
	}
	if _, err := resolveReleaseCommit(root, "deadbeef"); err == nil || !strings.Contains(err.Error(), "commit de release inválido") {
		t.Fatalf("SHA inexistente foi aceito: %v", err)
	}
	head, err := gitOutput(root, "rev-parse", "HEAD")
	if err != nil {
		t.Fatal(err)
	}
	resolved, err := resolveReleaseCommit(root, head[:12])
	if err != nil {
		t.Fatal(err)
	}
	if resolved != head {
		t.Fatalf("resolved=%s, esperado %s", resolved, head)
	}
}

func TestReleaseBuilderMustBeClean(t *testing.T) {
	root := t.TempDir()
	builder := filepath.Join(root, "tools", "bm-release", "main.go")
	if err := os.MkdirAll(filepath.Dir(builder), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(builder, []byte("package main\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	for _, arguments := range [][]string{
		{"init", "-b", "main"},
		{"config", "user.name", "BM Release Test"},
		{"config", "user.email", "release@example.invalid"},
		{"add", "tools/bm-release/main.go"},
		{"commit", "-m", "initial builder"},
	} {
		command := exec.Command("git", arguments...)
		command.Dir = root
		if output, err := command.CombinedOutput(); err != nil {
			t.Fatalf("git %v: %v\n%s", arguments, err, output)
		}
	}
	if err := requireCleanReleaseInputs(root); err != nil {
		t.Fatalf("builder limpo foi rejeitado: %v", err)
	}
	if err := os.WriteFile(builder, []byte("package main\n// dirty\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	err := requireCleanReleaseInputs(root)
	if err == nil || !strings.Contains(err.Error(), "tools/bm-release/main.go") {
		t.Fatalf("builder alterado não foi rejeitado: %v", err)
	}
}

func TestReleaseEntrypointCannotBeOverridden(t *testing.T) {
	if _, err := parseReleaseOptions([]string{"--entrypoint", "./tools/bm-release"}); err == nil {
		t.Fatal("entrypoint arbitrário foi aceito")
	}
}

func TestBuiltReleaseBinaryIdentityIsChecked(t *testing.T) {
	root, err := filepath.Abs(filepath.Join("..", ".."))
	if err != nil {
		t.Fatal(err)
	}
	binary := filepath.Join(t.TempDir(), "bm")
	commit := strings.Repeat("a", 40)
	ldflags := "-s -w -buildid= -X github.com/felipebianchini2006/bianchini-method/internal/gokernel.BuildCommit=" + commit
	command := exec.Command("go", "build", "-trimpath", "-ldflags", ldflags, "-o", binary, "./cmd/bm")
	command.Dir = root
	if output, err := command.CombinedOutput(); err != nil {
		t.Fatalf("build do CLI: %v\n%s", err, output)
	}
	target := runtime.GOOS + "-" + runtime.GOARCH
	if err := validateBuiltReleaseBinary(binary, target, "1.0.0", commit); err != nil {
		t.Fatalf("CLI oficial foi rejeitado: %v", err)
	}
	if err := validateBuiltReleaseBinary(binary, target, "1.0.0", strings.Repeat("b", 40)); err == nil {
		t.Fatal("build_commit divergente foi aceito")
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
