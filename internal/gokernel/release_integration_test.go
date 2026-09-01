package gokernel

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io/fs"
	"os"
	"os/exec"
	"path/filepath"
	"reflect"
	"runtime"
	"strings"
	"testing"
	"time"
)

type builtReleaseManifest struct {
	Version     string `json:"version"`
	BuildCommit string `json:"build_commit"`
	Artifacts   []struct {
		Target  string `json:"target"`
		Archive string `json:"archive"`
	} `json:"artifacts"`
}

type publicContractFixture struct {
	Argv     []string `json:"argv"`
	Expected struct {
		ExitCode int `json:"exit_code"`
		Stdout   struct {
			Kind  string `json:"kind"`
			Value any    `json:"value"`
		} `json:"stdout"`
		Stderr string `json:"stderr"`
	} `json:"expected"`
}

func TestRealReleaseArtifactInstallsRunsFixtureAndRollsBack(t *testing.T) {
	if !stringSet([]string{"darwin-amd64", "darwin-arm64", "linux-amd64", "linux-arm64", "windows-amd64"})[runtime.GOOS+"-"+runtime.GOARCH] {
		t.Skip("host sem target oficial de release")
	}
	root, err := filepath.Abs(filepath.Join("..", ".."))
	if err != nil {
		t.Fatal(err)
	}
	source := filepath.Join(t.TempDir(), "source")
	copyCurrentReleaseInputs(t, root, source)
	gitForReleaseIntegration(t, source, "init", "-b", "main")
	gitForReleaseIntegration(t, source, "config", "user.name", "BM Release Integration")
	gitForReleaseIntegration(t, source, "config", "user.email", "release-integration@example.invalid")
	gitForReleaseIntegration(t, source, "config", "commit.gpgsign", "false")
	gitForReleaseIntegration(t, source, "add", "cmd", "internal", "skills", "go.mod", "go.sum", "LICENSE", "THIRD_PARTY_NOTICES.md")
	gitForReleaseIntegration(t, source, "commit", "-m", "release fixture")
	commit := gitForReleaseIntegration(t, source, "rev-parse", "HEAD")

	dist := filepath.Join(t.TempDir(), "dist")
	target := runtime.GOOS + "-" + runtime.GOARCH
	builder := exec.Command("go", "run", "./tools/bm-release", "--repo", source, "--output", dist, "--targets", target)
	builder.Dir = root
	builder.Env = append(os.Environ(), "SOURCE_DATE_EPOCH=1700000000")
	if output, err := builder.CombinedOutput(); err != nil {
		t.Fatalf("builder real falhou: %v\n%s", err, output)
	}

	manifestBytes := mustReadReleaseIntegrationFile(t, filepath.Join(dist, "release-manifest.json"))
	checksums := mustReadReleaseIntegrationFile(t, filepath.Join(dist, "SHA256SUMS"))
	var manifest builtReleaseManifest
	if err := json.Unmarshal(manifestBytes, &manifest); err != nil {
		t.Fatal(err)
	}
	if manifest.Version != Version || manifest.BuildCommit != commit || len(manifest.Artifacts) != 1 || manifest.Artifacts[0].Target != target {
		t.Fatalf("manifesto real inesperado: %#v", manifest)
	}
	archive := mustReadReleaseIntegrationFile(t, filepath.Join(dist, manifest.Artifacts[0].Archive))
	fetch := exactBuiltReleaseFetcher(manifest.Version, manifestBytes, checksums, manifest.Artifacts[0].Archive, archive)

	t.Run("installs and executes frozen public fixture", func(t *testing.T) {
		skills := filepath.Join(t.TempDir(), "skills")
		writeUpdateInstallation(t, skills, "0.4.9", "local")
		result, err := updateBianchiniMethod(updateRequest{skillsRoot: skills, fetch: fetch, fs: defaultUpdateFS(), timeout: 15 * time.Second})
		if err != nil {
			t.Fatal(err)
		}
		if stateString(result["status"]) != "updated" || stateString(result["latest_version"]) != Version {
			t.Fatalf("resultado inesperado: %#v", result)
		}
		binary := filepath.Join(skills, "_shared", "bin", "bm")
		if runtime.GOOS == "windows" {
			binary += ".exe"
		}
		versionOutput, err := exec.Command(binary, "version", "--json").CombinedOutput()
		if err != nil {
			t.Fatalf("binário instalado não executou: %v\n%s", err, versionOutput)
		}
		var metadata VersionMetadata
		if err := json.Unmarshal(versionOutput, &metadata); err != nil {
			t.Fatalf("version --json inválido: %v\n%s", err, versionOutput)
		}
		if metadata.Version != Version || metadata.Engine != "go" || metadata.BuildCommit != commit || !metadata.Official || metadata.Preview {
			t.Fatalf("identidade instalada inesperada: %#v", metadata)
		}
		runInstalledContractFixture(t, root, binary, "change-policy-read-only.json")
	})

	t.Run("rename failure restores previous installation", func(t *testing.T) {
		skills := filepath.Join(t.TempDir(), "skills")
		writeUpdateInstallation(t, skills, "0.4.9", "local")
		fsops := defaultUpdateFS()
		realRename := fsops.rename
		renames := 0
		fsops.rename = func(oldPath, newPath string) error {
			renames++
			if renames == 4 {
				return errors.New("falha de rename injetada")
			}
			return realRename(oldPath, newPath)
		}
		_, err := updateBianchiniMethod(updateRequest{skillsRoot: skills, fetch: fetch, fs: fsops, timeout: 15 * time.Second})
		if err == nil || !strings.Contains(err.Error(), "rollback concluído") {
			t.Fatalf("rollback não foi comprovado: %v", err)
		}
		assertUpdateMarker(t, skills, "0.4.9", "local")
	})
}

