package gokernel

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strings"
	"time"
)

type migrationEntry struct {
	Source string `json:"source"`
	Target string `json:"target"`
	SHA256 string `json:"sha256"`
}

type migrationCopyPair struct{ source, target string }

var errMigrationRollbackIncomplete = errors.New("rollback incompleto")

func runMigrate(args []string) (any, error) {
	if len(args) == 0 {
		return nil, argparseError("the following arguments are required: action")
	}
	action := args[0]
	if !oneOf(action, "check", "apply") {
		return nil, argparseError(fmt.Sprintf("argument action: invalid choice: '%s'", action))
	}
	flags, err := parseFlags(args[1:], map[string]bool{"--repo": true}, map[string]bool{})
	if err != nil {
		return nil, err
	}
	repo := lastValue(flags, "--repo")
	if repo == "" {
		repo, err = os.Getwd()
		if err != nil {
			return nil, workflowError("DIRTY_WORKSPACE", "o diretório não é uma raiz Git")
		}
	}
	if action == "check" {
		return migrationCheck(repo)
	}
	return migrationApply(repo)
}

func migrationCheck(repo string) (map[string]any, error) {
	root, err := repositoryRoot(repo)
	if err != nil {
		return nil, err
	}
	workspace := newMethodWorkspace(root)
	if _, statErr := os.Lstat(workspace.dir); statErr == nil {
		return nil, workflowError("MIGRATION_REQUIRED", ".bianchini já existe")
	} else if !os.IsNotExist(statErr) {
		return nil, workflowError("MIGRATION_REQUIRED", statErr.Error())
	}
	command := exec.Command("git", "status", "--porcelain")
	command.Dir = root
	output, commandErr := command.CombinedOutput()
	if commandErr != nil {
		return nil, workflowError("DIRTY_WORKSPACE", strings.TrimSpace(string(output)))
	}
	if strings.TrimSpace(string(output)) != "" {
		return nil, workflowError("DIRTY_WORKSPACE", "migração exige Git limpo")
	}
	if err := migrationValidateKnownRoots(root); err != nil {
		return nil, err
	}
	idle, err := legacyMigrationIdle(root)
	if err != nil {
		return nil, err
	}
	if !idle {
		return nil, workflowError("MIGRATION_REQUIRED", "o trabalho anterior precisa estar idle ou concluído")
	}

	archive := filepath.ToSlash(filepath.Join(".bianchini", "archive", "import-"+time.Now().UTC().Format("2006-01-02")))
	entries := make([]migrationEntry, 0)
	seen := map[string]bool{}
	add := func(source, target string) error {
		if pathErr := migrationValidatePath(root, source, true); pathErr != nil {
			return pathErr
		}
		info, statErr := os.Lstat(source)
		if os.IsNotExist(statErr) {
			return nil
		}
		if statErr != nil || info.Mode()&os.ModeSymlink != 0 || !info.Mode().IsRegular() {
			return nil
		}
		relative, relErr := filepath.Rel(root, source)
		if relErr != nil {
			return workflowError("MIGRATION_REQUIRED", relErr.Error())
		}
		relative = filepath.ToSlash(relative)
		if seen[relative] {
			return nil
		}
		content, readErr := os.ReadFile(source)
		if readErr != nil {
			return workflowError("MIGRATION_REQUIRED", readErr.Error())
		}
		seen[relative] = true
		entries = append(entries, migrationEntry{Source: relative, Target: filepath.ToSlash(target), SHA256: sha256Bytes(content)})
		return nil
	}

	if err := add(filepath.Join(root, "docs", "living", "PROJECT_STATE.md"), filepath.Join(archive, "legacy", "PROJECT_STATE.md")); err != nil {
		return nil, err
	}
	specRoot := filepath.Join(root, "docs", "bianchini", "current", "specs")
	specFiles, err := migrationKnownFiles(root, specRoot)
	if err != nil {
		return nil, err
	}
	for _, source := range specFiles {
		relative, _ := filepath.Rel(specRoot, source)
		if err := add(source, filepath.Join(".bianchini", "current", "specs", relative)); err != nil {
			return nil, err
		}
	}
	for _, pair := range []struct {
		Source string
		Target string
	}{
		{filepath.Join(root, "docs", "bianchini"), filepath.Join(archive, "docs-bianchini")},
		{filepath.Join(root, "artifacts", "bianchini"), filepath.Join(archive, "artifacts-bianchini")},
	} {
		files, walkErr := migrationKnownFiles(root, pair.Source)
		if walkErr != nil {
			return nil, walkErr
		}
		for _, source := range files {
			relative, _ := filepath.Rel(pair.Source, source)
			if err := add(source, filepath.Join(pair.Target, relative)); err != nil {
				return nil, err
			}
		}
	}
	designFiles, err := migrationDesignFiles(root, filepath.Join(root, "docs", "design"))
	if err != nil {
		return nil, err
	}
	for _, source := range designFiles {
		relative, _ := filepath.Rel(filepath.Join(root, "docs", "design"), source)
		if err := add(source, filepath.Join(archive, "docs-design", relative)); err != nil {
			return nil, err
		}
	}
	directRoot := filepath.Join(root, ".superpowers", "bianchini", "direct")
	directFiles, err := migrationKnownFiles(root, directRoot)
	if err != nil {
		return nil, err
	}
	for _, source := range directFiles {
		relative, _ := filepath.Rel(directRoot, source)
		if err := add(source, filepath.Join(".bianchini", "quick", "imported", relative)); err != nil {
			return nil, err
		}
	}
	if len(entries) == 0 {
		return nil, workflowError("MIGRATION_REQUIRED", "nenhum artefato Bianchini anterior encontrado")
	}
	targets := map[string]bool{}
	for _, entry := range entries {
		if targets[entry.Target] {
			return nil, workflowError("MIGRATION_REQUIRED", "colisão no mapa de migração")
		}
		targets[entry.Target] = true
		if _, statErr := os.Lstat(filepath.Join(root, filepath.FromSlash(entry.Target))); statErr == nil {
			return nil, workflowError("MIGRATION_REQUIRED", "destino já existe: "+entry.Target)
		} else if !os.IsNotExist(statErr) {
			return nil, workflowError("MIGRATION_REQUIRED", statErr.Error())
		}
	}
	return map[string]any{"eligible": true, "entries": migrationEntriesAny(entries), "archive": archive}, nil
}

