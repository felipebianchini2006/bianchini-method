package gokernel

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

type updateTransactionMove struct {
	Name         string `json:"name"`
	HadOld       bool   `json:"had_old"`
	OldDigest    string `json:"old_digest,omitempty"`
	StagedDigest string `json:"staged_digest"`
}

type updateTransaction struct {
	SchemaVersion int                     `json:"schema_version"`
	SkillsRoot    string                  `json:"skills_root"`
	Stage         string                  `json:"stage"`
	Backup        string                  `json:"backup"`
	Committed     bool                    `json:"committed"`
	Moves         []updateTransactionMove `json:"moves"`
}

func updateJournalPath(skillsRoot string) string {
	return filepath.Join(filepath.Dir(skillsRoot), ".bianchini-method-update.json")
}

func updateLockPath(skillsRoot string) string {
	digest := sha256Bytes([]byte(filepath.Clean(skillsRoot)))
	return filepath.Join(filepath.Dir(filepath.Dir(skillsRoot)), ".bianchini-method-update-"+digest[:16]+".lock")
}

func withUpdateLock(skillsRoot string, action func() (map[string]any, error)) (map[string]any, error) {
	path := updateLockPath(skillsRoot)
	if info, err := os.Lstat(path); err == nil && info.Mode()&os.ModeSymlink != 0 {
		return nil, updateError("lock de atualização não pode ser symlink", 3)
	}
	file, err := os.OpenFile(path, os.O_RDWR|os.O_CREATE, 0o600)
	if err != nil {
		return nil, updateError("não foi possível abrir lock de atualização", 3)
	}
	defer file.Close()
	if err := lockCloseFile(file); err != nil {
		return nil, updateError("outra atualização está em execução", 3)
	}
	defer unlockCloseFile(file)
	return action()
}

func newUpdateTransaction(skillsRoot, stage, backup string) (updateTransaction, error) {
	transaction := updateTransaction{SchemaVersion: 1, SkillsRoot: skillsRoot, Stage: stage, Backup: backup, Moves: []updateTransactionMove{}}
	for _, name := range managedSkillDirectories {
		stagedDigest, err := updateTreeDigest(filepath.Join(stage, name))
		if err != nil {
			return updateTransaction{}, err
		}
		move := updateTransactionMove{Name: name, StagedDigest: stagedDigest}
		old := filepath.Join(skillsRoot, name)
		if info, statErr := os.Lstat(old); statErr == nil {
			if info.Mode()&os.ModeSymlink != 0 || !info.IsDir() {
				return updateTransaction{}, userError("target gerenciado não é diretório regular: " + old)
			}
			move.HadOld = true
			move.OldDigest, err = updateTreeDigest(old)
			if err != nil {
				return updateTransaction{}, err
			}
		} else if !os.IsNotExist(statErr) {
			return updateTransaction{}, statErr
		}
		transaction.Moves = append(transaction.Moves, move)
	}
	return transaction, nil
}

func writeUpdateJournal(transaction updateTransaction) error {
	return writeUpdateJournalWithSync(transaction, syncDirectory)
}

func writeUpdateJournalWithSync(transaction updateTransaction, syncDir directorySync) error {
	content, err := json.MarshalIndent(transaction, "", "  ")
	if err != nil {
		return err
	}
	path := updateJournalPath(transaction.SkillsRoot)
	if info, statErr := os.Lstat(path); statErr == nil && info.Mode()&os.ModeSymlink != 0 {
		return userError("journal de atualização não pode ser symlink")
	}
	temporary, err := os.CreateTemp(filepath.Dir(path), ".bianchini-method-update.*.part")
	if err != nil {
		return err
	}
	temporaryPath := temporary.Name()
	defer os.Remove(temporaryPath)
	if err := temporary.Chmod(0o600); err != nil {
		temporary.Close()
		return err
	}
	if _, err := temporary.Write(append(content, '\n')); err != nil {
		temporary.Close()
		return err
	}
	if err := temporary.Sync(); err != nil {
		temporary.Close()
		return err
	}
	if err := temporary.Close(); err != nil {
		return err
	}
	if err := os.Rename(temporaryPath, path); err != nil {
		return err
	}
	return syncDir(filepath.Dir(path))
}

