package gokernel

import (
	"encoding/json"
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"unicode"

	"golang.org/x/text/unicode/norm"
)

var modelCollections = []string{
	"modules", "interfaces", "capabilities", "contracts", "ownership",
	"data", "integrations", "journeys", "invariants", "effects",
}

func runModel(args []string) (any, error) {
	if len(args) == 0 {
		return nil, argparseError("the following arguments are required: action")
	}
	action := args[0]
	if !oneOf(action, "init", "validate") {
		return nil, argparseError(fmt.Sprintf("argument action: invalid choice: '%s'", action))
	}
	flags, err := parseFlags(args[1:], map[string]bool{"--repo": true, "--change": true}, map[string]bool{})
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
	change := lastValue(flags, "--change")
	if action == "init" {
		initialized, err := initializeModelWorkspace(repo)
		if err != nil {
			return nil, err
		}
		if change == "" {
			return initialized, nil
		}
		return createModelChange(repo, change)
	}
	if change != "" {
		return validateModelChange(repo, change)
	}
	return validateModelWorkspace(repo)
}

func initializeModelWorkspace(repo string) (map[string]any, error) {
	root, err := repositoryRoot(repo)
	if err != nil {
		return nil, err
	}
	workspace := newMethodWorkspace(root)
	if info, statErr := os.Lstat(workspace.dir); statErr == nil && info.Mode()&os.ModeSymlink != 0 {
		return nil, workflowError("MODEL_MISMATCH", ".bianchini não pode ser symlink")
	}
	if info, statErr := os.Lstat(workspace.state); statErr == nil && info.Mode().IsRegular() && info.Mode()&os.ModeSymlink == 0 {
		state, err := workspace.readState()
		if err != nil {
			return nil, err
		}
		return map[string]any{
			"method": stateString(state["method"]), "status": stateString(state["status"]),
			"workspace": workspace.dir, "created": false,
		}, nil
	}
	legacy, err := hasLegacyBianchiniArtifacts(root)
	if err != nil {
		return nil, err
	}
	if legacy {
		return nil, workflowError("MIGRATION_REQUIRED", "documentação anterior detectada; use /migrar-bianchini")
	}
	if _, statErr := os.Lstat(workspace.dir); statErr == nil {
		return nil, workflowError("MODEL_MISMATCH", ".bianchini existe sem STATE.md válido")
	}
	if err := workspace.initialize(); err != nil {
		return nil, err
	}
	if err := workspace.writeState(workspace.initialState(), "# Estado atual"); err != nil {
		return nil, err
	}
	return map[string]any{
		"method": methodVersion04, "status": "idle", "workspace": workspace.dir, "created": true,
	}, nil
}

func validateModelWorkspace(repo string) (map[string]any, error) {
	root, err := repositoryRoot(repo)
	if err != nil {
		return nil, err
	}
	workspace := newMethodWorkspace(root)
	state, err := workspace.readState()
	if err != nil {
		return nil, err
	}
	required := []string{"schema_version", "method", "status", "active_work", "blockers", "next_action", "pointers", "updated_at"}
	missing := missingMapKeys(state, required)
	if len(missing) > 0 {
		return nil, workflowError("MODEL_MISMATCH", "STATE.md incompleto: "+strings.Join(missing, ", "))
	}
	pointers := stateObject(state["pointers"])
	modelPointer := stateString(pointers["system_model"])
	modelPath, err := workspace.confined(modelPointer)
	if err != nil {
		return nil, err
	}
	if err := workspace.validateWorkspacePath(modelPath); err != nil {
		return nil, err
	}
	model, err := readJSONFrontmatter(modelPath, "SYSTEM_MODEL.md")
	if err != nil {
		return nil, err
	}
	modelRequired := append([]string{"schema_version"}, modelCollections...)
	modelMissing := missingMapKeys(model, modelRequired)
	if len(modelMissing) > 0 {
		return nil, workflowError("MODEL_MISMATCH", "SYSTEM_MODEL.md incompleto: "+strings.Join(modelMissing, ", "))
	}
	return map[string]any{
		"valid": true, "method": methodVersion04, "status": stateString(state["status"]),
		"state": workspace.state, "system_model": modelPath,
	}, nil
}

