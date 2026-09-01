package main

import (
	"archive/tar"
	"compress/gzip"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"io/fs"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"time"
)

var releaseTargets = []string{
	"darwin-amd64", "darwin-arm64", "linux-amd64", "linux-arm64", "windows-amd64",
}

type releaseArtifact struct {
	Target  string `json:"target"`
	Archive string `json:"archive"`
	SHA256  string `json:"sha256"`
	Size    int64  `json:"size"`
	Binary  string `json:"binary"`
}

type releaseManifest struct {
	SchemaVersion int               `json:"schema_version"`
	Version       string            `json:"version"`
	BuildCommit   string            `json:"build_commit"`
	SourceEpoch   int64             `json:"source_date_epoch"`
	Artifacts     []releaseArtifact `json:"artifacts"`
}

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(2)
	}
}

func run() error {
	repository := flag.String("repo", ".", "repository root")
	output := flag.String("output", "dist", "output directory")
	version := flag.String("version", "", "release version; defaults to skills/_shared/VERSION")
	commit := flag.String("commit", "", "build commit; defaults to HEAD")
	entrypoint := flag.String("entrypoint", "./cmd/bm-preview", "Go CLI package")
	targets := flag.String("targets", strings.Join(releaseTargets, ","), "comma-separated target matrix")
	flag.Parse()

	root, err := filepath.Abs(*repository)
	if err != nil {
		return err
	}
	if info, err := os.Lstat(root); err != nil || info.Mode()&os.ModeSymlink != 0 || !info.IsDir() {
		return fmt.Errorf("release root must be a real directory: %s", root)
	}
	resolvedCommit, err := resolveReleaseCommit(root, *commit)
	if err != nil {
		return err
	}
	if err := requireCleanReleaseInputs(root); err != nil {
		return err
	}
	resolvedVersion := strings.TrimSpace(*version)
	versionBytes, err := os.ReadFile(filepath.Join(root, "skills", "_shared", "VERSION"))
	if err != nil {
		return fmt.Errorf("read packaged version: %w", err)
	}
	packagedVersion := strings.TrimSpace(string(versionBytes))
	if resolvedVersion == "" {
		resolvedVersion = packagedVersion
	}
	if !semanticReleaseVersion(resolvedVersion) {
		return fmt.Errorf("invalid release version: %s", resolvedVersion)
	}
	if packagedVersion != resolvedVersion {
		return fmt.Errorf("skills version %s differs from release %s", packagedVersion, resolvedVersion)
	}
	epoch, err := releaseEpoch(root, resolvedCommit)
	if err != nil {
		return err
	}
	selected, err := parseReleaseTargets(*targets)
	if err != nil {
		return err
	}
	destination, err := filepath.Abs(*output)
	if err != nil {
		return err
	}
	if err := os.MkdirAll(destination, 0o755); err != nil {
		return err
	}
	temporary, err := os.MkdirTemp("", "bm-release-build.*")
	if err != nil {
		return err
	}
	defer os.RemoveAll(temporary)

	manifest := releaseManifest{SchemaVersion: 1, Version: resolvedVersion, BuildCommit: resolvedCommit, SourceEpoch: epoch}
	for _, target := range selected {
		parts := strings.Split(target, "-")
		goos, goarch := parts[0], parts[1]
		binaryName := "bm"
		if goos == "windows" {
			binaryName = "bm.exe"
		}
		binary := filepath.Join(temporary, target, binaryName)
		if err := os.MkdirAll(filepath.Dir(binary), 0o755); err != nil {
			return err
		}
		ldflags := "-s -w -buildid= -X github.com/felipebianchini2006/bianchini-method/internal/gokernel.BuildCommit=" + resolvedCommit
		command := exec.Command("go", "build", "-mod=readonly", "-trimpath", "-ldflags", ldflags, "-o", binary, *entrypoint)
		command.Dir = root
		command.Env = append(os.Environ(), "CGO_ENABLED=0", "GOOS="+goos, "GOARCH="+goarch)
		if output, err := command.CombinedOutput(); err != nil {
			return fmt.Errorf("build %s: %w\n%s", target, err, output)
		}
		archiveName := fmt.Sprintf("bianchini-method_%s_%s.tar.gz", resolvedVersion, target)
		archive := filepath.Join(destination, archiveName)
		packageRoot := fmt.Sprintf("bianchini-method_%s_%s", resolvedVersion, target)
		if err := createReleaseArchive(root, archive, packageRoot, binary, binaryName, time.Unix(epoch, 0).UTC()); err != nil {
			return fmt.Errorf("package %s: %w", target, err)
		}
		digest, size, err := digestReleaseFile(archive)
		if err != nil {
			return err
		}
		manifest.Artifacts = append(manifest.Artifacts, releaseArtifact{
			Target: target, Archive: archiveName, SHA256: digest, Size: size,
			Binary: filepath.ToSlash(filepath.Join("skills", "_shared", "bin", binaryName)),
		})
	}
	manifestBytes, _ := json.MarshalIndent(manifest, "", "  ")
	manifestBytes = append(manifestBytes, '\n')
	if err := atomicReleaseWrite(filepath.Join(destination, "release-manifest.json"), manifestBytes, 0o644); err != nil {
		return err
	}
	checksumLines := make([]string, 0, len(manifest.Artifacts))
	for _, artifact := range manifest.Artifacts {
		checksumLines = append(checksumLines, artifact.SHA256+"  "+artifact.Archive)
	}
	if err := atomicReleaseWrite(filepath.Join(destination, "SHA256SUMS"), []byte(strings.Join(checksumLines, "\n")+"\n"), 0o644); err != nil {
		return err
	}
	encoder := json.NewEncoder(os.Stdout)
	encoder.SetIndent("", "  ")
	return encoder.Encode(manifest)
}

