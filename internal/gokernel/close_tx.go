package gokernel

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"io/fs"
	"os"
	"path/filepath"
	"regexp"
	"strings"
)

var closeChangeID = regexp.MustCompile(`^C[0-9]{3}(?:-[a-z0-9]+(?:-[a-z0-9]+)*)?$`)

var closePhases = map[string]bool{
	"PREPARING": true, "PREPARED": true, "STAGED": true, "CURRENT_PROMOTED": true,
	"CHANGE_ARCHIVED": true, "STATE_COMMITTED": true, "DONE": true,
}

type closeCrash struct{ phase string }

func (crash closeCrash) Error() string { return "simulated crash after " + crash.phase }

type closeJournal struct {
	SchemaVersion int                          `json:"schema_version"`
	SpecContract  int                          `json:"spec_contract"`
	Change        string                       `json:"change"`
	Phase         string                       `json:"phase"`
	Paths         map[string]string            `json:"paths"`
	Digests       map[string]map[string]string `json:"digests"`
	Inputs        map[string]string            `json:"inputs"`
}

func closeError(code, message string) error { return workflowError(code, message) }

func closeJournalPath(root string) string {
	return filepath.Join(root, ".bianchini", ".runtime", "cycle-close.json")
}

func closeTransactionPath(root, change string) string {
	return filepath.Join(root, ".bianchini", ".runtime", "cycle-close-"+change)
}

func withCloseLock(root string, action func() (map[string]any, error)) (map[string]any, error) {
	workspace := filepath.Join(root, ".bianchini")
	info, err := os.Lstat(workspace)
	if err != nil || info.Mode()&os.ModeSymlink != 0 || !info.IsDir() {
		return nil, closeError("PATH_UNSAFE", "workspace .bianchini ausente ou inválido")
	}
	runtime := filepath.Join(workspace, ".runtime")
	if runtimeInfo, statErr := os.Lstat(runtime); statErr == nil && runtimeInfo.Mode()&os.ModeSymlink != 0 {
		return nil, closeError("PATH_UNSAFE", "runtime não pode ser symlink")
	}
	if err := os.MkdirAll(runtime, 0o755); err != nil {
		return nil, closeError("PATH_UNSAFE", "runtime não pode ser criado")
	}
	lockPath := filepath.Join(runtime, "cycle-close.lock")
	if lockInfo, statErr := os.Lstat(lockPath); statErr == nil && lockInfo.Mode()&os.ModeSymlink != 0 {
		return nil, closeError("PATH_UNSAFE", "lock não pode ser symlink")
	}
	file, err := os.OpenFile(lockPath, os.O_RDWR|os.O_CREATE, 0o600)
	if err != nil {
		return nil, closeError("PATH_UNSAFE", "lock não pode ser aberto")
	}
	defer file.Close()
	if err := lockCloseFile(file); err != nil {
		return nil, closeError("CLOSE_LOCKED", "outro fechamento está em execução")
	}
	defer unlockCloseFile(file)
	return action()
}

func closeTreeDigest(root string) (string, error) {
	info, err := os.Lstat(root)
	if err != nil || info.Mode()&os.ModeSymlink != 0 || !info.IsDir() {
		return "", closeError("RECOVERY_AMBIGUOUS", "árvore inválida: "+root)
	}
	entries := []string{}
	var walk func(string) error
	walk = func(directory string) error {
		children, readErr := os.ReadDir(directory)
		if readErr != nil {
			return closeError("PATH_UNSAFE", "entrada inválida no fechamento: "+directory)
		}
		directories, files := []string{}, []string{}
		for _, child := range children {
			if strings.EqualFold(child.Name(), ".planning") {
				return closeError("PATH_UNSAFE", "namespace .planning é proibido")
			}
			path := filepath.Join(directory, child.Name())
			metadata, statErr := os.Lstat(path)
			if statErr != nil || metadata.Mode()&os.ModeSymlink != 0 {
				return closeError("PATH_UNSAFE", "entrada inválida no fechamento: "+path)
			}
			if metadata.IsDir() {
				directories = append(directories, path)
			} else if metadata.Mode().IsRegular() {
				files = append(files, path)
			} else {
				return closeError("PATH_UNSAFE", "arquivo inválido no fechamento: "+path)
			}
		}
		for _, path := range directories {
			metadata, _ := os.Lstat(path)
			relative, _ := filepath.Rel(root, path)
			entries = append(entries, "D\x00"+filepath.ToSlash(relative)+"\x00"+fmt.Sprintf("%o", metadata.Mode().Perm())+"\n")
		}
		for _, path := range files {
			metadata, _ := os.Lstat(path)
			content, readErr := os.ReadFile(path)
			if readErr != nil {
				return closeError("RECOVERY_AMBIGUOUS", "arquivo inválido: "+path)
			}
			relative, _ := filepath.Rel(root, path)
			entries = append(entries, "F\x00"+filepath.ToSlash(relative)+"\x00"+fmt.Sprintf("%o", metadata.Mode().Perm())+"\x00"+sha256Bytes(content)+"\n")
		}
		for _, path := range directories {
			if err := walk(path); err != nil {
				return err
			}
		}
		return nil
	}
	err = walk(root)
	if err != nil {
		return "", err
	}
	return sha256Bytes([]byte(strings.Join(entries, ""))), nil
}