func createModelChange(repo, name string) (map[string]any, error) {
	root, err := repositoryRoot(repo)
	if err != nil {
		return nil, err
	}
	workspace := newMethodWorkspace(root)
	state, err := workspace.readState()
	if err != nil {
		return nil, err
	}
	if state["active_work"] != nil {
		return nil, workflowError("COHERENCE_ERROR", "já existe trabalho ativo")
	}
	slug, err := modelSlug(name)
	if err != nil {
		return nil, err
	}
	specs, err := inspectCurrentSpecs(workspace)
	if err != nil {
		return nil, err
	}
	identifier, err := workspace.allocateID("change")
	if err != nil {
		return nil, err
	}
	workID := identifier + "-" + slug
	directory := filepath.Join(workspace.changes, workID)
	if _, statErr := os.Lstat(directory); statErr == nil {
		return nil, workflowError("MODEL_MISMATCH", "mudança já existe: "+workID)
	}
	for _, path := range []string{directory, filepath.Join(directory, "plans"), filepath.Join(directory, "results"), filepath.Join(directory, "specs", "expected")} {
		if err := workspace.mkdirAll(path); err != nil {
			removeNewWorkspacePath(directory, workspace.changes)
			return nil, err
		}
	}
	failed := true
	defer func() {
		if failed {
			removeNewWorkspacePath(directory, workspace.changes)
		}
	}()
	templates := map[string]string{
		"SCOPE.md":        "# Escopo\n\nDefina resultado, aceite e não escopo.\n",
		"RESEARCH.md":     "# Pesquisa\n\nRegistre stack, fontes oficiais e decisões aplicadas.\n",
		"ARCHITECTURE.md": "# Arquitetura global\n\nDecisões, alternativas rejeitadas e trade-offs.\n",
		"ROADMAP.md":      "# Roadmap\n\nListe todas as fases e suas dependências.\n",
		"SUMMARY.md":      "# Resumo\n\nPreenchido no fechamento.\n",
	}
	for relative, content := range templates {
		if err := workspace.atomicWrite(filepath.Join(directory, relative), []byte(content)); err != nil {
			return nil, err
		}
	}
	modelBytes, err := os.ReadFile(workspace.currentMod)
	if err != nil {
		return nil, workflowError("MODEL_MISMATCH", "SYSTEM_MODEL atual ausente")
	}
	if err := workspace.atomicWrite(filepath.Join(directory, "SYSTEM_MODEL.md"), modelBytes); err != nil {
		return nil, err
	}
	for relative, content := range specs {
		if err := workspace.atomicWrite(filepath.Join(directory, "specs", "expected", filepath.FromSlash(relative)), content); err != nil {
			return nil, err
		}
	}
	emptyManifest, _ := json.MarshalIndent(map[string]any{
		"schema_version": 1, "spec_contract": 1, "specs": []any{}, "risk_coverage": []any{},
	}, "", "  ")
	if err := workspace.atomicWrite(filepath.Join(directory, "specs", "MANIFEST.json"), append(emptyManifest, '\n')); err != nil {
		return nil, err
	}
	coherence := map[string]any{
		"schema_version": 2, "planning_contract": 2, "spec_contract": 1,
		"change": workID, "status": "pending", "findings": []any{}, "impact": nil,
		"digest": nil, "updated_at": utcNow(),
	}
	coherenceDocument, err := frontmatterDocument(coherence, "# Coerência\n\nAguardando arquitetura, modelo e planos.", false)
	if err != nil {
		return nil, workflowError("MODEL_MISMATCH", err.Error())
	}
	if err := workspace.atomicWrite(filepath.Join(directory, "COHERENCE.md"), coherenceDocument); err != nil {
		return nil, err
	}
	state["active_work"] = map[string]any{"kind": "change", "id": workID, "status": "planning"}
	state["current_unit"] = "research"
	state["status"] = "planning"
	state["blockers"] = []any{}
	state["next_action"] = "Pesquisar a stack e definir o SYSTEM_MODEL de " + workID + "."
	state["digest"] = nil
	state["updated_at"] = utcNow()
	pointers := stateObject(state["pointers"])
	pointers["architecture"] = ".bianchini/changes/" + workID + "/ARCHITECTURE.md"
	pointers["system_model"] = ".bianchini/changes/" + workID + "/SYSTEM_MODEL.md"
	pointers["specs"] = ".bianchini/changes/" + workID + "/specs/expected"
	pointers["coherence"] = ".bianchini/changes/" + workID + "/COHERENCE.md"
	state["pointers"] = pointers
	if err := workspace.writeState(state, "# Estado atual"); err != nil {
		return nil, err
	}
	failed = false
	return map[string]any{
		"method": methodVersion04, "change": workID, "status": "planning",
		"spec_contract": 1, "path": directory,
	}, nil
}