func parseReleaseTargets(value string) ([]string, error) {
	allowed := map[string]bool{}
	for _, target := range releaseTargets {
		allowed[target] = true
	}
	seen := map[string]bool{}
	result := []string{}
	for _, raw := range strings.Split(value, ",") {
		target := strings.TrimSpace(raw)
		if !allowed[target] {
			return nil, fmt.Errorf("unsupported release target: %s", target)
		}
		if !seen[target] {
			seen[target] = true
			result = append(result, target)
		}
	}
	if len(result) == 0 {
		return nil, errors.New("at least one release target is required")
	}
	return result, nil
}

func semanticReleaseVersion(value string) bool {
	parts := strings.Split(value, ".")
	if len(parts) != 3 {
		return false
	}
	for _, part := range parts {
		if part == "" {
			return false
		}
		if _, err := strconv.ParseUint(part, 10, 64); err != nil {
			return false
		}
	}
	return true
}

func releaseEpoch(root, commit string) (int64, error) {
	if value := strings.TrimSpace(os.Getenv("SOURCE_DATE_EPOCH")); value != "" {
		epoch, err := strconv.ParseInt(value, 10, 64)
		if err != nil || epoch < 0 {
			return 0, fmt.Errorf("invalid SOURCE_DATE_EPOCH: %q", value)
		}
		return epoch, nil
	}
	value, err := gitOutput(root, "show", "-s", "--format=%ct", commit)
	if err != nil {
		return 0, err
	}
	epoch, err := strconv.ParseInt(strings.TrimSpace(value), 10, 64)
	if err != nil {
		return 0, fmt.Errorf("invalid commit epoch: %w", err)
	}
	return epoch, nil
}

func gitOutput(root string, args ...string) (string, error) {
	command := exec.Command("git", args...)
	command.Dir = root
	output, err := command.CombinedOutput()
	if err != nil {
		return "", fmt.Errorf("git %s: %w\n%s", strings.Join(args, " "), err, output)
	}
	return strings.TrimSpace(string(output)), nil
}

func resolveReleaseCommit(root, requested string) (string, error) {
	requested = strings.TrimSpace(requested)
	if requested == "" {
		requested = "HEAD"
	}
	if strings.ContainsAny(requested, " \t\r\n") {
		return "", fmt.Errorf("commit de release inválido: %q", requested)
	}
	resolved, err := gitOutput(root, "rev-parse", "--verify", requested+"^{commit}")
	if err != nil || !regexp.MustCompile(`^[0-9a-f]{40}$`).MatchString(resolved) {
		return "", fmt.Errorf("commit de release inválido: %q", requested)
	}
	head, err := gitOutput(root, "rev-parse", "HEAD")
	if err != nil {
		return "", err
	}
	if resolved != head {
		return "", fmt.Errorf("commit de release %s não corresponde ao HEAD %s", resolved, head)
	}
	return resolved, nil
}

func requireCleanReleaseInputs(root string) error {
	status, err := gitOutput(root, "status", "--porcelain=v1", "--untracked-files=all", "--",
		"cmd", "internal", "go.mod", "go.sum", "skills", "LICENSE", "THIRD_PARTY_NOTICES.md")
	if err != nil {
		return err
	}
	if status != "" {
		return fmt.Errorf("inputs de release possuem alterações locais:\n%s", status)
	}
	return nil
}