func migrationApply(repo string) (map[string]any, error) {
	root, err := repositoryRoot(repo)
	if err != nil {
		return nil, err
	}
	report, err := migrationCheck(root)
	if err != nil {
		return nil, err
	}
	entries := migrationEntriesFromAny(stateArray(report["entries"]))
	workspace := newMethodWorkspace(root)
	copied := make([]migrationCopyPair, 0, len(entries))
	removed := make([]migrationCopyPair, 0, len(entries))
	rollback := func(cause string) error {
		rollbackErr := rollbackMigration(workspace.dir, removed)
		if rollbackErr != nil {
			return workflowError("MIGRATION_REQUIRED", cause+"; "+rollbackErr.Error())
		}
		return workflowError("MIGRATION_REQUIRED", cause+"; rollback concluído")
	}
	for _, entry := range entries {
		source := filepath.Join(root, filepath.FromSlash(entry.Source))
		target := filepath.Join(root, filepath.FromSlash(entry.Target))
		if pathErr := migrationValidatePath(root, source, false); pathErr != nil {
			return nil, rollback(pathErr.Error())
		}
		content, readErr := os.ReadFile(source)
		if readErr != nil || sha256Bytes(content) != entry.SHA256 {
			return nil, rollback("checksum divergente: " + entry.Source)
		}
		if err := os.MkdirAll(filepath.Dir(target), 0o755); err != nil {
			return nil, rollback(err.Error())
		}
		part := target + ".part"
		if _, statErr := os.Lstat(part); statErr == nil {
			return nil, rollback("staging já existe: " + part)
		}
		if err := copyMigrationFile(source, part); err != nil {
			return nil, rollback(err.Error())
		}
		partBytes, readErr := os.ReadFile(part)
		if readErr != nil || sha256Bytes(partBytes) != entry.SHA256 {
			_ = os.Remove(part)
			return nil, rollback("checksum do destino divergiu: " + entry.Target)
		}
		if err := os.Rename(part, target); err != nil {
			return nil, rollback(err.Error())
		}
		copied = append(copied, migrationCopyPair{source: source, target: target})
	}
	for _, pair := range copied {
		source, sourceErr := os.ReadFile(pair.source)
		target, targetErr := os.ReadFile(pair.target)
		if sourceErr != nil || targetErr != nil || sha256Bytes(source) != sha256Bytes(target) {
			return nil, rollback("verificação final divergiu: " + pair.target)
		}
	}
	for _, pair := range copied {
		if pathErr := migrationValidatePath(root, pair.source, false); pathErr != nil {
			return nil, rollback(pathErr.Error())
		}
		if err := os.Remove(pair.source); err != nil {
			return nil, rollback(err.Error())
		}
		removed = append(removed, pair)
	}
	removeEmptyLegacyDirectories(root)
	if err := workspace.initialize(); err != nil {
		return nil, rollback(err.Error())
	}
	state := workspace.initialState()
	state["last_completed"] = map[string]any{"kind": "migration", "id": stateString(report["archive"]), "status": "completed"}
	state["next_action"] = "Revisar o modelo atual e iniciar o próximo trabalho."
	state["updated_at"] = utcNow()
	if err := workspace.writeState(state, "# Estado atual"); err != nil {
		return nil, rollback(err.Error())
	}
	manifest := filepath.Join(root, filepath.FromSlash(stateString(report["archive"])), "MANIFEST.md")
	manifestValue := map[string]any{
		"schema_version": 1, "method": methodVersion04, "imported_at": utcNow(), "entries": migrationEntriesAny(entries),
	}
	document, documentErr := frontmatterDocument(manifestValue, "# Manifesto de migração\n\nArquivos anteriores preservados por checksum.", false)
	if documentErr != nil {
		return nil, rollback(documentErr.Error())
	}
	if err := workspace.atomicWrite(manifest, document); err != nil {
		return nil, rollback(err.Error())
	}
	return map[string]any{
		"status": "migrated", "entries": migrationEntriesAny(entries), "manifest": manifest, "state": workspace.state,
	}, nil
}

