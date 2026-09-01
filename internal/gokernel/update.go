package gokernel

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"runtime"
	"sort"
	"strconv"
	"strings"
	"time"
)

const (
	officialUpdateRepository = "felipebianchini2006/bianchini-method"
	officialUpdateBranch     = "main"
	maxUpdateVersionBytes    = 128
	maxUpdateManifestBytes   = 8 * 1024
	maxUpdateArchiveBytes    = 64 * 1024 * 1024
	lineageResetVersion      = "0.4.0"
	lineageResetManifest     = "_shared/releases/0.4.0.json"
)

var managedSkillDirectories = []string{
	"_shared", "preparar-escopo", "design-projeto", "sdd-planning",
	"executar-plano", "executar-direto", "auditar-arquitetura", "status-projeto",
	"corrigir-bug", "migrar-bianchini", "homologar-sistema", "update-bm",
}

type updateFetch func(url string, timeout time.Duration) ([]byte, error)

type semanticVersion struct {
	major int
	minor int
	patch int
}

type updateRequest struct {
	skillsRoot string
	checkOnly  bool
	fetch      updateFetch
	fs         updateFS
	timeout    time.Duration
}

func runUpdate(args []string) (any, error) {
	return runUpdateWithFetcher(args, defaultUpdateFetch, defaultUpdateFS())
}

func runUpdateWithFetcher(args []string, fetch updateFetch, fsops updateFS) (any, error) {
	flags, err := parseFlags(args, map[string]bool{"--skills-root": true, "--timeout": true, "--format": true}, map[string]bool{"--check": true})
	if err != nil {
		return nil, err
	}
	timeout := 15.0
	if raw := lastValue(flags, "--timeout"); raw != "" {
		timeout, err = strconv.ParseFloat(raw, 64)
		if err != nil {
			return nil, argparseError("argument --timeout: invalid float value: '" + raw + "'")
		}
	}
	format := lastValue(flags, "--format")
	if format == "" {
		format = "text"
	}
	if format != "text" && format != "json" {
		return nil, argparseError("argument --format: invalid choice: '" + format + "'")
	}
	skillsRoot := lastValue(flags, "--skills-root")
	if skillsRoot == "" {
		skillsRoot = defaultUpdateSkillsRoot()
	}
	result, err := updateBianchiniMethod(updateRequest{
		skillsRoot: skillsRoot, checkOnly: flags.booleans["--check"], fetch: fetch,
		fs: fsops, timeout: time.Duration(timeout * float64(time.Second)),
	})
	if err != nil {
		return nil, err
	}
	if format == "json" {
		return result, nil
	}
	return renderUpdateResult(result), nil
}