func readUpdateJournal(skillsRoot string) (*updateTransaction, error) {
	path := updateJournalPath(skillsRoot)
	info, err := os.Lstat(path)
	if os.IsNotExist(err) {
		return nil, nil
	}
	if err != nil || info.Mode()&os.ModeSymlink != 0 || !info.Mode().IsRegular() {
		return nil, updateError("journal de atualização inválido", 3)
	}
	content, err := os.ReadFile(path)
	if err != nil {
		return nil, updateError("journal de atualização inválido", 3)
	}
	decoder := json.NewDecoder(bytes.NewReader(content))
	decoder.DisallowUnknownFields()
	var transaction updateTransaction
	if err := decoder.Decode(&transaction); err != nil {
		return nil, updateError("journal de atualização inválido", 3)
	}
	if err := decoder.Decode(&struct{}{}); err != io.EOF {
		return nil, updateError("journal de atualização inválido", 3)
	}
	if err := validateUpdateTransaction(skillsRoot, transaction); err != nil {
		return nil, err
	}
	return &transaction, nil
}

func validateUpdateTransaction(skillsRoot string, transaction updateTransaction) error {
	parent := filepath.Dir(skillsRoot)
	if transaction.SchemaVersion != 1 || filepath.Clean(transaction.SkillsRoot) != filepath.Clean(skillsRoot) || len(transaction.Moves) != len(managedSkillDirectories) {
		return updateError("journal de atualização não corresponde à instalação", 3)
	}
	for value, prefix := range map[string]string{transaction.Stage: ".bianchini-method-stage.", transaction.Backup: ""} {
		relative, err := filepath.Rel(parent, value)
		if err != nil || relative == ".." || strings.HasPrefix(relative, ".."+string(filepath.Separator)) || filepath.IsAbs(relative) {
			return updateError("journal de atualização contém path inseguro", 3)
		}
		if prefix != "" && !strings.HasPrefix(filepath.Base(value), prefix) {
			return updateError("journal de atualização contém stage inválido", 3)
		}
	}
	expectedBackupRoot := filepath.Join(parent, ".bianchini-method-backups")
	backupRelative, err := filepath.Rel(expectedBackupRoot, transaction.Backup)
	if err != nil || backupRelative == ".." || strings.HasPrefix(backupRelative, ".."+string(filepath.Separator)) || filepath.IsAbs(backupRelative) {
		return updateError("journal de atualização contém backup inválido", 3)
	}
	seen := map[string]bool{}
	for _, move := range transaction.Moves {
		if seen[move.Name] || !stringSet(managedSkillDirectories)[move.Name] || !updateReleaseDigest.MatchString(move.StagedDigest) || move.HadOld != (move.OldDigest != "") || move.OldDigest != "" && !updateReleaseDigest.MatchString(move.OldDigest) {
			return updateError("journal de atualização contém movimento inválido", 3)
		}
		seen[move.Name] = true
	}
	return nil
}

const (
	updateRecoveryNone       = "none"
	updateRecoveryCommitted  = "committed"
	updateRecoveryRolledBack = "rolled_back"
)

func recoverUpdateTransaction(skillsRoot string, fsops updateFS) error {
	_, err := recoverUpdateTransactionOutcome(skillsRoot, fsops)
	return err
}

