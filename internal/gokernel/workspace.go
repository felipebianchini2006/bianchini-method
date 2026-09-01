package gokernel

import (
	"bytes"
	"encoding/json"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"time"
)

const (
	methodVersion04 = "0.4"
	stateLimitBytes = 64 * 1024
)

var frontmatterPattern = regexp.MustCompile(`(?s)\A---\r?\n(.*?)\r?\n---(?:\r?\n|\z)`)

var workspaceStateAllowed = map[string]bool{
	"schema_version": true, "method": true, "active_work": true,
	"current_unit": true, "status": true, "blockers": true,
	"next_action": true, "last_completed": true, "pointers": true,
	"digest": true, "updated_at": true,
}

var workspaceStateHistory = map[string]bool{
	"history": true, "ledger": true, "events": true, "results": true,
	"timeline": true, "completed_work": true,
}

type methodWorkspace struct {
	root        string
	dir         string
	state       string
	current     string
	changes     string
	runtime     string
	currentMod  string
	currentSpec string
}

func newMethodWorkspace(root string) methodWorkspace {
	directory := filepath.Join(root, ".bianchini")
	current := filepath.Join(directory, "current")
	return methodWorkspace{
		root: root, dir: directory, state: filepath.Join(directory, "STATE.md"),
		current: current, changes: filepath.Join(directory, "changes"),
		runtime:     filepath.Join(directory, ".runtime"),
		currentMod:  filepath.Join(current, "SYSTEM_MODEL.md"),
		currentSpec: filepath.Join(current, "specs"),
	}
}

func repositoryRoot(repo string) (string, error) {
	root, err := safeRoot(repo)
	if err != nil {
		return "", workflowError("DIRTY_WORKSPACE", strings.TrimPrefix(err.Error(), "PATH_SAFETY: "))
	}
	marker := filepath.Join(root, ".git")
	info, err := os.Lstat(marker)
	if err != nil || info.Mode()&os.ModeSymlink != 0 || (!info.IsDir() && !info.Mode().IsRegular()) {
		return "", workflowError("DIRTY_WORKSPACE", "o diretório não é uma raiz Git")
	}
	return root, nil
}

func (workspace methodWorkspace) initialize() error {
	directories := []string{
		workspace.currentSpec, workspace.changes, filepath.Join(workspace.dir, "quick"),
		filepath.Join(workspace.dir, "debug", "active"), filepath.Join(workspace.dir, "debug", "resolved"),
		filepath.Join(workspace.dir, "archive"), workspace.runtime,
	}
	for _, directory := range directories {
		if err := workspace.mkdirAll(directory); err != nil {
			return err
		}
	}
	emptyModel := map[string]any{
		"schema_version": 1, "modules": []any{}, "interfaces": []any{},
		"capabilities": []any{}, "contracts": []any{}, "ownership": []any{},
		"data": []any{}, "integrations": []any{}, "journeys": []any{},
		"invariants": []any{}, "effects": []any{},
	}
	modelJSON, _ := json.MarshalIndent(emptyModel, "", "  ")
	manifestJSON, _ := json.MarshalIndent(map[string]any{
		"schema_version": 1, "spec_contract": 1,
		"specs": []any{}, "risk_coverage": []any{},
	}, "", "  ")
	defaults := map[string][]byte{
		filepath.Join(workspace.dir, ".gitignore"):            []byte(".runtime/\n"),
		filepath.Join(workspace.dir, "PROJECT.md"):            []byte("# Projeto\n\nPropósito, limites e invariantes estáveis.\n"),
		filepath.Join(workspace.current, "ARCHITECTURE.md"):   []byte("# Arquitetura atual\n"),
		workspace.currentMod:                                  append(append([]byte("---\n"), modelJSON...), []byte("\n---\n# Modelo do sistema\n")...),
		filepath.Join(workspace.currentSpec, "MANIFEST.json"): append(manifestJSON, '\n'),
		filepath.Join(workspace.dir, "debug", "KNOWLEDGE.md"): []byte("# Conhecimento de debug\n"),
	}
	paths := make([]string, 0, len(defaults))
	for path := range defaults {
		paths = append(paths, path)
	}
	sort.Strings(paths)
	for _, path := range paths {
		if _, err := os.Lstat(path); err == nil {
			continue
		} else if !os.IsNotExist(err) {
			return workflowError("MODEL_MISMATCH", err.Error())
		}
		if err := workspace.atomicWrite(path, defaults[path]); err != nil {
			return err
		}
	}
	return nil
}