func updateBianchiniMethod(request updateRequest) (map[string]any, error) {
	if request.timeout <= 0 {
		return nil, userError("timeout deve ser positivo")
	}
	if request.fetch == nil {
		request.fetch = defaultUpdateFetch
	}
	if request.fs.rename == nil {
		request.fs = defaultUpdateFS()
	}
	root, err := resolveUpdateSkillsRoot(request.skillsRoot)
	if err != nil {
		return nil, err
	}
	installed, err := readInstalledUpdateVersion(root)
	if err != nil {
		return nil, err
	}
	installedVersion, err := parseUpdateVersion(installed)
	if err != nil {
		return nil, err
	}
	latestBytes, err := fetchUpdateLimited(request.fetch, updateVersionURL(), request.timeout, maxUpdateVersionBytes, "versão remota")
	if err != nil {
		return nil, err
	}
	if !validUTF8Text(latestBytes) {
		return nil, userError("versão remota não está em UTF-8")
	}
	latest := strings.TrimSpace(string(latestBytes))
	latestVersion, err := parseUpdateVersion(latest)
	if err != nil {
		return nil, err
	}
	gitRoot := updateGitRoot(root)
	mode := "installed_package"
	if gitRoot != "" {
		mode = "git_checkout"
	}
	var lineageManifest []byte
	if isLineageReset(installedVersion, latestVersion) {
		if gitRoot != "" {
			if err := verifyGitLineageSource(gitRoot); err != nil {
				return nil, err
			}
		}
		lineageManifest, err = fetchUpdateLimited(request.fetch, lineageManifestURL(), request.timeout, maxUpdateManifestBytes, "manifesto de reset")
		if err != nil {
			return nil, err
		}
		if err := validateLineageManifest(lineageManifest, installed, latest); err != nil {
			return nil, err
		}
	}
	comparison := compareUpdateVersion(installedVersion, latestVersion)
	if comparison == 0 {
		return updateBaseResult(installed, latest, root, mode, "up_to_date", false, ""), nil
	}
	if comparison > 0 && lineageManifest == nil {
		return updateBaseResult(installed, latest, root, mode, "ahead", false, ""), nil
	}
	if request.checkOnly {
		return updateBaseResult(installed, latest, root, mode, "update_available", false, ""), nil
	}
	if gitRoot != "" {
		return updateGitCheckout(gitRoot, root, installed, latest, lineageManifest)
	}
	archiveURL, err := updateArchiveURL(latest, runtime.GOOS, runtime.GOARCH)
	if err != nil {
		return nil, err
	}
	archiveBytes, err := fetchUpdateLimited(request.fetch, archiveURL, request.timeout, maxUpdateArchiveBytes, "archive oficial")
	if err != nil {
		return nil, err
	}
	extraction, err := os.MkdirTemp("", "bianchini-method-download.*")
	if err != nil {
		return nil, userError("não foi possível preparar archive: " + err.Error())
	}
	defer os.RemoveAll(extraction)
	remoteSkills, err := extractUpdateArchive(archiveBytes, extraction)
	if err != nil {
		return nil, err
	}
	if err := validateRemoteSkills(remoteSkills, latest, installed, lineageManifest); err != nil {
		return nil, err
	}
	backup, err := installSkillsAtomically(root, remoteSkills, installed, request.fs)
	if err != nil {
		return nil, err
	}
	finalVersion, err := readInstalledUpdateVersion(root)
	if err != nil {
		return nil, err
	}
	if finalVersion != latest {
		return nil, updateError("atualização terminou com versão "+finalVersion+"; esperado "+latest, 3)
	}
	return updateBaseResult(installed, latest, root, "installed_package", "updated", true, backup), nil
}

func parseUpdateVersion(value string) (semanticVersion, error) {
	text := strings.TrimSpace(value)
	match := regexp.MustCompile(`^([0-9]+)\.([0-9]+)\.([0-9]+)$`).FindStringSubmatch(text)
	if len(match) != 4 {
		empty := text
		if empty == "" {
			empty = "<vazia>"
		}
		return semanticVersion{}, userError("versão inválida: " + empty)
	}
	parts := [3]int{}
	for index := range parts {
		parsed, err := strconv.Atoi(match[index+1])
		if err != nil {
			return semanticVersion{}, userError("versão inválida: " + text)
		}
		parts[index] = parsed
	}
	return semanticVersion{major: parts[0], minor: parts[1], patch: parts[2]}, nil
}

func compareUpdateVersion(left, right semanticVersion) int {
	for _, pair := range [][2]int{{left.major, right.major}, {left.minor, right.minor}, {left.patch, right.patch}} {
		if pair[0] < pair[1] {
			return -1
		}
		if pair[0] > pair[1] {
			return 1
		}
	}
	return 0
}

func isLineageReset(installed, latest semanticVersion) bool {
	reset, _ := parseUpdateVersion(lineageResetVersion)
	return compareUpdateVersion(latest, reset) == 0 && compareUpdateVersion(installed, latest) > 0 && installed.major > 0
}

func updateVersionURL() string {
	base := "https://raw.githubusercontent.com/" + officialUpdateRepository + "/" + officialUpdateBranch
	return base + "/skills/_shared/VERSION"
}

func updateArchiveURL(version, goos, goarch string) (string, error) {
	if _, err := parseUpdateVersion(version); err != nil {
		return "", err
	}
	target := goos + "-" + goarch
	allowed := map[string]bool{
		"linux-amd64": true, "linux-arm64": true, "darwin-amd64": true,
		"darwin-arm64": true, "windows-amd64": true,
	}
	if !allowed[target] {
		return "", userError("plataforma sem pacote oficial: " + target)
	}
	name := "bianchini-method_" + version + "_" + target + ".tar.gz"
	return "https://github.com/" + officialUpdateRepository + "/releases/download/v" + version + "/" + name, nil
}

