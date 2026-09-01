package gokernel

import (
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"
)

type updateFS struct {
	rename    func(string, string) error
	removeAll func(string) error
}

type updateCompletedMove struct {
	name   string
	hadOld bool
}

func defaultUpdateFS() updateFS {
	return updateFS{rename: os.Rename, removeAll: os.RemoveAll}
}

func installSkillsAtomically(skillsRoot, remoteSkills, installed string, fsops updateFS) (string, error) {
	info, err := os.Lstat(skillsRoot)
	if err != nil || info.Mode()&os.ModeSymlink != 0 || !info.IsDir() {
		return "", userError("raiz de skills deve ser diretório regular: " + skillsRoot)
	}
	stage, err := os.MkdirTemp(filepath.Dir(skillsRoot), ".bianchini-method-stage.*")
	if err != nil {
		return "", userError("não foi possível preparar stage: " + err.Error())
	}
	journalCreated := false
	defer func() {
		if !journalCreated {
			_ = fsops.removeAll(stage)
		}
	}()
	backup, err := uniqueUpdateBackup(skillsRoot, installed)
	if err != nil {
		return "", err
	}
	for _, name := range managedSkillDirectories {
		if err := copyUpdateTree(filepath.Join(remoteSkills, name), filepath.Join(stage, name)); err != nil {
			return "", err
		}
	}
	transaction, err := newUpdateTransaction(skillsRoot, stage, backup)
	if err != nil {
		return "", err
	}
	if err := writeUpdateJournal(transaction); err != nil {
		return "", err
	}
	journalCreated = true
	fail := func(cause error) (string, error) {
		if recoveryErr := recoverUpdateTransaction(skillsRoot, fsops); recoveryErr != nil {
			return "", updateError("falha na atualização; "+recoveryErr.Error()+"; causa: "+cause.Error(), 3)
		}
		journalCreated = false
		return "", updateError("falha na atualização; rollback concluído; causa: "+cause.Error(), 3)
	}
	for _, move := range transaction.Moves {
		name := move.Name
		target := filepath.Join(skillsRoot, name)
		if move.HadOld {
			if err := fsops.rename(target, filepath.Join(backup, name)); err != nil {
				return fail(err)
			}
		}
		if err := fsops.rename(filepath.Join(stage, name), target); err != nil {
			return fail(err)
		}
	}
	transaction.Committed = true
	if err := writeUpdateJournal(transaction); err != nil {
		return fail(err)
	}
	if err := fsops.removeAll(stage); err != nil {
		return "", updateError("atualização concluída, mas stage não pôde ser removido: "+err.Error(), 3)
	}
	if err := os.Remove(updateJournalPath(skillsRoot)); err != nil && !os.IsNotExist(err) {
		return "", updateError("atualização concluída, mas journal foi preservado", 3)
	}
	journalCreated = false
	pruneUpdateBackups(backup, fsops, 3)
	return backup, nil
}

func rollbackUpdateFailure(skillsRoot, backup string, completed []updateCompletedMove, currentName string, currentOldMoved bool, fsops updateFS, cause error) error {
	errors := make([]string, 0)
	if currentName != "" && currentOldMoved {
		target := filepath.Join(skillsRoot, currentName)
		if _, err := os.Lstat(target); err == nil {
			if err := fsops.removeAll(target); err != nil {
				errors = append(errors, currentName+": "+err.Error())
			}
		}
		if err := fsops.rename(filepath.Join(backup, currentName), target); err != nil {
			errors = append(errors, currentName+": "+err.Error())
		}
	}
	for index := len(completed) - 1; index >= 0; index-- {
		item := completed[index]
		target := filepath.Join(skillsRoot, item.name)
		if _, err := os.Lstat(target); err == nil {
			if err := fsops.removeAll(target); err != nil {
				errors = append(errors, item.name+": "+err.Error())
				continue
			}
		}
		if item.hadOld {
			if err := fsops.rename(filepath.Join(backup, item.name), target); err != nil {
				errors = append(errors, item.name+": "+err.Error())
			}
		}
	}
	detail := "rollback concluído"
	if len(errors) > 0 {
		detail = "rollback incompleto: " + strings.Join(errors, "; ")
	}
	return updateError("falha na atualização; "+detail+"; causa: "+cause.Error(), 3)
}

func copyUpdateTree(source, destination string) error {
	if err := rejectUpdateTreeLinks(source, "pacote"); err != nil {
		return err
	}
	return filepath.WalkDir(source, func(path string, entry fs.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		relative, err := filepath.Rel(source, path)
		if err != nil {
			return err
		}
		target := filepath.Join(destination, relative)
		info, err := entry.Info()
		if err != nil {
			return err
		}
		if entry.IsDir() {
			return os.MkdirAll(target, info.Mode().Perm())
		}
		content, err := os.ReadFile(path)
		if err != nil {
			return err
		}
		if err := os.WriteFile(target, content, info.Mode().Perm()); err != nil {
			return err
		}
		return nil
	})
}

func uniqueUpdateBackup(skillsRoot, installed string) (string, error) {
	backupRoot := filepath.Join(filepath.Dir(skillsRoot), ".bianchini-method-backups")
	if info, err := os.Lstat(backupRoot); err == nil && info.Mode()&os.ModeSymlink != 0 {
		return "", userError("diretório de backup não pode ser symlink: " + backupRoot)
	}
	if err := os.MkdirAll(backupRoot, 0o755); err != nil {
		return "", userError("não foi possível criar backup: " + err.Error())
	}
	stamp := time.Now().UTC().Format("20060102T150405Z")
	base := filepath.Join(backupRoot, fmt.Sprintf("%s-v%s", stamp, installed))
	candidate := base
	for suffix := 1; ; suffix++ {
		if _, err := os.Lstat(candidate); os.IsNotExist(err) {
			break
		}
		candidate = fmt.Sprintf("%s-%d", base, suffix)
	}
	if err := os.Mkdir(candidate, 0o755); err != nil {
		return "", userError("não foi possível criar backup: " + err.Error())
	}
	return candidate, nil
}

func pruneUpdateBackups(backup string, fsops updateFS, keep int) {
	entries, err := os.ReadDir(filepath.Dir(backup))
	if err != nil {
		return
	}
	names := make([]string, 0)
	for _, entry := range entries {
		if entry.IsDir() && entry.Type()&os.ModeSymlink == 0 {
			names = append(names, entry.Name())
		}
	}
	sort.Sort(sort.Reverse(sort.StringSlice(names)))
	for _, name := range names[minimumInt(keep, len(names)):] {
		_ = fsops.removeAll(filepath.Join(filepath.Dir(backup), name))
	}
}

func minimumInt(left, right int) int {
	if left < right {
		return left
	}
	return right
}