func validateModelChange(repo, change string) (map[string]any, error) {
	root, err := repositoryRoot(repo)
	if err != nil {
		return nil, err
	}
	workspace := newMethodWorkspace(root)
	if _, err := workspace.readState(); err != nil {
		return nil, err
	}
	directory, err := locateChangeDirectory(workspace, change)
	if err != nil {
		return nil, err
	}
	current, err := loadProjectModel(workspace.currentMod)
	if err != nil {
		return nil, workflowError("MODEL_MISMATCH", err.Error())
	}
	expected, err := loadProjectModel(filepath.Join(directory, "SYSTEM_MODEL.md"))
	if err != nil {
		return nil, workflowError("MODEL_MISMATCH", err.Error())
	}
	plans, err := filepath.Glob(filepath.Join(directory, "plans", "P*.md"))
	if err != nil || len(plans) == 0 {
		return nil, workflowError("COHERENCE_ERROR", "a mudança exige ao menos um plano")
	}
	sort.Strings(plans)
	calculated := current
	for _, path := range plans {
		plan, loadErr := loadPlanContract(path)
		if loadErr != nil {
			return nil, workflowError("MODEL_MISMATCH", loadErr.Error())
		}
		calculated, loadErr = calculated.applyDelta(plan.modelDelta)
		if loadErr != nil {
			return nil, workflowError("MODEL_MISMATCH", loadErr.Error())
		}
	}
	coherence, specContract, err := loadCoherenceContract(directory)
	if err != nil {
		return nil, err
	}
	differences := calculated.differences(expected)
	result := map[string]any{
		"valid": len(differences) == 0, "change": filepath.Base(directory),
		"current_digest": current.digest(), "calculated_digest": calculated.digest(),
		"expected_digest": expected.digest(), "differences": differences,
	}
	if specContract != nil {
		specs, loadErr := loadModelSpecPackage(workspace, directory, coherence)
		if loadErr != nil {
			return nil, loadErr
		}
		for key, value := range specs {
			result[key] = value
		}
	}
	return result, nil
}

func loadCoherenceContract(directory string) (map[string]any, *int, error) {
	coherence, err := readStructuredFrontmatter(filepath.Join(directory, "COHERENCE.md"))
	if err != nil {
		return nil, nil, workflowError("COHERENCE_ERROR", err.Error())
	}
	schema := stateInt(coherence["schema_version"])
	if schema == 0 {
		schema = 1
	}
	if schema != 1 && schema != 2 {
		return nil, nil, workflowError("COHERENCE_ERROR", "schema_version de COHERENCE inválido")
	}
	planningContract := stateInt(coherence["planning_contract"])
	if planningContract == 0 {
		planningContract = 1
	}
	if planningContract != 1 && planningContract != 2 {
		return nil, nil, workflowError("COHERENCE_ERROR", "planning_contract inválido")
	}
	if schema == 1 {
		return coherence, nil, nil
	}
	if planningContract != 2 {
		return nil, nil, workflowError("COHERENCE_ERROR", "COHERENCE schema 2 exige planning_contract: 2")
	}
	if stateInt(coherence["spec_contract"]) != 1 {
		return nil, nil, workflowError("SPEC_CONTRACT_UNSUPPORTED", "COHERENCE schema 2 exige spec_contract: 1")
	}
	specContract := 1
	return coherence, &specContract, nil
}