func lineageManifestURL() string {
	return "https://raw.githubusercontent.com/" + officialUpdateRepository + "/" + officialUpdateBranch + "/skills/" + lineageResetManifest
}

func defaultUpdateFetch(url string, timeout time.Duration) ([]byte, error) {
	ctx, cancel := context.WithTimeout(context.Background(), timeout)
	defer cancel()
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return nil, userError("não foi possível consultar a atualização: " + err.Error())
	}
	request.Header.Set("User-Agent", "Bianchini-Method-Updater/1")
	response, err := http.DefaultClient.Do(request)
	if err != nil {
		return nil, userError("não foi possível consultar a atualização: " + err.Error())
	}
	defer response.Body.Close()
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		return nil, userError("não foi possível consultar a atualização: HTTP " + response.Status)
	}
	content, err := io.ReadAll(io.LimitReader(response.Body, maxUpdateArchiveBytes+1))
	if err != nil {
		return nil, userError("não foi possível consultar a atualização: " + err.Error())
	}
	return content, nil
}

func fetchUpdateLimited(fetch updateFetch, url string, timeout time.Duration, limit int, label string) ([]byte, error) {
	content, err := fetch(url, timeout)
	if err != nil {
		if _, ok := err.(*commandError); ok {
			return nil, err
		}
		return nil, userError("não foi possível baixar " + label + ": " + err.Error())
	}
	if len(content) > limit {
		return nil, userError(label + " excede o limite seguro de tamanho")
	}
	return content, nil
}

func resolveUpdateSkillsRoot(value string) (string, error) {
	if value == "" {
		value = defaultUpdateSkillsRoot()
	}
	abs, err := filepath.Abs(value)
	if err != nil {
		return "", userError("raiz de skills não encontrada ou insegura: " + value)
	}
	info, err := os.Lstat(abs)
	if err != nil || info.Mode()&os.ModeSymlink != 0 || !info.IsDir() {
		return "", userError("raiz de skills não encontrada ou insegura: " + abs)
	}
	resolved, err := filepath.EvalSymlinks(abs)
	if err != nil {
		return "", userError("raiz de skills não encontrada ou insegura: " + abs)
	}
	return resolved, nil
}

func defaultUpdateSkillsRoot() string {
	if cwd, err := os.Getwd(); err == nil {
		candidate := filepath.Join(cwd, "skills")
		if info, statErr := os.Lstat(candidate); statErr == nil && info.IsDir() && info.Mode()&os.ModeSymlink == 0 {
			return candidate
		}
	}
	if executable, err := os.Executable(); err == nil {
		candidate := filepath.Clean(filepath.Join(filepath.Dir(executable), "..", ".."))
		if info, statErr := os.Lstat(filepath.Join(candidate, "_shared", "VERSION")); statErr == nil && info.Mode().IsRegular() {
			return candidate
		}
	}
	return filepath.Join(".", "skills")
}

func readInstalledUpdateVersion(root string) (string, error) {
	path := filepath.Join(root, "_shared", "VERSION")
	info, err := os.Lstat(path)
	if err != nil || info.Mode()&os.ModeSymlink != 0 || !info.Mode().IsRegular() {
		return "0.0.0", nil
	}
	content, err := os.ReadFile(path)
	if err != nil || !validUTF8Text(content) {
		return "", userError("não foi possível ler a versão instalada")
	}
	if len(content) > maxUpdateVersionBytes {
		return "", userError("não foi possível ler a versão instalada: arquivo excede limite seguro")
	}
	value := strings.TrimSpace(string(content))
	if _, err := parseUpdateVersion(value); err != nil {
		return "", err
	}
	return value, nil
}