func legacyMigrationIdle(root string) (bool, error) {
	path := filepath.Join(root, "docs", "living", "PROJECT_STATE.md")
	if pathErr := migrationValidatePath(root, path, true); pathErr != nil {
		return false, pathErr
	}
	info, err := os.Lstat(path)
	if os.IsNotExist(err) {
		return true, nil
	}
	if err != nil || info.Mode()&os.ModeSymlink != 0 || !info.Mode().IsRegular() {
		return false, workflowError("MIGRATION_REQUIRED", "symlink não permitido: "+path)
	}
	content, err := os.ReadFile(path)
	if err != nil {
		return false, workflowError("MIGRATION_REQUIRED", err.Error())
	}
	value := map[string]any{}
	if json.Unmarshal(content, &value) == nil {
		for _, key := range []string{"status", "planning_status"} {
			if oneOf(strings.ToLower(stateString(value[key])), "idle", "completed", "done", "concluido") {
				return true, nil
			}
		}
		return false, nil
	}
	lowered := strings.ToLower(string(content))
	return strings.Contains(lowered, "status: idle") || strings.Contains(lowered, "status: completed"), nil
}

func migrationKnownFiles(root, directory string) ([]string, error) {
	if pathErr := migrationValidatePath(root, directory, true); pathErr != nil {
		return nil, pathErr
	}
	info, err := os.Lstat(directory)
	if os.IsNotExist(err) {
		return nil, nil
	}
	if err != nil || info.Mode()&os.ModeSymlink != 0 || !info.IsDir() {
		return nil, workflowError("MIGRATION_REQUIRED", "symlink não permitido: "+directory)
	}
	files := []string{}
	err = filepath.WalkDir(directory, func(path string, entry os.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if path == directory {
			return nil
		}
		if strings.EqualFold(entry.Name(), ".planning") {
			if entry.IsDir() {
				return filepath.SkipDir
			}
			return nil
		}
		if entry.Type()&os.ModeSymlink != 0 {
			return workflowError("MIGRATION_REQUIRED", "symlink não permitido: "+path)
		}
		if !entry.IsDir() {
			files = append(files, path)
		}
		return nil
	})
	if err != nil {
		return nil, err
	}
	sort.Strings(files)
	return files, nil
}