func (workspace methodWorkspace) initialState() map[string]any {
	return map[string]any{
		"schema_version": 1, "method": methodVersion04, "active_work": nil,
		"current_unit": nil, "status": "idle", "blockers": []any{},
		"next_action":    "Iniciar /sdd-planning, /executar-direto ou /corrigir-bug.",
		"last_completed": nil,
		"pointers": map[string]any{
			"architecture": ".bianchini/current/ARCHITECTURE.md",
			"system_model": ".bianchini/current/SYSTEM_MODEL.md",
			"specs":        ".bianchini/current/specs", "coherence": nil,
		},
		"digest": nil, "updated_at": utcNow(),
	}
}

func (workspace methodWorkspace) writeState(state map[string]any, body string) error {
	validated, err := workspace.validateState(state)
	if err != nil {
		return err
	}
	encoded, err := json.Marshal(validated)
	if err != nil {
		return workflowError("DOCVIVA_INCOMPLETE", err.Error())
	}
	document := append([]byte("---\n"), encoded...)
	document = append(document, []byte("\n---\n"+strings.TrimRight(body, "\r\n")+"\n")...)
	if len(document) > stateLimitBytes {
		return workflowError("DOCVIVA_INCOMPLETE", "STATE.md excede o limite de 64 KiB")
	}
	return workspace.atomicWrite(workspace.state, document)
}

func (workspace methodWorkspace) readState() (map[string]any, error) {
	if err := workspace.validateWorkspacePath(workspace.state); err != nil {
		return nil, err
	}
	content, err := os.ReadFile(workspace.state)
	if err != nil {
		return nil, workflowError("DOCVIVA_INCOMPLETE", "STATE.md ausente: "+workspace.state)
	}
	if len(content) > stateLimitBytes {
		return nil, workflowError("DOCVIVA_INCOMPLETE", "STATE.md excede o limite de 64 KiB")
	}
	match := frontmatterPattern.FindSubmatch(content)
	if match == nil {
		return nil, workflowError("DOCVIVA_INCOMPLETE", "STATE.md exige frontmatter JSON")
	}
	value, err := decodeJSONObject(match[1])
	if err != nil {
		return nil, workflowError("DOCVIVA_INCOMPLETE", "STATE.md contém JSON inválido")
	}
	return workspace.validateState(value)
}

func (workspace methodWorkspace) validateState(state map[string]any) (map[string]any, error) {
	for key := range state {
		if workspaceStateHistory[key] {
			return nil, workflowError("DOCVIVA_INCOMPLETE", "campo de histórico proibido em STATE.md: "+key)
		}
		if !workspaceStateAllowed[key] {
			return nil, workflowError("DOCVIVA_INCOMPLETE", "campo não suportado em STATE.md: "+key)
		}
	}
	if stateInt(state["schema_version"]) != 1 {
		return nil, workflowError("DOCVIVA_INCOMPLETE", "STATE.md exige schema_version 1")
	}
	if stateString(state["method"]) != methodVersion04 {
		return nil, workflowError("MIGRATION_REQUIRED", "STATE.md não pertence ao método 0.4")
	}
	if _, ok := state["blockers"].([]any); !ok {
		return nil, workflowError("DOCVIVA_INCOMPLETE", "STATE.md.blockers exige lista de strings")
	}
	for _, blocker := range stateArray(state["blockers"]) {
		if _, ok := blocker.(string); !ok {
			return nil, workflowError("DOCVIVA_INCOMPLETE", "STATE.md.blockers exige lista de strings")
		}
	}
	pointers, ok := state["pointers"].(map[string]any)
	if !ok {
		return nil, workflowError("DOCVIVA_INCOMPLETE", "STATE.md.pointers exige objeto de strings ou null")
	}
	if _, exists := pointers["model"]; exists {
		return nil, workflowError("DOCVIVA_INCOMPLETE", "pointer não canônico: use system_model")
	}
	for label, value := range pointers {
		if value == nil {
			continue
		}
		text, ok := value.(string)
		if !ok {
			return nil, workflowError("DOCVIVA_INCOMPLETE", "STATE.md.pointers exige objeto de strings ou null")
		}
		if !strings.HasPrefix(text, ".bianchini/") {
			return nil, workflowError("DOCVIVA_INCOMPLETE", "pointer fora de .bianchini: "+label)
		}
		if _, err := workspace.confined(text); err != nil {
			return nil, err
		}
	}
	copyBytes, _ := json.Marshal(state)
	return decodeJSONObject(copyBytes)
}

func (workspace methodWorkspace) confined(path string) (string, error) {
	if !filepath.IsAbs(path) {
		path = filepath.Join(workspace.root, path)
	}
	abs, err := filepath.Abs(path)
	if err != nil {
		return "", workflowError("MODEL_MISMATCH", err.Error())
	}
	base := filepath.Clean(workspace.dir)
	abs = filepath.Clean(abs)
	relative, err := filepath.Rel(base, abs)
	if err != nil || relative == ".." || strings.HasPrefix(relative, ".."+string(filepath.Separator)) || filepath.IsAbs(relative) {
		return "", workflowError("MODEL_MISMATCH", "caminho fora de .bianchini: "+path)
	}
	return abs, nil
}