func updateBaseResult(installed, latest, root, mode, status string, updated bool, backup string) map[string]any {
	var backupValue any
	if backup != "" {
		backupValue = backup
	}
	return map[string]any{
		"installed_version": installed, "latest_version": latest, "status": status,
		"updated": updated, "mode": mode, "skills_root": root, "backup": backupValue,
		"repository": officialUpdateRepository, "branch": officialUpdateBranch,
	}
}

func renderUpdateResult(result map[string]any) string {
	installed, latest, status := stateString(result["installed_version"]), stateString(result["latest_version"]), stateString(result["status"])
	switch status {
	case "up_to_date":
		return "Bianchini Method já está atualizado na versão " + installed + ".\n"
	case "ahead":
		return "Versão instalada " + installed + " é mais nova que a versão oficial " + latest + "; nenhuma alteração foi feita.\n"
	case "update_available":
		return "Atualização disponível: " + installed + " -> " + latest + ".\n"
	case "updated":
		suffix := ""
		if backup := stateString(result["backup"]); backup != "" {
			suffix = " Backup: " + backup + "."
		}
		return "Bianchini Method atualizado: " + installed + " -> " + latest + "." + suffix + "\n"
	default:
		return "Estado de atualização desconhecido: " + status + ".\n"
	}
}

func updateGitRoot(skillsRoot string) string {
	output, err := runUpdateGit(skillsRoot, false, "rev-parse", "--show-toplevel")
	if err != nil {
		return ""
	}
	root, err := filepath.EvalSymlinks(strings.TrimSpace(output))
	if err != nil {
		return ""
	}
	expected, err := filepath.EvalSymlinks(filepath.Join(root, "skills"))
	if err != nil || filepath.Clean(expected) != filepath.Clean(skillsRoot) {
		return ""
	}
	return root
}

func runUpdateGit(repo string, checked bool, args ...string) (string, error) {
	command := exec.Command("git", args...)
	command.Dir = repo
	output, err := command.CombinedOutput()
	if err != nil {
		if checked {
			message := strings.TrimSpace(string(output))
			if message == "" {
				message = "comando Git falhou"
			}
			return "", updateError(message, 3)
		}
		return "", err
	}
	return strings.TrimSpace(string(output)), nil
}

func updateGitCheckout(repo, skillsRoot, installed, latest string, lineageManifest []byte) (map[string]any, error) {
	branch, err := runUpdateGit(repo, true, "branch", "--show-current")
	if err != nil {
		return nil, err
	}
	if branch != officialUpdateBranch {
		if branch == "" {
			branch = "detached"
		}
		return nil, updateError("checkout Git deve estar na branch main; atual: "+branch, 3)
	}
	dirty, err := runUpdateGit(repo, true, "status", "--porcelain=v1", "--untracked-files=all")
	if err != nil {
		return nil, err
	}
	if dirty != "" {
		return nil, updateError("checkout Git possui alterações locais; commit ou guarde antes de atualizar", 3)
	}
	if err := verifyOfficialUpdateOrigin(repo); err != nil {
		return nil, err
	}
	if _, err := runUpdateGit(repo, true, "fetch", "origin", officialUpdateBranch); err != nil {
		return nil, err
	}
	remoteVersion, err := runUpdateGit(repo, true, "show", "origin/main:skills/_shared/VERSION")
	if err != nil {
		return nil, err
	}
	if _, err := parseUpdateVersion(remoteVersion); err != nil {
		return nil, err
	}
	if remoteVersion != latest {
		return nil, updateError("origin/main não corresponde à versão oficial consultada; atualização recusada", 3)
	}
	if lineageManifest != nil {
		remoteManifest, err := runUpdateGitRaw(repo, "show", "origin/main:skills/"+lineageResetManifest)
		if err != nil {
			return nil, updateError("origin/main não contém o manifesto de reset versionado", 3)
		}
		if !bytes.Equal(remoteManifest, lineageManifest) {
			return nil, updateError("manifesto de reset do origin/main diverge da fonte oficial consultada", 3)
		}
	}
	if _, err := runUpdateGit(repo, true, "merge", "--ff-only", "origin/main"); err != nil {
		return nil, err
	}
	finalVersion, err := readInstalledUpdateVersion(skillsRoot)
	if err != nil {
		return nil, err
	}
	if finalVersion != latest {
		return nil, updateError("Git atualizou, mas a versão final é "+finalVersion+"; esperado "+latest, 3)
	}
	return updateBaseResult(installed, latest, skillsRoot, "git_checkout", "updated", true, ""), nil
}