func closeFileDigest(path string) (string, error) {
	info, err := os.Lstat(path)
	if err != nil || info.Mode()&os.ModeSymlink != 0 || !info.Mode().IsRegular() {
		return "", closeError("RECOVERY_AMBIGUOUS", "arquivo inválido: "+path)
	}
	content, err := os.ReadFile(path)
	if err != nil {
		return "", closeError("RECOVERY_AMBIGUOUS", "arquivo inválido: "+path)
	}
	return sha256Bytes(content), nil
}

func closeDigestIfPresent(path string, directory bool) (string, error) {
	if _, err := os.Lstat(path); os.IsNotExist(err) {
		return "", nil
	}
	if directory {
		return closeTreeDigest(path)
	}
	return closeFileDigest(path)
}

func closeAtomicWrite(path string, content []byte) error {
	return closeAtomicWriteWithSync(path, content, syncDirectory)
}

func closeAtomicWriteWithSync(path string, content []byte, syncDir directorySync) error {
	if info, err := os.Lstat(path); err == nil {
		if info.Mode()&os.ModeSymlink != 0 || !info.Mode().IsRegular() {
			return closeError("PATH_UNSAFE", "escrita recusada para symlink: "+path)
		}
		current, readErr := os.ReadFile(path)
		if readErr == nil && bytes.Equal(current, content) {
			return syncDir(filepath.Dir(path))
		}
	}
	repository, err := closeRepositoryPath(path)
	if err != nil {
		return err
	}
	if err := closeRejectSymlinkChain(repository, path); err != nil {
		return err
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return closeError("PATH_UNSAFE", err.Error())
	}
	temporary, err := os.CreateTemp(filepath.Dir(path), "."+filepath.Base(path)+".*.tmp")
	if err != nil {
		return closeError("PATH_UNSAFE", err.Error())
	}
	temporaryPath := temporary.Name()
	defer os.Remove(temporaryPath)
	if info, statErr := os.Stat(path); statErr == nil {
		_ = temporary.Chmod(info.Mode().Perm())
	}
	if _, err := temporary.Write(content); err != nil {
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

func closeRejectSymlinkChain(root, path string) error {
	root = filepath.Clean(root)
	path = filepath.Clean(path)
	relative, err := filepath.Rel(root, path)
	if err != nil || relative == ".." || strings.HasPrefix(relative, ".."+string(filepath.Separator)) {
		return closeError("PATH_UNSAFE", "caminho fora do repositório: "+path)
	}
	cursor := root
	for _, part := range strings.Split(relative, string(filepath.Separator)) {
		if strings.EqualFold(part, ".planning") {
			return closeError("PATH_UNSAFE", "namespace .planning é proibido")
		}
		cursor = filepath.Join(cursor, part)
		if info, statErr := os.Lstat(cursor); statErr == nil && info.Mode()&os.ModeSymlink != 0 {
			return closeError("PATH_UNSAFE", "path atravessa symlink: "+cursor)
		}
	}
	return nil
}

func closeRepositoryPath(path string) (string, error) {
	canonical := filepath.ToSlash(filepath.Clean(path))
	marker := "/.bianchini/"
	index := strings.LastIndex(canonical, marker)
	if index <= 0 {
		return "", closeError("PATH_UNSAFE", "caminho fora do workspace: "+path)
	}
	return filepath.FromSlash(canonical[:index]), nil
}

func closeCopyTree(source, target string) error {
	if _, err := closeTreeDigest(source); err != nil {
		return err
	}
	if _, err := os.Lstat(target); err == nil {
		return closeError("RECOVERY_AMBIGUOUS", "target de cópia já existe: "+target)
	}
	rootInfo, _ := os.Stat(source)
	if err := os.MkdirAll(target, rootInfo.Mode().Perm()); err != nil {
		return err
	}
	if err := os.Chmod(target, rootInfo.Mode().Perm()); err != nil {
		return err
	}
	return filepath.WalkDir(source, func(path string, entry fs.DirEntry, walkErr error) error {
		if walkErr != nil || path == source {
			return walkErr
		}
		relative, _ := filepath.Rel(source, path)
		destination := filepath.Join(target, relative)
		info, err := os.Lstat(path)
		if err != nil || info.Mode()&os.ModeSymlink != 0 {
			return closeError("PATH_UNSAFE", "entrada inválida no fechamento: "+path)
		}
		if info.IsDir() {
			if err := os.Mkdir(destination, info.Mode().Perm()); err != nil {
				return err
			}
			return os.Chmod(destination, info.Mode().Perm())
		}
		content, err := os.ReadFile(path)
		if err != nil {
			return err
		}
		if err := os.WriteFile(destination, content, info.Mode().Perm()); err != nil {
			return err
		}
		return os.Chmod(destination, info.Mode().Perm())
	})
}

func closeRemoveKnown(path string, expected string) error {
	info, err := os.Lstat(path)
	if os.IsNotExist(err) {
		return syncDirectory(filepath.Dir(path))
	}
	if err != nil || info.Mode()&os.ModeSymlink != 0 {
		return closeError("PATH_UNSAFE", "remoção recusada para symlink: "+path)
	}
	if expected != "" {
		actual, digestErr := closeDigestIfPresent(path, info.IsDir())
		if digestErr != nil || actual != expected {
			return closeError("RECOVERY_AMBIGUOUS", "digest inesperado antes de remover "+path)
		}
	} else if info.IsDir() {
		if _, digestErr := closeTreeDigest(path); digestErr != nil {
			return digestErr
		}
	}
	return durableRemoveAll(path)
}

func closeRename(source, target string) error {
	return closeRenameWithSync(source, target, syncDirectory)
}

func closeRenameWithSync(source, target string, syncDir directorySync) error {
	if err := os.MkdirAll(filepath.Dir(target), 0o755); err != nil {
		return err
	}
	if err := os.Rename(source, target); err != nil {
		return err
	}
	return syncRenameDirectories(source, target, syncDir)
}

func writeCloseJournal(root string, journal closeJournal) error {
	content, err := json.MarshalIndent(journal, "", "  ")
	if err != nil {
		return closeError("JOURNAL_CORRUPT", err.Error())
	}
	return closeAtomicWrite(closeJournalPath(root), append(content, '\n'))
}

func readCloseJournal(root string) (*closeJournal, error) {
	path := closeJournalPath(root)
	info, err := os.Lstat(path)
	if os.IsNotExist(err) {
		return nil, nil
	}
	if err != nil || info.Mode()&os.ModeSymlink != 0 || !info.Mode().IsRegular() {
		return nil, closeError("JOURNAL_CORRUPT", "journal não é arquivo regular")
	}
	if err := closeRejectSymlinkChain(root, path); err != nil {
		return nil, closeError("JOURNAL_CORRUPT", "path inseguro no journal")
	}
	content, err := os.ReadFile(path)
	if err != nil {
		return nil, closeError("JOURNAL_CORRUPT", "journal truncado ou inválido")
	}
	decoder := json.NewDecoder(bytes.NewReader(content))
	decoder.DisallowUnknownFields()
	var journal closeJournal
	if err := decoder.Decode(&journal); err != nil {
		return nil, closeError("JOURNAL_CORRUPT", "journal truncado ou inválido")
	}
	var trailing any
	if err := decoder.Decode(&trailing); err != io.EOF {
		return nil, closeError("JOURNAL_CORRUPT", "journal truncado ou inválido")
	}
	if err := validateCloseJournal(root, journal); err != nil {
		return nil, err
	}
	return &journal, nil
}

func validateCloseJournal(root string, journal closeJournal) error {
	if journal.SchemaVersion != 1 || journal.SpecContract != 1 || !closePhases[journal.Phase] {
		return closeError("JOURNAL_CORRUPT", "versão ou fase do journal inválida")
	}
	if !closeChangeID.MatchString(journal.Change) {
		return closeError("JOURNAL_CORRUPT", "change do journal inválido")
	}
	expectedPaths := closePaths(root, journal.Change)
	if len(journal.Paths) != len(expectedPaths) {
		return closeError("JOURNAL_CORRUPT", "paths do journal inválidos")
	}
	for key, absolute := range expectedPaths {
		relative, _ := filepath.Rel(root, absolute)
		expected := filepath.ToSlash(relative)
		if journal.Paths[key] != expected {
			return closeError("JOURNAL_CORRUPT", "paths não correspondem ao change")
		}
		if err := closeRejectSymlinkChain(root, absolute); err != nil {
			return closeError("JOURNAL_CORRUPT", "path inseguro no journal")
		}
	}
	before := journal.Digests["before"]
	if !closeDigestMap(before) {
		return closeError("JOURNAL_CORRUPT", "digests before inválidos")
	}
	after := journal.Digests["after"]
	if journal.Phase == "PREPARING" || journal.Phase == "PREPARED" {
		if len(after) != 0 || journal.Phase == "PREPARING" && len(journal.Inputs) != 0 {
			return closeError("JOURNAL_CORRUPT", "journal PREPARING contém digests prematuros")
		}
	} else if !closeDigestMap(after) {
		return closeError("JOURNAL_CORRUPT", "digests after inválidos")
	}
	if journal.Phase != "PREPARING" {
		for _, key := range []string{"architecture", "system_model", "specs", "summary", "state"} {
			if !waveDigest.MatchString(journal.Inputs[key]) {
				return closeError("JOURNAL_CORRUPT", "digests de input inválidos")
			}
		}
		if len(journal.Inputs) != 5 {
			return closeError("JOURNAL_CORRUPT", "digests de input inválidos")
		}
	}
	return nil
}

func closeDigestMap(value map[string]string) bool {
	if len(value) != 3 {
		return false
	}
	for _, key := range []string{"current", "change", "state"} {
		if !waveDigest.MatchString(value[key]) {
			return false
		}
	}
	return true
}

func closePaths(root, change string) map[string]string {
	return map[string]string{
		"current":     filepath.Join(root, ".bianchini", "current"),
		"change":      filepath.Join(root, ".bianchini", "changes", change),
		"archive":     filepath.Join(root, ".bianchini", "archive", change),
		"state":       filepath.Join(root, ".bianchini", "STATE.md"),
		"transaction": closeTransactionPath(root, change),
	}
}

func prepareClose(root, change, specsSource, specsManifest string, summary, nextState []byte) (closeJournal, error) {
	if !closeChangeID.MatchString(change) {
		return closeJournal{}, closeError("PATH_UNSAFE", "change inválido: "+change)
	}
	paths := closePaths(root, change)
	for _, key := range []string{"current", "change"} {
		info, err := os.Lstat(paths[key])
		if err != nil || info.Mode()&os.ModeSymlink != 0 || !info.IsDir() {
			return closeJournal{}, closeError("CLOSE_INCOMPLETE", key+" ausente ou inválido")
		}
	}
	if _, err := os.Lstat(paths["archive"]); err == nil {
		return closeJournal{}, closeError("CLOSE_CONFLICT", "archive já existe: "+paths["archive"])
	}
	stateInfo, err := os.Lstat(paths["state"])
	if err != nil || stateInfo.Mode()&os.ModeSymlink != 0 || !stateInfo.Mode().IsRegular() {
		return closeJournal{}, closeError("CLOSE_INCOMPLETE", "STATE.md ausente ou inválido")
	}
	for _, name := range []string{"ARCHITECTURE.md", "SYSTEM_MODEL.md"} {
		path := filepath.Join(paths["change"], name)
		info, err := os.Lstat(path)
		if err != nil || info.Mode()&os.ModeSymlink != 0 || !info.Mode().IsRegular() {
			return closeJournal{}, closeError("CLOSE_INCOMPLETE", name+" final ausente")
		}
	}
	for _, input := range []string{specsSource, specsManifest} {
		if err := closeInputWithinChange(paths["change"], input); err != nil {
			return closeJournal{}, err
		}
	}
	if len(summary) == 0 || len(nextState) == 0 {
		return closeJournal{}, closeError("CLOSE_INCOMPLETE", "summary e next_state são obrigatórios")
	}
	if _, err := os.Lstat(paths["transaction"]); err == nil {
		return closeJournal{}, closeError("RECOVERY_AMBIGUOUS", "staging órfão sem journal")
	}
	currentDigest, err := closeTreeDigest(paths["current"])
	if err != nil {
		return closeJournal{}, err
	}
	changeDigest, err := closeTreeDigest(paths["change"])
	if err != nil {
		return closeJournal{}, err
	}
	stateDigest, err := closeFileDigest(paths["state"])
	if err != nil {
		return closeJournal{}, err
	}
	relativePaths := map[string]string{}
	for key, absolute := range paths {
		relative, _ := filepath.Rel(root, absolute)
		relativePaths[key] = filepath.ToSlash(relative)
	}
	journal := closeJournal{
		SchemaVersion: 1, SpecContract: 1, Change: change, Phase: "PREPARING", Paths: relativePaths,
		Digests: map[string]map[string]string{"before": {"current": currentDigest, "change": changeDigest, "state": stateDigest}, "after": {}},
		Inputs:  map[string]string{},
	}
	if err := writeCloseJournal(root, journal); err != nil {
		return closeJournal{}, err
	}
	inputs := filepath.Join(paths["transaction"], "inputs")
	if err := os.MkdirAll(inputs, 0o755); err != nil {
		return closeJournal{}, err
	}
	copyInputs := map[string][]byte{
		"ARCHITECTURE.md": mustReadClose(filepath.Join(paths["change"], "ARCHITECTURE.md")),
		"SYSTEM_MODEL.md": mustReadClose(filepath.Join(paths["change"], "SYSTEM_MODEL.md")),
		"SUMMARY.md":      summary, "STATE.md": nextState, "STATE.before.md": mustReadClose(paths["state"]),
	}
	for name, content := range copyInputs {
		if content == nil {
			return closeJournal{}, closeError("CLOSE_INCOMPLETE", "input ausente: "+name)
		}
		if err := closeAtomicWrite(filepath.Join(inputs, name), content); err != nil {
			return closeJournal{}, err
		}
	}
	if err := closeCopyTree(specsSource, filepath.Join(inputs, "specs")); err != nil {
		return closeJournal{}, err
	}
	manifestContent := mustReadClose(specsManifest)
	if manifestContent == nil {
		return closeJournal{}, closeError("PATH_UNSAFE", "specs manifest inválido")
	}
	if err := closeAtomicWrite(filepath.Join(inputs, "specs", "MANIFEST.json"), manifestContent); err != nil {
		return closeJournal{}, err
	}
	if err := syncTreeDurably(inputs); err != nil {
		return closeJournal{}, err
	}
	journal.Inputs = map[string]string{}
	for key, path := range map[string]string{
		"architecture": filepath.Join(inputs, "ARCHITECTURE.md"), "system_model": filepath.Join(inputs, "SYSTEM_MODEL.md"),
		"summary": filepath.Join(inputs, "SUMMARY.md"), "state": filepath.Join(inputs, "STATE.md"),
	} {
		journal.Inputs[key], err = closeFileDigest(path)
		if err != nil {
			return closeJournal{}, err
		}
	}
	journal.Inputs["specs"], err = closeTreeDigest(filepath.Join(inputs, "specs"))
	if err != nil {
		return closeJournal{}, err
	}
	journal.Phase = "PREPARED"
	if err := writeCloseJournal(root, journal); err != nil {
		return closeJournal{}, err
	}
	return journal, nil
}

func closeInputWithinChange(change, input string) error {
	if input == "" || strings.Contains(filepath.ToSlash(input), "/../") || hasForeignPart(input) {
		return closeError("PATH_UNSAFE", "specs source inseguro")
	}
	absolute, err := filepath.Abs(input)
	if err != nil {
		return closeError("PATH_UNSAFE", "specs source inseguro")
	}
	relative, err := filepath.Rel(change, absolute)
	if err != nil || relative == ".." || strings.HasPrefix(relative, ".."+string(filepath.Separator)) {
		return closeError("PATH_UNSAFE", "specs source fora do change")
	}
	return closeRejectSymlinkChain(change, absolute)
}

func mustReadClose(path string) []byte {
	content, err := os.ReadFile(path)
	if err != nil {
		return nil
	}
	return content
}

func crashRecoverableClose(root, change, specsSource, specsManifest string, summary, nextState []byte, failpoint string) (map[string]any, error) {
	return withCloseLock(root, func() (map[string]any, error) {
		journal, err := readCloseJournal(root)
		recovered := journal != nil
		if err != nil {
			return nil, err
		}
		if journal != nil && journal.Change != change {
			return nil, closeError("CLOSE_CONFLICT", "journal pendente pertence a "+journal.Change)
		}
		if journal != nil && journal.Phase == "PREPARING" {
			if _, err := discardPreparingClose(root, *journal); err != nil {
				return nil, err
			}
			journal, recovered = nil, true
		}
		if journal == nil {
			prepared, err := prepareClose(root, change, specsSource, specsManifest, summary, nextState)
			if err != nil {
				return nil, err
			}
			journal = &prepared
			if failpoint == "PREPARED" {
				return nil, closeCrash{phase: "PREPARED"}
			}
		}
		result, err := advanceClose(root, *journal, failpoint)
		if err != nil {
			return nil, err
		}
		result["recovered"] = recovered
		return result, nil
	})
}

func recoverPendingClose(root string) (map[string]any, error) {
	return withCloseLock(root, func() (map[string]any, error) {
		journal, err := readCloseJournal(root)
		if err != nil || journal == nil {
			return nil, err
		}
		if journal.Phase == "PREPARING" {
			return discardPreparingClose(root, *journal)
		}
		result, err := advanceClose(root, *journal, "")
		if err == nil {
			result["recovered"] = true
		}
		return result, err
	})
}

func discardPreparingClose(root string, journal closeJournal) (map[string]any, error) {
	paths := closePaths(root, journal.Change)
	for _, key := range []string{"current", "change", "state"} {
		actual, err := closeDigestIfPresent(paths[key], key != "state")
		if err != nil || actual != journal.Digests["before"][key] {
			return nil, closeError("RECOVERY_AMBIGUOUS", key+" divergiu durante preparação")
		}
	}
	if _, err := os.Lstat(paths["archive"]); err == nil {
		return nil, closeError("RECOVERY_AMBIGUOUS", "archive apareceu durante preparação")
	}
	if err := closeRemoveKnown(paths["transaction"], ""); err != nil {
		return nil, err
	}
	if err := durableRemoveFile(closeJournalPath(root)); err != nil {
		return nil, err
	}
	return map[string]any{"change": journal.Change, "status": "restored"}, nil
}

func advanceClose(root string, journal closeJournal, failpoint string) (map[string]any, error) {
	for {
		var err error
		switch journal.Phase {
		case "PREPARED":
			err = stageClose(root, &journal)
		case "STAGED":
			err = promoteCloseCurrent(root, &journal)
		case "CURRENT_PROMOTED":
			err = archiveCloseChange(root, &journal)
		case "CHANGE_ARCHIVED":
			err = commitCloseState(root, &journal)
		case "STATE_COMMITTED":
			err = verifyCloseDone(root, journal)
			if err == nil {
				journal.Phase = "DONE"
				err = writeCloseJournal(root, journal)
			}
		case "DONE":
			paths := closePaths(root, journal.Change)
			result := map[string]any{
				"change": journal.Change, "status": "completed", "archive": paths["archive"],
				"current_digest": journal.Digests["after"]["current"], "archive_digest": journal.Digests["after"]["change"],
				"state_digest": journal.Digests["after"]["state"],
			}
			if err := cleanupCloseDone(root, journal); err != nil {
				return nil, err
			}
			return result, nil
		default:
			return nil, closeError("JOURNAL_CORRUPT", "fase do journal inválida")
		}
		if err != nil {
			return nil, err
		}
		if failpoint != "" && journal.Phase == failpoint {
			return nil, closeCrash{phase: failpoint}
		}
	}
}

func stageClose(root string, journal *closeJournal) error {
	paths := closePaths(root, journal.Change)
	inputs := filepath.Join(paths["transaction"], "inputs")
	actualInputs := map[string]string{}
	var err error
	for key, path := range map[string]string{
		"architecture": filepath.Join(inputs, "ARCHITECTURE.md"), "system_model": filepath.Join(inputs, "SYSTEM_MODEL.md"),
		"summary": filepath.Join(inputs, "SUMMARY.md"), "state": filepath.Join(inputs, "STATE.md"),
	} {
		actualInputs[key], err = closeFileDigest(path)
		if err != nil {
			return err
		}
	}
	actualInputs["specs"], err = closeTreeDigest(filepath.Join(inputs, "specs"))
	if err != nil || !stringMapsEqual(actualInputs, journal.Inputs) {
		return closeError("RECOVERY_AMBIGUOUS", "inputs do fechamento divergiram")
	}
	beforeState, err := closeFileDigest(filepath.Join(inputs, "STATE.before.md"))
	if err != nil || beforeState != journal.Digests["before"]["state"] {
		return closeError("RECOVERY_AMBIGUOUS", "STATE.md anterior divergiu")
	}
	for _, key := range []string{"current", "change", "state"} {
		actual, digestErr := closeDigestIfPresent(paths[key], key != "state")
		if digestErr != nil || actual != journal.Digests["before"][key] {
			return closeError("RECOVERY_AMBIGUOUS", key+" divergiu do digest conhecido")
		}
	}
	stagedCurrent := filepath.Join(paths["transaction"], "staged-current")
	stagedArchive := filepath.Join(paths["transaction"], "staged-archive")
	if err := closeRemoveKnown(stagedCurrent, ""); err != nil {
		return err
	}
	if err := closeRemoveKnown(stagedArchive, ""); err != nil {
		return err
	}
	if err := closeCopyTree(paths["current"], stagedCurrent); err != nil {
		return err
	}
	for _, name := range []string{"ARCHITECTURE.md", "SYSTEM_MODEL.md"} {
		if err := closeAtomicWrite(filepath.Join(stagedCurrent, name), mustReadClose(filepath.Join(inputs, name))); err != nil {
			return err
		}
	}
	stagedSpecs := filepath.Join(stagedCurrent, "specs")
	if err := closeRemoveKnown(stagedSpecs, ""); err != nil {
		return err
	}
	if err := closeCopyTree(filepath.Join(inputs, "specs"), stagedSpecs); err != nil {
		return err
	}
	if err := closeCopyTree(paths["change"], stagedArchive); err != nil {
		return err
	}
	if err := closeAtomicWrite(filepath.Join(stagedArchive, "SUMMARY.md"), mustReadClose(filepath.Join(inputs, "SUMMARY.md"))); err != nil {
		return err
	}
	if err := syncTreeDurably(stagedCurrent); err != nil {
		return err
	}
	if err := syncTreeDurably(stagedArchive); err != nil {
		return err
	}
	currentAfter, err := closeTreeDigest(stagedCurrent)
	if err != nil {
		return err
	}
	changeAfter, err := closeTreeDigest(stagedArchive)
	if err != nil {
		return err
	}
	stateAfter, err := closeFileDigest(filepath.Join(inputs, "STATE.md"))
	if err != nil {
		return err
	}
	journal.Digests["after"] = map[string]string{"current": currentAfter, "change": changeAfter, "state": stateAfter}
	journal.Phase = "STAGED"
	return writeCloseJournal(root, *journal)
}

func promoteCloseCurrent(root string, journal *closeJournal) error {
	paths := closePaths(root, journal.Change)
	stage := filepath.Join(paths["transaction"], "staged-current")
	backup := filepath.Join(paths["transaction"], "previous-current")
	before, after := journal.Digests["before"]["current"], journal.Digests["after"]["current"]
	currentDigest, _ := closeDigestIfPresent(paths["current"], true)
	stageDigest, _ := closeDigestIfPresent(stage, true)
	backupDigest, _ := closeDigestIfPresent(backup, true)
	if currentDigest == before && stageDigest == after && backupDigest == "" {
		if err := closeRename(paths["current"], backup); err != nil {
			return err
		}
		currentDigest, backupDigest = "", before
	}
	if currentDigest == "" && stageDigest == after && backupDigest == before {
		if err := closeRename(stage, paths["current"]); err != nil {
			return err
		}
		currentDigest, stageDigest = after, ""
	}
	if currentDigest != after || stageDigest != "" || backupDigest != before {
		return closeError("RECOVERY_AMBIGUOUS", "promoção de current está em estado desconhecido")
	}
	if err := syncRenameDirectories(stage, paths["current"], syncDirectory); err != nil {
		return err
	}
	journal.Phase = "CURRENT_PROMOTED"
	return writeCloseJournal(root, *journal)
}

func archiveCloseChange(root string, journal *closeJournal) error {
	paths := closePaths(root, journal.Change)
	stage := filepath.Join(paths["transaction"], "staged-archive")
	backup := filepath.Join(paths["transaction"], "previous-change")
	before, after := journal.Digests["before"]["change"], journal.Digests["after"]["change"]
	changeDigest, _ := closeDigestIfPresent(paths["change"], true)
	archiveDigest, _ := closeDigestIfPresent(paths["archive"], true)
	stageDigest, _ := closeDigestIfPresent(stage, true)
	backupDigest, _ := closeDigestIfPresent(backup, true)
	if changeDigest == before && archiveDigest == "" && stageDigest == after && backupDigest == "" {
		if err := closeRename(paths["change"], backup); err != nil {
			return err
		}
		changeDigest, backupDigest = "", before
	}
	if changeDigest == "" && archiveDigest == "" && stageDigest == after && backupDigest == before {
		if err := closeRename(stage, paths["archive"]); err != nil {
			return err
		}
		archiveDigest, stageDigest = after, ""
	}
	if changeDigest != "" || archiveDigest != after || stageDigest != "" || backupDigest != before {
		return closeError("RECOVERY_AMBIGUOUS", "arquivamento da mudança está em estado desconhecido")
	}
	if err := syncRenameDirectories(stage, paths["archive"], syncDirectory); err != nil {
		return err
	}
	journal.Phase = "CHANGE_ARCHIVED"
	return writeCloseJournal(root, *journal)
}

func commitCloseState(root string, journal *closeJournal) error {
	paths := closePaths(root, journal.Change)
	before, after := journal.Digests["before"]["state"], journal.Digests["after"]["state"]
	current, _ := closeDigestIfPresent(paths["state"], false)
	if current == before {
		if err := closeAtomicWrite(paths["state"], mustReadClose(filepath.Join(paths["transaction"], "inputs", "STATE.md"))); err != nil {
			return err
		}
		current, _ = closeFileDigest(paths["state"])
	}
	if current != after {
		return closeError("RECOVERY_AMBIGUOUS", "STATE.md promovido divergiu do digest conhecido")
	}
	journal.Phase = "STATE_COMMITTED"
	return writeCloseJournal(root, *journal)
}

func verifyCloseDone(root string, journal closeJournal) error {
	paths := closePaths(root, journal.Change)
	for _, key := range []string{"current", "archive", "state"} {
		expectedKey := key
		directory := key != "state"
		if key == "archive" {
			expectedKey = "change"
		}
		actual, err := closeDigestIfPresent(paths[key], directory)
		if err != nil || actual != journal.Digests["after"][expectedKey] {
			return closeError("RECOVERY_AMBIGUOUS", key+" final divergiu do digest conhecido")
		}
	}
	if _, err := os.Lstat(paths["change"]); err == nil {
		return closeError("RECOVERY_AMBIGUOUS", "change ainda existe após arquivamento")
	}
	return nil
}

func cleanupCloseDone(root string, journal closeJournal) error {
	if err := verifyCloseDone(root, journal); err != nil {
		return err
	}
	paths := closePaths(root, journal.Change)
	if err := closeRemoveKnown(paths["transaction"], ""); err != nil {
		return err
	}
	if err := durableRemoveFile(closeJournalPath(root)); err != nil {
		return err
	}
	return nil
}

func stringMapsEqual(left, right map[string]string) bool {
	if len(left) != len(right) {
		return false
	}
	for key, value := range left {
		if right[key] != value {
			return false
		}
	}
	return true
}
