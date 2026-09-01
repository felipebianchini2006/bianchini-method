package gokernel

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func TestAdapterRenderMatchesCanonicalFixtures(t *testing.T) {
	for _, host := range []string{"generic", "codex", "claude-compatible"} {
		t.Run(host, func(t *testing.T) {
			code, stdout, stderr := runCLI(t, "adapter", "render", "--host", host)
			if code != 0 || stderr != "" {
				t.Fatalf("code=%d stderr=%q", code, stderr)
			}
			var payload map[string]any
			if err := json.Unmarshal([]byte(stdout), &payload); err != nil {
				t.Fatal(err)
			}
			expected, err := os.ReadFile(filepath.Join("..", "..", "tests", "fixtures", "host_adapters", host+".md"))
			if err != nil {
				t.Fatal(err)
			}
			if payload["host"] != host || payload["content"] != string(expected) || payload["digest"] != sha256Bytes(expected) {
				t.Fatalf("payload mismatch: %#v", payload)
			}
		})
	}
}

func TestAdapterInstallIsIdempotentAndPreservesForeignBytes(t *testing.T) {
	repo := t.TempDir()
	target := filepath.Join(repo, "AGENTS.md")
	foreign := []byte("# Regras estrangeiras\n\nPreservar.\n")
	if err := os.WriteFile(target, foreign, 0o640); err != nil {
		t.Fatal(err)
	}
	code, stdout, stderr := runCLI(t, "adapter", "install", "--host", "generic", "--repo", repo)
	if code != 0 || stderr != "" {
		t.Fatalf("code=%d stderr=%q", code, stderr)
	}
	var first map[string]any
	if err := json.Unmarshal([]byte(stdout), &first); err != nil {
		t.Fatal(err)
	}
	if first["status"] != "installed" || first["changed"] != true {
		t.Fatalf("first=%#v", first)
	}
	firstBytes, err := os.ReadFile(target)
	if err != nil {
		t.Fatal(err)
	}
	if len(firstBytes) <= len(foreign) || string(firstBytes[:len(foreign)]) != string(foreign) {
		t.Fatalf("foreign prefix changed: %q", firstBytes)
	}
	info, err := os.Stat(target)
	if err != nil {
		t.Fatal(err)
	}
	if info.Mode().Perm() != 0o640 {
		t.Fatalf("mode=%o", info.Mode().Perm())
	}
	code, stdout, stderr = runCLI(t, "adapter", "install", "--host", "generic", "--repo", repo)
	if code != 0 || stderr != "" {
		t.Fatalf("second code=%d stderr=%q", code, stderr)
	}
	var second map[string]any
	if err := json.Unmarshal([]byte(stdout), &second); err != nil {
		t.Fatal(err)
	}
	if second["status"] != "unchanged" || second["changed"] != false {
		t.Fatalf("second=%#v", second)
	}
}

func TestAdapterInstallRejectsSymlinkWithoutMutation(t *testing.T) {
	repo := t.TempDir()
	outside := filepath.Join(repo, "outside.md")
	if err := os.WriteFile(outside, []byte("fora\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(outside, filepath.Join(repo, "AGENTS.md")); err != nil {
		t.Fatal(err)
	}
	code, stdout, stderr := runCLI(t, "adapter", "install", "--host", "generic", "--repo", repo)
	if code != 3 || stdout != "" || stderr != "HOST_ADAPTER_SYMLINK: target não pode ser symlink: AGENTS.md\n" {
		t.Fatalf("code=%d stdout=%q stderr=%q", code, stdout, stderr)
	}
	content, err := os.ReadFile(outside)
	if err != nil || string(content) != "fora\n" {
		t.Fatalf("outside=%q err=%v", content, err)
	}
}