func (workspace methodWorkspace) allocateID(kind string) (string, error) {
	prefix, width := "", 0
	if kind == "change" {
		prefix, width = "C", 3
	} else {
		return "", workflowError("MODEL_MISMATCH", "tipo de ID desconhecido: "+kind)
	}
	if err := workspace.mkdirAll(workspace.runtime); err != nil {
		return "", err
	}
	countersPath := filepath.Join(workspace.runtime, "id-counters.json")
	counters := map[string]any{}
	if content, err := os.ReadFile(countersPath); err == nil {
		loaded, decodeErr := decodeJSONObject(content)
		if decodeErr != nil {
			return "", workflowError("MODEL_MISMATCH", "registro de IDs inválido")
		}
		counters = loaded
	}
	largest := 0
	pattern := regexp.MustCompile("^" + prefix + `([0-9]+)(?:\b|[-_.])`)
	err := filepath.WalkDir(workspace.dir, func(path string, entry fs.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if entry.Type()&os.ModeSymlink != 0 {
			if entry.IsDir() {
				return filepath.SkipDir
			}
			return nil
		}
		match := pattern.FindStringSubmatch(entry.Name())
		if len(match) == 2 {
			var value int
			_, _ = fmt.Sscanf(match[1], "%d", &value)
			largest = maxInt(largest, value)
		}
		return nil
	})
	if err != nil {
		return "", workflowError("MODEL_MISMATCH", err.Error())
	}
	value := maxInt(largest, stateInt(counters[kind])) + 1
	counters[kind] = value
	encoded, _ := json.Marshal(counters)
	if err := workspace.atomicWrite(countersPath, append(encoded, '\n')); err != nil {
		return "", err
	}
	return fmt.Sprintf("%s%0*d", prefix, width, value), nil
}

func inspectCurrentSpecs(workspace methodWorkspace) (map[string][]byte, error) {
	if err := workspace.validateWorkspacePath(workspace.currentSpec); err != nil {
		return nil, err
	}
	manifestPath := filepath.Join(workspace.currentSpec, "MANIFEST.json")
	manifestInfo, err := os.Lstat(manifestPath)
	if err != nil || manifestInfo.Mode()&os.ModeSymlink != 0 || !manifestInfo.Mode().IsRegular() {
		return nil, workflowError("SPEC_BASE_MANIFEST_MISSING", "specs atuais legadas exigem manifesto explícito antes de change schema 2")
	}
	manifest, err := decodeJSONObjectFromFile(manifestPath)
	if err != nil {
		return nil, workflowError("SPEC_MANIFEST_INVALID", err.Error())
	}
	if stateInt(manifest["schema_version"]) != 1 || stateInt(manifest["spec_contract"]) != 1 {
		return nil, workflowError("SPEC_CONTRACT_UNSUPPORTED", "manifesto exige spec_contract 1")
	}
	result := map[string][]byte{}
	declared := map[string]bool{"MANIFEST.json": true}
	for _, rawSpec := range stateArray(manifest["specs"]) {
		spec := stateObject(rawSpec)
		relative := stateString(spec["path"])
		if err := validateSpecRelativePath(relative); err != nil {
			return nil, err
		}
		if declared[relative] {
			return nil, workflowError("SPEC_MANIFEST_INVALID", "path de spec duplicado: "+relative)
		}
		declared[relative] = true
		path := filepath.Join(workspace.currentSpec, filepath.FromSlash(relative))
		if err := workspace.validateWorkspacePath(path); err != nil {
			return nil, workflowError("SPEC_SYMLINK", "spec atual contém symlink: "+relative)
		}
		info, err := os.Lstat(path)
		if err != nil || info.Mode()&os.ModeSymlink != 0 || !info.Mode().IsRegular() {
			return nil, workflowError("SPEC_PATH_INVALID", "spec atual ausente: "+relative)
		}
		content, err := os.ReadFile(path)
		if err != nil || !validUTF8Text(content) || len(content) == 0 {
			return nil, workflowError("SPEC_CONTENT_INVALID", "spec atual inválida: "+relative)
		}
		result[relative] = content
	}
	err = filepath.WalkDir(workspace.currentSpec, func(path string, entry fs.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if path == workspace.currentSpec {
			return nil
		}
		relative, _ := filepath.Rel(workspace.currentSpec, path)
		relative = filepath.ToSlash(relative)
		if entry.Type()&os.ModeSymlink != 0 {
			return workflowError("SPEC_SYMLINK", "specs atuais contêm symlink: "+relative)
		}
		if !entry.IsDir() && !declared[relative] {
			return workflowError("SPEC_BASE_MANIFEST_MISMATCH", "paths do manifesto da base não correspondem às specs aceitas")
		}
		return nil
	})
	if err != nil {
		return nil, err
	}
	return result, nil
}