func runUpdateGitRaw(repo string, args ...string) ([]byte, error) {
	command := exec.Command("git", args...)
	command.Dir = repo
	output, err := command.Output()
	if err != nil {
		return nil, err
	}
	return output, nil
}

func verifyGitLineageSource(repo string) error {
	branch, err := runUpdateGit(repo, true, "branch", "--show-current")
	if err != nil {
		return err
	}
	if branch != officialUpdateBranch {
		if branch == "" {
			branch = "detached"
		}
		return updateError("reset de linhagem exige checkout na branch main; atual: "+branch, 3)
	}
	return verifyOfficialUpdateOrigin(repo)
}

func verifyOfficialUpdateOrigin(repo string) error {
	remote, err := runUpdateGit(repo, true, "config", "--get", "remote.origin.url")
	if err != nil {
		return err
	}
	if normalizeGitHubRepository(remote) != strings.ToLower(officialUpdateRepository) {
		if remote == "" {
			remote = "<ausente>"
		}
		return updateError("origin não aponta para o repositório oficial "+officialUpdateRepository+": "+remote, 3)
	}
	return nil
}

func normalizeGitHubRepository(value string) string {
	patterns := []*regexp.Regexp{
		regexp.MustCompile(`(?i)^https://github\.com/([^/]+/[^/]+?)(?:\.git)?/?$`),
		regexp.MustCompile(`(?i)^git@github\.com:([^/]+/[^/]+?)(?:\.git)?$`),
		regexp.MustCompile(`(?i)^ssh://git@github\.com/([^/]+/[^/]+?)(?:\.git)?/?$`),
	}
	for _, pattern := range patterns {
		if match := pattern.FindStringSubmatch(strings.TrimSpace(value)); len(match) == 2 {
			return strings.ToLower(strings.TrimSuffix(match[1], ".git"))
		}
	}
	return ""
}

type lineageResetDocument struct {
	SchemaVersion  int    `json:"schema_version"`
	ReleaseVersion string `json:"release_version"`
	LineageReset   struct {
		Authorized        bool   `json:"authorized"`
		FromMajorVersions []int  `json:"from_major_versions"`
		ToVersion         string `json:"to_version"`
	} `json:"lineage_reset"`
}

func validateLineageManifest(content []byte, installed, latest string) error {
	decoder := json.NewDecoder(bytes.NewReader(content))
	decoder.DisallowUnknownFields()
	var document lineageResetDocument
	if err := decoder.Decode(&document); err != nil {
		return userError("manifesto de reset inválido: " + err.Error())
	}
	if err := decoder.Decode(&struct{}{}); err != io.EOF {
		return userError("manifesto de reset possui estrutura inválida")
	}
	if document.SchemaVersion != 1 || document.ReleaseVersion != lineageResetVersion || latest != lineageResetVersion {
		return userError("manifesto de reset diverge da release 0.4.0")
	}
	reset := document.LineageReset
	if !reset.Authorized {
		return userError("manifesto de reset não autoriza a transição")
	}
	if reset.ToVersion != lineageResetVersion {
		return userError("manifesto de reset autoriza destino diferente de 0.4.0")
	}
	if len(reset.FromMajorVersions) == 0 || !sort.IntsAreSorted(reset.FromMajorVersions) {
		return userError("manifesto de reset possui linhagens de origem inválidas")
	}
	seen := map[int]bool{}
	for _, major := range reset.FromMajorVersions {
		if major <= 0 || seen[major] {
			return userError("manifesto de reset possui linhagens de origem inválidas")
		}
		seen[major] = true
	}
	installedVersion, err := parseUpdateVersion(installed)
	if err != nil {
		return err
	}
	if !seen[installedVersion.major] {
		return userError("manifesto de reset não autoriza a linhagem instalada " + installed)
	}
	return nil
}

func updateError(message string, code int) error {
	return &commandError{message: message, exitCode: code}
}