func migrationDesignFiles(root, directory string) ([]string, error) {
	if pathErr := migrationValidatePath(root, directory, true); pathErr != nil {
		return nil, pathErr
	}
	entries, err := os.ReadDir(directory)
	if os.IsNotExist(err) {
		return nil, nil
	}
	if err != nil {
		return nil, workflowError("MIGRATION_REQUIRED", err.Error())
	}
	files := []string{}
	for _, entry := range entries {
		if strings.EqualFold(entry.Name(), ".planning") {
			continue
		}
		path := filepath.Join(directory, entry.Name())
		if entry.Type()&os.ModeSymlink != 0 {
			return nil, workflowError("MIGRATION_REQUIRED", "symlink não permitido: "+path)
		}
		if !entry.IsDir() {
			continue
		}
		manifest := filepath.Join(path, "DESIGN_MANIFEST.json")
		info, statErr := os.Lstat(manifest)
		if statErr != nil || info.Mode()&os.ModeSymlink != 0 || !info.Mode().IsRegular() {
			continue
		}
		value, decodeErr := decodeJSONObjectFromFile(manifest)
		if decodeErr != nil || stateInt(value["schema_version"]) != 1 {
			continue
		}
		known, walkErr := migrationKnownFiles(root, path)
		if walkErr != nil {
			return nil, walkErr
		}
		// Mantém o manifesto por último como o oráculo Python nas fixtures congeladas.
		for _, candidate := range known {
			if candidate != manifest {
				files = append(files, candidate)
			}
		}
		files = append(files, manifest)
	}
	return files, nil
}

func migrationEntriesAny(entries []migrationEntry) []any {
	result := make([]any, 0, len(entries))
	for _, entry := range entries {
		result = append(result, map[string]any{"source": entry.Source, "target": entry.Target, "sha256": entry.SHA256})
	}
	return result
}

func migrationEntriesFromAny(values []any) []migrationEntry {
	result := make([]migrationEntry, 0, len(values))
	for _, value := range values {
		entry := stateObject(value)
		result = append(result, migrationEntry{Source: stateString(entry["source"]), Target: stateString(entry["target"]), SHA256: stateString(entry["sha256"])})
	}
	return result
}

func copyMigrationFile(source, target string) error {
	input, err := os.Open(source)
	if err != nil {
		return err
	}
	defer input.Close()
	info, err := input.Stat()
	if err != nil || info.Mode()&os.ModeSymlink != 0 || !info.Mode().IsRegular() {
		return fmt.Errorf("fonte insegura: %s", source)
	}
	output, err := os.OpenFile(target, os.O_WRONLY|os.O_CREATE|os.O_EXCL, info.Mode().Perm())
	if err != nil {
		return err
	}
	closed := false
	defer func() {
		if !closed {
			_ = output.Close()
		}
	}()
	if _, err := io.Copy(output, input); err != nil {
		return err
	}
	if err := output.Sync(); err != nil {
		return err
	}
	if err := output.Chmod(info.Mode()); err != nil {
		return err
	}
	if err := output.Close(); err != nil {
		return err
	}
	closed = true
	return nil
}