func (workspace methodWorkspace) validateWorkspacePath(path string) error {
	if _, err := workspace.confined(path); err != nil {
		return err
	}
	probe := path
	for {
		info, err := os.Lstat(probe)
		if err == nil && info.Mode()&os.ModeSymlink != 0 {
			return workflowError("MODEL_MISMATCH", "caminho contém symlink: "+probe)
		}
		if filepath.Clean(probe) == filepath.Clean(workspace.dir) {
			break
		}
		parent := filepath.Dir(probe)
		if parent == probe {
			return workflowError("MODEL_MISMATCH", "caminho fora de .bianchini: "+path)
		}
		probe = parent
	}
	return nil
}

func (workspace methodWorkspace) mkdirAll(path string) error {
	if _, err := workspace.confined(path); err != nil {
		return err
	}
	if filepath.Clean(path) != filepath.Clean(workspace.dir) {
		if err := workspace.validateWorkspacePath(filepath.Dir(path)); err != nil {
			return err
		}
	}
	if err := os.MkdirAll(path, 0o755); err != nil {
		return workflowError("MODEL_MISMATCH", err.Error())
	}
	return workspace.validateWorkspacePath(path)
}

func (workspace methodWorkspace) atomicWrite(path string, content []byte) error {
	if _, err := workspace.confined(path); err != nil {
		return err
	}
	if err := workspace.mkdirAll(filepath.Dir(path)); err != nil {
		return err
	}
	if info, err := os.Lstat(path); err == nil {
		if info.Mode()&os.ModeSymlink != 0 || !info.Mode().IsRegular() {
			return workflowError("MODEL_MISMATCH", "target de escrita inseguro: "+path)
		}
		existing, readErr := os.ReadFile(path)
		if readErr == nil && bytes.Equal(existing, content) {
			return nil
		}
	}
	temporary, err := os.CreateTemp(filepath.Dir(path), "."+filepath.Base(path)+".*.tmp")
	if err != nil {
		return workflowError("MODEL_MISMATCH", err.Error())
	}
	temporaryPath := temporary.Name()
	defer os.Remove(temporaryPath)
	if info, statErr := os.Stat(path); statErr == nil {
		if chmodErr := temporary.Chmod(info.Mode().Perm()); chmodErr != nil {
			temporary.Close()
			return workflowError("MODEL_MISMATCH", chmodErr.Error())
		}
	}
	if _, err := temporary.Write(content); err != nil {
		temporary.Close()
		return workflowError("MODEL_MISMATCH", err.Error())
	}
	if err := temporary.Sync(); err != nil {
		temporary.Close()
		return workflowError("MODEL_MISMATCH", err.Error())
	}
	if err := temporary.Close(); err != nil {
		return workflowError("MODEL_MISMATCH", err.Error())
	}
	if err := durableRename(temporaryPath, path); err != nil {
		return workflowError("MODEL_MISMATCH", err.Error())
	}
	return nil
}

func readJSONFrontmatter(path, label string) (map[string]any, error) {
	info, err := os.Lstat(path)
	if err != nil || info.Mode()&os.ModeSymlink != 0 || !info.Mode().IsRegular() {
		return nil, workflowError("MODEL_MISMATCH", label+": arquivo ausente ou inseguro")
	}
	content, err := os.ReadFile(path)
	if err != nil || !validUTF8Text(content) {
		return nil, workflowError("MODEL_MISMATCH", label+": conteúdo inválido")
	}
	match := frontmatterPattern.FindSubmatch(content)
	if match == nil {
		return nil, workflowError("MODEL_MISMATCH", label+": frontmatter ausente")
	}
	value, err := decodeJSONObject(match[1])
	if err != nil {
		return nil, workflowError("MODEL_MISMATCH", label+": JSON inválido")
	}
	return value, nil
}

func frontmatterDocument(value map[string]any, body string, compact bool) ([]byte, error) {
	var encoded []byte
	var err error
	if compact {
		encoded, err = json.Marshal(value)
	} else {
		encoded, err = json.MarshalIndent(value, "", "  ")
	}
	if err != nil {
		return nil, err
	}
	return []byte("---\n" + string(encoded) + "\n---\n\n" + strings.TrimRight(body, "\r\n") + "\n"), nil
}

func utcNow() string {
	return time.Now().UTC().Truncate(time.Second).Format("2006-01-02T15:04:05+00:00")
}

func workflowError(code, message string) error {
	return &commandError{message: code + ": " + message, exitCode: 3}
}

func removeNewWorkspacePath(path, root string) {
	relative, err := filepath.Rel(root, path)
	if err == nil && relative != "." && relative != ".." && !strings.HasPrefix(relative, ".."+string(filepath.Separator)) {
		_ = os.RemoveAll(path)
	}
}