func recoverUpdateTransactionOutcome(skillsRoot string, fsops updateFS) (string, error) {
	transaction, err := readUpdateJournal(skillsRoot)
	if err != nil || transaction == nil {
		return updateRecoveryNone, err
	}
	if transaction.Committed {
		problems := []string{}
		for _, move := range transaction.Moves {
			target := filepath.Join(skillsRoot, move.Name)
			digest, present, digestErr := updateTreeDigestIfPresent(target)
			if digestErr != nil || !present || digest != move.StagedDigest {
				problems = append(problems, move.Name+": target committed divergiu")
			}
		}
		if len(problems) > 0 {
			return updateRecoveryCommitted, updateError("commit de atualização não pôde ser confirmado; cópias preservadas: "+strings.Join(problems, "; "), 3)
		}
		if err := fsops.removeAll(transaction.Stage); err != nil {
			return updateRecoveryCommitted, updateError("commit confirmado, mas stage foi preservado: "+err.Error(), 3)
		}
		if err := durableRemoveFile(updateJournalPath(skillsRoot)); err != nil {
			return updateRecoveryCommitted, updateError("atualização concluída, mas journal não pôde ser removido", 3)
		}
		return updateRecoveryCommitted, nil
	}
	problems := []string{}
	for index := len(transaction.Moves) - 1; index >= 0; index-- {
		move := transaction.Moves[index]
		target := filepath.Join(skillsRoot, move.Name)
		backup := filepath.Join(transaction.Backup, move.Name)
		stage := filepath.Join(transaction.Stage, move.Name)
		targetDigest, targetExists, targetErr := updateTreeDigestIfPresent(target)
		backupDigest, backupExists, backupErr := updateTreeDigestIfPresent(backup)
		stageDigest, stageExists, stageErr := updateTreeDigestIfPresent(stage)
		if targetErr != nil || backupErr != nil || stageErr != nil {
			problems = append(problems, move.Name+": árvore inválida")
			continue
		}
		if move.HadOld {
			switch {
			case backupExists && backupDigest == move.OldDigest:
				if targetExists && targetDigest != move.StagedDigest && targetDigest != move.OldDigest {
					problems = append(problems, move.Name+": target divergiu")
					continue
				}
				if targetExists {
					if err := fsops.removeAll(target); err != nil {
						problems = append(problems, move.Name+": "+err.Error())
						continue
					}
				}
				if err := fsops.rename(backup, target); err != nil {
					problems = append(problems, move.Name+": "+err.Error())
				}
			case !backupExists && targetExists && targetDigest == move.OldDigest:
				// O swap deste diretório ainda não começou.
			default:
				problems = append(problems, move.Name+": cópia anterior não recuperável com segurança")
			}
		} else {
			if backupExists {
				problems = append(problems, move.Name+": backup inesperado")
				continue
			}
			if targetExists {
				if targetDigest != move.StagedDigest || stageExists && stageDigest == move.StagedDigest {
					problems = append(problems, move.Name+": target novo ambíguo")
					continue
				}
				if err := fsops.removeAll(target); err != nil {
					problems = append(problems, move.Name+": "+err.Error())
				}
			}
		}
	}
	if len(problems) > 0 {
		return updateRecoveryRolledBack, updateError("rollback incompleto; cópias preservadas: "+strings.Join(problems, "; "), 3)
	}
	if err := fsops.removeAll(transaction.Stage); err != nil {
		return updateRecoveryRolledBack, updateError("rollback restaurou a instalação, mas stage foi preservado: "+err.Error(), 3)
	}
	if err := durableRemoveFile(updateJournalPath(skillsRoot)); err != nil {
		return updateRecoveryRolledBack, updateError("rollback restaurou a instalação, mas journal foi preservado", 3)
	}
	return updateRecoveryRolledBack, nil
}

func updateTreeDigestIfPresent(path string) (string, bool, error) {
	if _, err := os.Lstat(path); os.IsNotExist(err) {
		return "", false, nil
	}
	digest, err := updateTreeDigest(path)
	return digest, err == nil, err
}

func updateTreeDigest(root string) (string, error) {
	info, err := os.Lstat(root)
	if err != nil || info.Mode()&os.ModeSymlink != 0 || !info.IsDir() {
		return "", userError("árvore de atualização inválida: " + root)
	}
	entries := []string{}
	err = filepath.WalkDir(root, func(path string, entry os.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		info, statErr := os.Lstat(path)
		if statErr != nil || info.Mode()&os.ModeSymlink != 0 {
			return userError("árvore de atualização contém symlink: " + path)
		}
		relative, _ := filepath.Rel(root, path)
		if relative == "." {
			return nil
		}
		if strings.EqualFold(entry.Name(), ".planning") {
			return userError("árvore de atualização contém namespace estrangeiro")
		}
		if info.IsDir() {
			entries = append(entries, "D\x00"+filepath.ToSlash(relative)+"\x00"+fmt.Sprintf("%o", info.Mode().Perm())+"\n")
			return nil
		}
		if !info.Mode().IsRegular() {
			return userError("árvore de atualização contém entrada não regular: " + path)
		}
		content, readErr := os.ReadFile(path)
		if readErr != nil {
			return readErr
		}
		entries = append(entries, "F\x00"+filepath.ToSlash(relative)+"\x00"+fmt.Sprintf("%o", info.Mode().Perm())+"\x00"+sha256Bytes(content)+"\n")
		return nil
	})
	if err != nil {
		return "", err
	}
	sort.Strings(entries)
	return sha256Bytes([]byte(strings.Join(entries, ""))), nil
}
