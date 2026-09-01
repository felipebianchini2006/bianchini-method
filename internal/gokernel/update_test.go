package gokernel

import (
	"archive/tar"
	"bytes"
	"compress/gzip"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func writeUpdateInstallation(t *testing.T, root, version, marker string) {
	t.Helper()
	for _, name := range managedSkillDirectories {
		directory := filepath.Join(root, name)
		if err := os.MkdirAll(directory, 0o755); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(filepath.Join(directory, "PACKAGE.txt"), []byte(marker+"\n"), 0o644); err != nil {
			t.Fatal(err)
		}
	}
	if err := os.WriteFile(filepath.Join(root, "_shared", "VERSION"), []byte(version+"\n"), 0o644); err != nil {
		t.Fatal(err)
	}
}

type updateArchiveEntry struct {
	name     string
	content  []byte
	typeflag byte
	linkname string
	size     int64
}

func updateArchive(t *testing.T, version, marker string, extra ...updateArchiveEntry) []byte {
	t.Helper()
	entries := []updateArchiveEntry{{name: "bianchini-method-main/skills/_shared/VERSION", content: []byte(version + "\n")}}
	for _, name := range managedSkillDirectories {
		entries = append(entries, updateArchiveEntry{name: "bianchini-method-main/skills/" + name + "/PACKAGE.txt", content: []byte(marker + "\n")})
	}
	entries = append(entries, extra...)
	return rawUpdateArchive(t, entries)
}

func rawUpdateArchive(t *testing.T, entries []updateArchiveEntry) []byte {
	t.Helper()
	var buffer bytes.Buffer
	compressed := gzip.NewWriter(&buffer)
	archive := tar.NewWriter(compressed)
	for _, entry := range entries {
		typeflag := entry.typeflag
		if typeflag == 0 {
			typeflag = tar.TypeReg
		}
		size := int64(len(entry.content))
		if entry.size != 0 {
			size = entry.size
		}
		header := &tar.Header{Name: entry.name, Mode: 0o644, Size: size, Typeflag: typeflag, Linkname: entry.linkname}
		if err := archive.WriteHeader(header); err != nil {
			t.Fatal(err)
		}
		if len(entry.content) > 0 {
			if _, err := archive.Write(entry.content); err != nil {
				t.Fatal(err)
			}
		}
	}
	if err := archive.Close(); err != nil {
		t.Fatal(err)
	}
	if err := compressed.Close(); err != nil {
		t.Fatal(err)
	}
	return buffer.Bytes()
}

func updateFetcher(version string, archive, manifest []byte) (updateFetch, *[]string) {
	calls := []string{}
	fetch := func(url string, _ time.Duration) ([]byte, error) {
		calls = append(calls, url)
		switch {
		case strings.HasSuffix(url, "/skills/_shared/VERSION"):
			return []byte(version + "\n"), nil
		case strings.HasSuffix(url, "/skills/_shared/releases/0.4.0.json"):
			return manifest, nil
		case strings.Contains(url, "/releases/download/"):
			return archive, nil
		default:
			return nil, fmt.Errorf("URL inesperada: %s", url)
		}
	}
	return fetch, &calls
}

func TestUpdateUsesVersionedNativeReleaseArchive(t *testing.T) {
	url, err := updateArchiveURL("0.5.0", "darwin", "arm64")
	if err != nil {
		t.Fatal(err)
	}
	want := "https://github.com/felipebianchini2006/bianchini-method/releases/download/v0.5.0/bianchini-method_0.5.0_darwin-arm64.tar.gz"
	if url != want {
		t.Fatalf("url=%q, esperado %q", url, want)
	}
	if _, err := updateArchiveURL("0.5.0", "plan9", "amd64"); err == nil || !strings.Contains(err.Error(), "plataforma sem pacote oficial") {
		t.Fatalf("plataforma sem distribuição aceita: %v", err)
	}
}

func TestUpdateParserFreezesPublicFlagsWithoutTestSource(t *testing.T) {
	fetch, calls := updateFetcher("3.2.0", nil, nil)
	_, err := runUpdateWithFetcher([]string{
		"--check", "--skills-root", filepath.Join(t.TempDir(), "missing-skills"),
		"--timeout", "0.001", "--format", "json",
	}, fetch, defaultUpdateFS())
	if err == nil || !strings.HasPrefix(err.Error(), "raiz de skills não encontrada ou insegura:") {
		t.Fatalf("err=%v", err)
	}
	if len(*calls) != 0 {
		t.Fatalf("fetch called before root validation: %v", *calls)
	}
	_, err = runUpdateWithFetcher([]string{"--source", "local"}, fetch, defaultUpdateFS())
	if err == nil || !strings.Contains(err.Error(), "unrecognized arguments: --source") {
		t.Fatalf("unexpected extension accepted: %v", err)
	}
}

func TestUpdateCheckOnlyDoesNotDownloadOrWrite(t *testing.T) {
	skills := filepath.Join(t.TempDir(), "skills")
	writeUpdateInstallation(t, skills, "3.1.0", "local")
	fetch, calls := updateFetcher("3.2.0", nil, nil)
	resultValue, err := runUpdateWithFetcher([]string{"--check", "--skills-root", skills, "--format", "json"}, fetch, defaultUpdateFS())
	if err != nil {
		t.Fatal(err)
	}
	result := resultValue.(map[string]any)
	if stateString(result["status"]) != "update_available" || result["updated"] != false || len(*calls) != 1 {
		t.Fatalf("result=%#v calls=%v", result, *calls)
	}
	content, err := os.ReadFile(filepath.Join(skills, "_shared", "VERSION"))
	if err != nil || string(content) != "3.1.0\n" {
		t.Fatalf("version=%q err=%v", content, err)
	}
}

func TestInstalledPackageUpdatesAtomicallyAndPreservesForeignSkills(t *testing.T) {
	root := t.TempDir()
	skills := filepath.Join(root, "skills")
	writeUpdateInstallation(t, skills, "3.1.0", "local")
	foreign := filepath.Join(skills, "foreign-skill", "SKILL.md")
	if err := os.MkdirAll(filepath.Dir(foreign), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(foreign, []byte("foreign\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	fetch, calls := updateFetcher("3.2.0", updateArchive(t, "3.2.0", "remote"), nil)
	result, err := updateBianchiniMethod(updateRequest{skillsRoot: skills, fetch: fetch, fs: defaultUpdateFS(), timeout: 15 * time.Second})
	if err != nil {
		t.Fatal(err)
	}
	if stateString(result["status"]) != "updated" || stateString(result["mode"]) != "installed_package" || len(*calls) != 2 {
		t.Fatalf("result=%#v calls=%v", result, *calls)
	}
	assertUpdateMarker(t, skills, "3.2.0", "remote")
	if content, err := os.ReadFile(foreign); err != nil || string(content) != "foreign\n" {
		t.Fatalf("foreign=%q err=%v", content, err)
	}
	backup := stateString(result["backup"])
	assertUpdateMarker(t, backup, "3.1.0", "local")
}

func TestUpdateInstallsCleanSkillsRootFromZeroVersion(t *testing.T) {
	skills := filepath.Join(t.TempDir(), "skills")
	if err := os.Mkdir(skills, 0o755); err != nil {
		t.Fatal(err)
	}
	fetch, calls := updateFetcher("3.2.0", updateArchive(t, "3.2.0", "clean"), nil)
	result, err := updateBianchiniMethod(updateRequest{skillsRoot: skills, fetch: fetch, fs: defaultUpdateFS(), timeout: 15 * time.Second})
	if err != nil {
		t.Fatal(err)
	}
	if stateString(result["installed_version"]) != "0.0.0" || stateString(result["status"]) != "updated" || len(*calls) != 2 {
		t.Fatalf("result=%#v calls=%v", result, *calls)
	}
	assertUpdateMarker(t, skills, "3.2.0", "clean")
}

func TestUpdateFailureRollsBackCompleteInstallation(t *testing.T) {
	skills := filepath.Join(t.TempDir(), "skills")
	writeUpdateInstallation(t, skills, "3.1.0", "local")
	fetch, _ := updateFetcher("3.2.0", updateArchive(t, "3.2.0", "remote"), nil)
	fsops := defaultUpdateFS()
	realRename := fsops.rename
	calls := 0
	fsops.rename = func(oldPath, newPath string) error {
		calls++
		if calls == 4 {
			return errors.New("falha simulada")
		}
		return realRename(oldPath, newPath)
	}
	_, err := updateBianchiniMethod(updateRequest{skillsRoot: skills, fetch: fetch, fs: fsops, timeout: 15 * time.Second})
	if err == nil || !strings.Contains(err.Error(), "rollback concluído") {
		t.Fatalf("err=%v", err)
	}
	assertUpdateMarker(t, skills, "3.1.0", "local")
}

func TestUpdateArchiveRejectsTraversalLinksDuplicatesAndSize(t *testing.T) {
	tests := []struct {
		name    string
		archive func(*testing.T) []byte
		want    string
	}{
		{"traversal", func(t *testing.T) []byte {
			return updateArchive(t, "3.2.0", "remote", updateArchiveEntry{name: "../../escape.txt", content: []byte("escape")})
		}, "arquivo inseguro"},
		{"symlink", func(t *testing.T) []byte {
			return updateArchive(t, "3.2.0", "remote", updateArchiveEntry{name: "bianchini-method-main/skills/link", typeflag: tar.TypeSymlink, linkname: "/tmp"})
		}, "arquivo inseguro"},
		{"hardlink", func(t *testing.T) []byte {
			return updateArchive(t, "3.2.0", "remote", updateArchiveEntry{name: "bianchini-method-main/skills/link", typeflag: tar.TypeLink, linkname: "target"})
		}, "arquivo inseguro"},
		{"duplicate", func(t *testing.T) []byte {
			return updateArchive(t, "3.2.0", "remote", updateArchiveEntry{name: "bianchini-method-main/skills/_shared/VERSION", content: []byte("3.2.0\n")})
		}, "arquivo duplicado"},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			skills := filepath.Join(t.TempDir(), "skills")
			writeUpdateInstallation(t, skills, "3.1.0", "local")
			fetch, _ := updateFetcher("3.2.0", test.archive(t), nil)
			_, err := updateBianchiniMethod(updateRequest{skillsRoot: skills, fetch: fetch, fs: defaultUpdateFS(), timeout: 15 * time.Second})
			if err == nil || !strings.Contains(err.Error(), test.want) {
				t.Fatalf("err=%v", err)
			}
			assertUpdateMarker(t, skills, "3.1.0", "local")
		})
	}

	t.Run("declared extracted size", func(t *testing.T) {
		var buffer bytes.Buffer
		compressed := gzip.NewWriter(&buffer)
		archive := tar.NewWriter(compressed)
		if err := archive.WriteHeader(&tar.Header{Name: "bianchini-method-main/skills/huge", Mode: 0o644, Typeflag: tar.TypeReg, Size: maxUpdateArchiveBytes + 1}); err != nil {
			t.Fatal(err)
		}
		// Deliberately do not close tar: extraction must reject the declared size before reading the body.
		if err := compressed.Close(); err != nil {
			t.Fatal(err)
		}
		destination := t.TempDir()
		_, err := extractUpdateArchive(buffer.Bytes(), destination)
		if err == nil || !strings.Contains(err.Error(), "conteúdo extraído excede") {
			t.Fatalf("err=%v", err)
		}
	})
}

func TestUpdateLineageResetTo040RequiresAndValidatesManifest(t *testing.T) {
	manifest := []byte(`{"schema_version":1,"release_version":"0.4.0","lineage_reset":{"authorized":true,"from_major_versions":[3],"to_version":"0.4.0"}}`)
	manifest = append(manifest, '\n')
	archive := updateArchive(t, "0.4.0", "reset", updateArchiveEntry{name: "bianchini-method-main/skills/_shared/releases/0.4.0.json", content: manifest})

	t.Run("authorized", func(t *testing.T) {
		skills := filepath.Join(t.TempDir(), "skills")
		writeUpdateInstallation(t, skills, "3.2.0", "local")
		fetch, calls := updateFetcher("0.4.0", archive, manifest)
		result, err := updateBianchiniMethod(updateRequest{skillsRoot: skills, fetch: fetch, fs: defaultUpdateFS(), timeout: 15 * time.Second})
		if err != nil {
			t.Fatal(err)
		}
		if stateString(result["status"]) != "updated" || len(*calls) != 3 {
			t.Fatalf("result=%#v calls=%v", result, *calls)
		}
		assertUpdateMarker(t, skills, "0.4.0", "reset")
	})

	t.Run("invalid authorization", func(t *testing.T) {
		skills := filepath.Join(t.TempDir(), "skills")
		writeUpdateInstallation(t, skills, "3.2.0", "local")
		bad := bytes.Replace(manifest, []byte(`"authorized":true`), []byte(`"authorized":false`), 1)
		fetch, _ := updateFetcher("0.4.0", archive, bad)
		_, err := updateBianchiniMethod(updateRequest{skillsRoot: skills, fetch: fetch, fs: defaultUpdateFS(), timeout: 15 * time.Second})
		if err == nil || !strings.Contains(err.Error(), "não autoriza") {
			t.Fatalf("err=%v", err)
		}
		assertUpdateMarker(t, skills, "3.2.0", "local")
	})
}

func TestUpdateGitCheckoutFastForwardsOfficialMainWithoutArchive(t *testing.T) {
	root := t.TempDir()
	remote := filepath.Join(root, "remote.git")
	seed := filepath.Join(root, "seed")
	local := filepath.Join(root, "local")
	updateGitCommand(t, root, "init", "--bare", remote)
	if err := os.Mkdir(seed, 0o755); err != nil {
		t.Fatal(err)
	}
	updateGitCommand(t, seed, "init", "-b", "main")
	updateGitCommand(t, seed, "config", "user.name", "BM Test")
	updateGitCommand(t, seed, "config", "user.email", "test@example.invalid")
	writeUpdateInstallation(t, filepath.Join(seed, "skills"), "3.1.0", "old")
	updateGitCommand(t, seed, "add", "skills")
	updateGitCommand(t, seed, "commit", "-m", "v3.1")
	updateGitCommand(t, seed, "remote", "add", "origin", remote)
	updateGitCommand(t, seed, "push", "-u", "origin", "main")
	updateGitCommand(t, root, "clone", "--branch", "main", remote, local)
	official := "https://github.com/felipebianchini2006/bianchini-method.git"
	updateGitCommand(t, local, "remote", "set-url", "origin", official)
	updateGitCommand(t, local, "config", "url.file://"+remote+"/.insteadOf", official)

	writeUpdateInstallation(t, filepath.Join(seed, "skills"), "3.2.0", "new")
	updateGitCommand(t, seed, "add", "skills")
	updateGitCommand(t, seed, "commit", "-m", "v3.2")
	updateGitCommand(t, seed, "push", "origin", "main")
	expectedHead := updateGitCommand(t, seed, "rev-parse", "HEAD")
	fetch, calls := updateFetcher("3.2.0", nil, nil)
	result, err := updateBianchiniMethod(updateRequest{skillsRoot: filepath.Join(local, "skills"), fetch: fetch, fs: defaultUpdateFS(), timeout: 15 * time.Second})
	if err != nil {
		t.Fatal(err)
	}
	if stateString(result["mode"]) != "git_checkout" || stateString(result["status"]) != "updated" || len(*calls) != 1 {
		t.Fatalf("result=%#v calls=%v", result, *calls)
	}
	if head := updateGitCommand(t, local, "rev-parse", "HEAD"); head != expectedHead {
		t.Fatalf("head=%s want=%s", head, expectedHead)
	}
	assertUpdateMarker(t, filepath.Join(local, "skills"), "3.2.0", "new")
}

func assertUpdateMarker(t *testing.T, root, version, marker string) {
	t.Helper()
	versionBytes, err := os.ReadFile(filepath.Join(root, "_shared", "VERSION"))
	if err != nil || strings.TrimSpace(string(versionBytes)) != version {
		t.Fatalf("version=%q err=%v", versionBytes, err)
	}
	for _, name := range managedSkillDirectories {
		content, err := os.ReadFile(filepath.Join(root, name, "PACKAGE.txt"))
		if err != nil || strings.TrimSpace(string(content)) != marker {
			t.Fatalf("%s marker=%q err=%v", name, content, err)
		}
	}
}

func updateGitCommand(t *testing.T, directory string, args ...string) string {
	t.Helper()
	command := exec.Command("git", args...)
	command.Dir = directory
	command.Env = append(os.Environ(), "GIT_AUTHOR_DATE=2020-01-01T00:00:00Z", "GIT_COMMITTER_DATE=2020-01-01T00:00:00Z")
	output, err := command.CombinedOutput()
	if err != nil {
		t.Fatalf("git %v: %v: %s", args, err, output)
	}
	return strings.TrimSpace(string(output))
}