func exactBuiltReleaseFetcher(version string, manifest, checksums []byte, archiveName string, archive []byte) updateFetch {
	return func(url string, _ time.Duration) ([]byte, error) {
		switch {
		case strings.HasSuffix(url, "/skills/_shared/VERSION"):
			return []byte(version + "\n"), nil
		case strings.HasSuffix(url, "/release-manifest.json"):
			return append([]byte(nil), manifest...), nil
		case strings.HasSuffix(url, "/SHA256SUMS"):
			return append([]byte(nil), checksums...), nil
		case strings.HasSuffix(url, "/"+archiveName):
			return append([]byte(nil), archive...), nil
		default:
			return nil, fmt.Errorf("URL inesperada: %s", url)
		}
	}
}

func runInstalledContractFixture(t *testing.T, root, binary, fixtureName string) {
	t.Helper()
	fixtureBytes := mustReadReleaseIntegrationFile(t, filepath.Join(root, "tests", "fixtures", "cli_contract", fixtureName))
	var fixture publicContractFixture
	if err := json.Unmarshal(fixtureBytes, &fixture); err != nil {
		t.Fatal(err)
	}
	if fixture.Expected.Stdout.Kind != "json" {
		t.Fatalf("fixture deve congelar stdout JSON: %s", fixtureName)
	}
	working := t.TempDir()
	keep := filepath.Join(working, "keep.txt")
	if err := os.WriteFile(keep, []byte("preservar\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	command := exec.Command(binary, fixture.Argv...)
	command.Dir = working
	var stdout, stderr bytes.Buffer
	command.Stdout = &stdout
	command.Stderr = &stderr
	err := command.Run()
	exitCode := 0
	if err != nil {
		var exitErr *exec.ExitError
		if !errors.As(err, &exitErr) {
			t.Fatal(err)
		}
		exitCode = exitErr.ExitCode()
	}
	if exitCode != fixture.Expected.ExitCode || stderr.String() != fixture.Expected.Stderr {
		t.Fatalf("fixture %s: exit=%d stderr=%q", fixtureName, exitCode, stderr.String())
	}
	want, err := json.MarshalIndent(fixture.Expected.Stdout.Value, "", "  ")
	if err != nil {
		t.Fatal(err)
	}
	want = append(want, '\n')
	if !bytes.Equal(stdout.Bytes(), want) {
		t.Fatalf("fixture %s divergiu\n got: %s\nwant: %s", fixtureName, stdout.Bytes(), want)
	}
	if content, err := os.ReadFile(keep); err != nil || !reflect.DeepEqual(content, []byte("preservar\n")) {
		t.Fatalf("fixture alterou arquivo preservado: content=%q err=%v", content, err)
	}
}

func copyCurrentReleaseInputs(t *testing.T, root, destination string) {
	t.Helper()
	for _, relative := range []string{"cmd", "internal", "skills"} {
		sourceRoot := filepath.Join(root, relative)
		err := filepath.WalkDir(sourceRoot, func(path string, entry fs.DirEntry, walkErr error) error {
			if walkErr != nil {
				return walkErr
			}
			if entry.Name() == ".planning" {
				return filepath.SkipDir
			}
			relativePath, err := filepath.Rel(root, path)
			if err != nil {
				return err
			}
			target := filepath.Join(destination, relativePath)
			info, err := entry.Info()
			if err != nil {
				return err
			}
			if entry.IsDir() {
				return os.MkdirAll(target, info.Mode().Perm())
			}
			if info.Mode()&os.ModeSymlink != 0 || !info.Mode().IsRegular() {
				return fmt.Errorf("input de release não regular: %s", relativePath)
			}
			content, err := os.ReadFile(path)
			if err != nil {
				return err
			}
			return os.WriteFile(target, content, info.Mode().Perm())
		})
		if err != nil {
			t.Fatal(err)
		}
	}
	for _, name := range []string{"go.mod", "go.sum", "LICENSE", "THIRD_PARTY_NOTICES.md"} {
		content := mustReadReleaseIntegrationFile(t, filepath.Join(root, name))
		if err := os.WriteFile(filepath.Join(destination, name), content, 0o644); err != nil {
			t.Fatal(err)
		}
	}
}

func gitForReleaseIntegration(t *testing.T, directory string, args ...string) string {
	t.Helper()
	command := exec.Command("git", args...)
	command.Dir = directory
	command.Env = append(os.Environ(), "GIT_AUTHOR_DATE=2020-01-01T00:00:00Z", "GIT_COMMITTER_DATE=2020-01-01T00:00:00Z")
	output, err := command.CombinedOutput()
	if err != nil {
		t.Fatalf("git %v: %v\n%s", args, err, output)
	}
	return strings.TrimSpace(string(output))
}

func mustReadReleaseIntegrationFile(t *testing.T, path string) []byte {
	t.Helper()
	content, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	return content
}