func removeEmptyLegacyDirectories(root string) {
	for _, relative := range []string{"docs/living", "docs/bianchini", "artifacts/bianchini", "docs/design", ".superpowers/bianchini/direct"} {
		directory := filepath.Join(root, filepath.FromSlash(relative))
		directories := []string{}
		_ = filepath.WalkDir(directory, func(path string, entry os.DirEntry, err error) error {
			if err == nil && path != directory && strings.EqualFold(entry.Name(), ".planning") && entry.IsDir() {
				return filepath.SkipDir
			}
			if err == nil && entry.IsDir() {
				directories = append(directories, path)
			}
			return nil
		})
		sort.Slice(directories, func(left, right int) bool {
			return len(directories[left]) > len(directories[right])
		})
		for _, current := range directories {
			_ = os.Remove(current)
		}
	}
}

func migrationValidateKnownRoots(root string) error {
	for _, relative := range []string{
		"docs", "docs/living", "docs/bianchini", "docs/design",
		"artifacts", "artifacts/bianchini", ".superpowers",
		".superpowers/bianchini", ".superpowers/bianchini/direct",
	} {
		if err := migrationValidatePath(root, filepath.Join(root, filepath.FromSlash(relative)), true); err != nil {
			return err
		}
	}
	return nil
}

func migrationValidatePath(root, path string, allowMissing bool) error {
	cleanRoot := filepath.Clean(root)
	cleanPath := filepath.Clean(path)
	relative, err := filepath.Rel(cleanRoot, cleanPath)
	if err != nil || relative == ".." || strings.HasPrefix(relative, ".."+string(filepath.Separator)) || filepath.IsAbs(relative) {
		return workflowError("MIGRATION_REQUIRED", "fonte fora da raiz: "+path)
	}
	if relative == "." {
		return nil
	}
	current := cleanRoot
	for _, component := range strings.Split(relative, string(filepath.Separator)) {
		if strings.EqualFold(component, ".planning") {
			return workflowError("MIGRATION_REQUIRED", "namespace estrangeiro não pode ser migrado")
		}
		current = filepath.Join(current, component)
		info, statErr := os.Lstat(current)
		if os.IsNotExist(statErr) && allowMissing {
			return nil
		}
		if statErr != nil {
			return workflowError("MIGRATION_REQUIRED", statErr.Error())
		}
		if info.Mode()&os.ModeSymlink != 0 {
			return workflowError("MIGRATION_REQUIRED", "symlink não permitido: "+current)
		}
	}
	return nil
}

func rollbackMigration(workspace string, removed []migrationCopyPair) error {
	problems := make([]string, 0)
	for index := len(removed) - 1; index >= 0; index-- {
		pair := removed[index]
		if _, sourceErr := os.Lstat(pair.source); os.IsNotExist(sourceErr) {
			if err := os.MkdirAll(filepath.Dir(pair.source), 0o755); err != nil {
				problems = append(problems, pair.source+": "+err.Error())
				continue
			}
			if err := copyMigrationFile(pair.target, pair.source); err != nil {
				problems = append(problems, pair.source+": "+err.Error())
				continue
			}
		} else if sourceErr != nil {
			problems = append(problems, pair.source+": "+sourceErr.Error())
			continue
		}
		sourceBytes, sourceErr := os.ReadFile(pair.source)
		targetBytes, targetErr := os.ReadFile(pair.target)
		sourceInfo, sourceStatErr := os.Stat(pair.source)
		targetInfo, targetStatErr := os.Stat(pair.target)
		if sourceErr != nil || targetErr != nil || sourceStatErr != nil || targetStatErr != nil ||
			sha256Bytes(sourceBytes) != sha256Bytes(targetBytes) || sourceInfo.Mode() != targetInfo.Mode() {
			problems = append(problems, pair.source+": restauração não verificada")
		}
	}
	if len(problems) > 0 {
		return fmt.Errorf("%w; cópias recuperáveis preservadas em %s; %s", errMigrationRollbackIncomplete, workspace, strings.Join(problems, "; "))
	}
	if err := os.RemoveAll(workspace); err != nil {
		return fmt.Errorf("%w; workspace preservado em %s: %v", errMigrationRollbackIncomplete, workspace, err)
	}
	return nil
}