func createReleaseArchive(root, output, packageRoot, binary, binaryName string, epoch time.Time) error {
	temporary := output + ".part"
	if _, err := os.Lstat(temporary); err == nil {
		return fmt.Errorf("stale package staging exists: %s", temporary)
	}
	file, err := os.OpenFile(temporary, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0o644)
	if err != nil {
		return err
	}
	failed := true
	defer func() {
		_ = file.Close()
		if failed {
			_ = os.Remove(temporary)
		}
	}()
	gzipWriter, err := gzip.NewWriterLevel(file, gzip.BestCompression)
	if err != nil {
		return err
	}
	gzipWriter.Header.ModTime = epoch
	gzipWriter.Header.OS = 255
	tarWriter := tar.NewWriter(gzipWriter)
	closeWithError := func() error {
		if err := tarWriter.Close(); err != nil {
			return err
		}
		if err := gzipWriter.Close(); err != nil {
			return err
		}
		if err := file.Sync(); err != nil {
			return err
		}
		return file.Close()
	}
	if err := writeTarDirectory(tarWriter, packageRoot, epoch); err != nil {
		return err
	}
	if err := addTrackedReleaseTree(tarWriter, root, packageRoot, epoch); err != nil {
		return err
	}
	if err := writeTarDirectory(tarWriter, packageRoot+"/skills/_shared/bin", epoch); err != nil {
		return err
	}
	if err := writeTarFileFromPath(tarWriter, binary, packageRoot+"/skills/_shared/bin/"+binaryName, 0o755, epoch); err != nil {
		return err
	}
	for _, legal := range []string{"LICENSE", "THIRD_PARTY_NOTICES.md"} {
		source := filepath.Join(root, legal)
		if err := writeTarFileFromPath(tarWriter, source, packageRoot+"/"+legal, 0o644, epoch); err != nil {
			return err
		}
		if err := writeTarFileFromPath(tarWriter, source, packageRoot+"/skills/_shared/"+legal, 0o644, epoch); err != nil {
			return err
		}
	}
	if err := closeWithError(); err != nil {
		return err
	}
	if err := os.Rename(temporary, output); err != nil {
		return err
	}
	failed = false
	return nil
}

func addTrackedReleaseTree(writer *tar.Writer, root, packageRoot string, epoch time.Time) error {
	command := exec.Command("git", "ls-files", "-z", "--", "skills")
	command.Dir = root
	output, err := command.Output()
	if err != nil {
		return fmt.Errorf("list tracked skills: %w", err)
	}
	files := []string{}
	directories := map[string]bool{packageRoot + "/skills": true}
	for _, raw := range strings.Split(string(output), "\x00") {
		relative := filepath.ToSlash(raw)
		if relative == "" {
			continue
		}
		if !strings.HasPrefix(relative, "skills/") || strings.Contains(relative, "../") {
			return fmt.Errorf("unsafe tracked skill path: %s", relative)
		}
		source := filepath.Join(root, filepath.FromSlash(relative))
		info, err := os.Lstat(source)
		if err != nil || info.Mode()&os.ModeSymlink != 0 || !info.Mode().IsRegular() {
			return fmt.Errorf("release input is not a regular tracked file: %s", source)
		}
		files = append(files, relative)
		archivePath := packageRoot + "/" + relative
		for directory := filepath.ToSlash(filepath.Dir(archivePath)); directory != "." && strings.HasPrefix(directory, packageRoot); directory = filepath.ToSlash(filepath.Dir(directory)) {
			directories[directory] = true
			if directory == packageRoot {
				break
			}
		}
	}
	directoryNames := make([]string, 0, len(directories))
	for directory := range directories {
		if directory != packageRoot {
			directoryNames = append(directoryNames, directory)
		}
	}
	sort.Strings(directoryNames)
	for _, directory := range directoryNames {
		if err := writeTarDirectory(writer, directory, epoch); err != nil {
			return err
		}
	}
	sort.Strings(files)
	for _, relative := range files {
		source := filepath.Join(root, filepath.FromSlash(relative))
		info, err := os.Lstat(source)
		if err != nil {
			return err
		}
		if err := writeTarFileFromPath(writer, source, packageRoot+"/"+relative, info.Mode().Perm(), epoch); err != nil {
			return err
		}
	}
	return nil
}

func writeTarDirectory(writer *tar.Writer, name string, epoch time.Time) error {
	header := &tar.Header{Name: strings.TrimSuffix(name, "/") + "/", Typeflag: tar.TypeDir, Mode: 0o755, ModTime: epoch, AccessTime: epoch, ChangeTime: epoch, Uid: 0, Gid: 0}
	return writer.WriteHeader(header)
}

func writeTarFileFromPath(writer *tar.Writer, source, name string, mode fs.FileMode, epoch time.Time) error {
	file, err := os.Open(source)
	if err != nil {
		return err
	}
	defer file.Close()
	info, err := file.Stat()
	if err != nil || !info.Mode().IsRegular() {
		return fmt.Errorf("release input is not a regular file: %s", source)
	}
	header := &tar.Header{Name: name, Typeflag: tar.TypeReg, Mode: int64(mode.Perm()), Size: info.Size(), ModTime: epoch, AccessTime: epoch, ChangeTime: epoch, Uid: 0, Gid: 0}
	if err := writer.WriteHeader(header); err != nil {
		return err
	}
	_, err = io.Copy(writer, file)
	return err
}

func digestReleaseFile(path string) (string, int64, error) {
	file, err := os.Open(path)
	if err != nil {
		return "", 0, err
	}
	defer file.Close()
	hash := sha256.New()
	size, err := io.Copy(hash, file)
	if err != nil {
		return "", 0, err
	}
	return hex.EncodeToString(hash.Sum(nil)), size, nil
}

func atomicReleaseWrite(path string, content []byte, mode fs.FileMode) error {
	temporary := path + ".part"
	if err := os.WriteFile(temporary, content, mode); err != nil {
		return err
	}
	return os.Rename(temporary, path)
}
