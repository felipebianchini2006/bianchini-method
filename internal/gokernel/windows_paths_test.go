package gokernel

import (
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

func TestNativeWindowsAbsolutePathsRemainConfined(t *testing.T) {
	if runtime.GOOS != "windows" {
		t.Skip("exercitado pelo job Windows nativo")
	}
	root := t.TempDir()
	if err := os.Mkdir(filepath.Join(root, ".bianchini"), 0o755); err != nil {
		t.Fatal(err)
	}
	file := filepath.Join(root, ".bianchini", "STATE.md")
	if err := os.WriteFile(file, []byte("state"), 0o600); err != nil {
		t.Fatal(err)
	}
	resolvedRoot, err := contextRoot(root)
	if err != nil || resolvedRoot != filepath.Clean(root) {
		t.Fatalf("root nativo recusado: root=%q err=%v", resolvedRoot, err)
	}
	if got, err := contextSafePath(root, file, "arquivo"); err != nil || got != filepath.Clean(file) {
		t.Fatalf("context path nativo recusado: got=%q err=%v", got, err)
	}
	if got, err := specConfined(root, file, "arquivo"); err != nil || got != filepath.Clean(file) {
		t.Fatalf("spec path nativo recusado: got=%q err=%v", got, err)
	}
	for _, value := range []string{`..\escape.md`, `.bianchini\STATE.md`, `.planning/secret.md`} {
		if _, err := contextSafePath(root, value, "referência"); err == nil {
			t.Fatalf("context aceitou referência insegura: %q", value)
		}
		if _, err := specConfined(root, value, "referência"); err == nil {
			t.Fatalf("spec aceitou referência insegura: %q", value)
		}
	}
}

func TestUnixAbsolutePathWithBackslashIsRejected(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("semântica específica de Unix")
	}
	root := t.TempDir()
	unsafe := filepath.Join(root, `segment\escape.md`)
	if _, err := contextSafePath(root, unsafe, "arquivo"); err == nil || !strings.Contains(err.Error(), "separador inválido") {
		t.Fatalf("context aceitou absoluto Unix com backslash: %v", err)
	}
	if _, err := specConfined(root, unsafe, "arquivo"); err == nil || !strings.Contains(err.Error(), "traversal") {
		t.Fatalf("spec aceitou absoluto Unix com backslash: %v", err)
	}
}