func validateSpecRelativePath(path string) error {
	if path == "" || strings.Contains(path, "\\") || filepath.IsAbs(path) || filepath.ToSlash(filepath.Clean(path)) != path {
		return workflowError("SPEC_PATH_INVALID", "path de spec inválido: "+path)
	}
	for _, part := range strings.Split(path, "/") {
		if part == "" || part == "." || part == ".." || strings.EqualFold(part, ".planning") {
			return workflowError("SPEC_PATH_INVALID", "path de spec inválido: "+path)
		}
	}
	return nil
}

func decodeJSONObjectFromFile(path string) (map[string]any, error) {
	content, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	return decodeJSONObject(content)
}

func locateChangeDirectory(workspace methodWorkspace, reference string) (string, error) {
	var directory string
	if regexp.MustCompile(`^C\d{3}$`).MatchString(reference) {
		matches, _ := filepath.Glob(filepath.Join(workspace.changes, reference+"-*"))
		if len(matches) != 1 {
			return "", workflowError("MODEL_MISMATCH", reference+" deve localizar exatamente uma mudança")
		}
		directory = matches[0]
	} else if regexp.MustCompile(`^C\d{3}-[a-z0-9]+(?:-[a-z0-9]+)*$`).MatchString(reference) {
		directory = filepath.Join(workspace.changes, reference)
	} else {
		return "", workflowError("MODEL_MISMATCH", "ID de mudança inválido: "+reference)
	}
	if err := workspace.validateWorkspacePath(directory); err != nil {
		return "", err
	}
	info, err := os.Lstat(directory)
	if err != nil || info.Mode()&os.ModeSymlink != 0 || !info.IsDir() {
		return "", workflowError("MODEL_MISMATCH", "mudança não encontrada: "+reference)
	}
	return directory, nil
}

func modelSlug(value string) (string, error) {
	normalized := norm.NFKD.String(value)
	var builder strings.Builder
	previousDash := false
	for _, runeValue := range strings.ToLower(normalized) {
		if unicode.Is(unicode.Mn, runeValue) {
			continue
		}
		if runeValue >= 'a' && runeValue <= 'z' || runeValue >= '0' && runeValue <= '9' {
			builder.WriteRune(runeValue)
			previousDash = false
		} else if !previousDash && builder.Len() > 0 {
			builder.WriteByte('-')
			previousDash = true
		}
	}
	slug := strings.Trim(builder.String(), "-")
	if slug == "" {
		return "", workflowError("MODEL_MISMATCH", "slug da mudança é obrigatório")
	}
	runes := []rune(slug)
	if len(runes) > 48 {
		slug = strings.TrimRight(string(runes[:48]), "-")
	}
	return slug, nil
}

func hasLegacyBianchiniArtifacts(root string) (bool, error) {
	for _, relative := range []string{
		"docs/living/PROJECT_STATE.md", "docs/bianchini", "artifacts/bianchini", ".superpowers/bianchini/direct",
	} {
		if _, err := os.Lstat(filepath.Join(root, filepath.FromSlash(relative))); err == nil {
			return true, nil
		}
	}
	designRoot := filepath.Join(root, "docs", "design")
	entries, err := os.ReadDir(designRoot)
	if os.IsNotExist(err) {
		return false, nil
	}
	if err != nil {
		return false, workflowError("MIGRATION_REQUIRED", err.Error())
	}
	for _, entry := range entries {
		if entry.Type()&os.ModeSymlink != 0 {
			return false, workflowError("MIGRATION_REQUIRED", "symlink não permitido: "+filepath.Join(designRoot, entry.Name()))
		}
		if !entry.IsDir() {
			continue
		}
		manifestPath := filepath.Join(designRoot, entry.Name(), "DESIGN_MANIFEST.json")
		info, err := os.Lstat(manifestPath)
		if err != nil || info.Mode()&os.ModeSymlink != 0 || !info.Mode().IsRegular() {
			continue
		}
		manifest, err := decodeJSONObjectFromFile(manifestPath)
		if err == nil && stateInt(manifest["schema_version"]) == 1 {
			return true, nil
		}
	}
	return false, nil
}

func missingMapKeys(value map[string]any, required []string) []string {
	missing := make([]string, 0)
	for _, key := range required {
		if _, ok := value[key]; !ok {
			missing = append(missing, key)
		}
	}
	sort.Strings(missing)
	return missing
}
