package gokernel

import (
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

// Opt-in: exercises a real Docker daemon without pulling images or using volumes.
func TestRealContainerArtifactIdentity(t *testing.T) {
	if os.Getenv("BM_TEST_DOCKER") != "1" {
		t.Skip("set BM_TEST_DOCKER=1 for the real Docker integration")
	}
	directory := t.TempDir()
	architecture, err := exec.Command("docker", "info", "--format", "{{.Architecture}}").Output()
	if err != nil {
		t.Fatal(err)
	}
	arch := strings.TrimSpace(string(architecture))
	if arch == "aarch64" {
		arch = "arm64"
	}
	if arch == "x86_64" {
		arch = "amd64"
	}
	if !oneOf(arch, "arm64", "amd64") {
		t.Fatalf("unsupported daemon architecture: %s", arch)
	}
	if err := os.WriteFile(filepath.Join(directory, "main.go"), []byte("package main\nfunc main(){println(\"candidate-ok\")}\n"), 0600); err != nil {
		t.Fatal(err)
	}
	build := exec.Command("go", "build", "-trimpath", "-o", filepath.Join(directory, "candidate"), filepath.Join(directory, "main.go"))
	build.Env = append(os.Environ(), "CGO_ENABLED=0", "GOOS=linux", "GOARCH="+arch)
	if output, err := build.CombinedOutput(); err != nil {
		t.Fatalf("compile: %s %v", output, err)
	}
	if err := os.WriteFile(filepath.Join(directory, "Dockerfile"), []byte("FROM scratch\nCOPY candidate /candidate\nUSER 65534\nENTRYPOINT [\"/candidate\"]\n"), 0600); err != nil {
		t.Fatal(err)
	}
	tag := "bm-v1-identity:" + time.Now().UTC().Format("20060102150405.000000000")
	t.Cleanup(func() {
		if output, err := exec.Command("docker", "image", "rm", tag).CombinedOutput(); err != nil {
			t.Errorf("image cleanup: %s %v", output, err)
		}
	})
	if output, err := exec.Command("docker", "build", "--network=none", "--pull=false", "-t", tag, directory).CombinedOutput(); err != nil {
		t.Fatalf("image build: %s %v", output, err)
	}
	identity, err := releaseArtifactIdentity(directory, "container", tag, "")
	if err != nil {
		t.Fatal(err)
	}
	output, err := exec.Command("docker", "run", "--rm", "--network=none", "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges", "sha256:"+identity).CombinedOutput()
	if err != nil || strings.TrimSpace(string(output)) != "candidate-ok" {
		t.Fatalf("smoke on immutable identity: %s %v", output, err)
	}
	if _, err := releaseArtifactIdentity(directory, "container", tag, strings.Repeat("a", 64)); err == nil {
		t.Fatal("wrong image checksum accepted")
	}
	if _, err := releaseArtifactIdentity(directory, "container", tag+"-missing", ""); err == nil {
		t.Fatal("missing image accepted")
	}
}
