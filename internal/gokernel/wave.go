package gokernel

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
)

var (
	waveChangePrefix = regexp.MustCompile(`^C[0-9]{3}$`)
	waveChangeFull   = regexp.MustCompile(`^C[0-9]{3}-[a-z0-9]+(?:-[a-z0-9]+)*$`)
	wavePlanID       = regexp.MustCompile(`^P[0-9]{2,}$`)
	waveTaskID       = regexp.MustCompile(`^T[0-9]{2,}$`)
	waveDigest       = regexp.MustCompile(`^[0-9a-f]{64}$`)
)

var wavePlanResultFields = []string{
	"schema_version", "change", "plan", "status", "result", "promised_delta_digest",
	"actual_delta", "actual_delta_digest", "model_before_digest", "model_after_digest",
	"verification", "completed_tasks", "impact", "completed_at",
}

var waveTaskResultFields = []string{
	"schema_version", "change", "plan", "task", "status", "expected_result", "result",
	"covers", "verification", "pack_identity", "pack_digest", "package_digest", "completed_at",
}

func waveError(code, message string) error { return workflowError(code, message) }

func waveStableDigest(value any) string {
	encoded, _ := canonicalJSON(value)
	return sha256Bytes(encoded)
}

func waveNonemptyText(value any) bool {
	text, ok := value.(string)
	return ok && text != "" && text == strings.TrimSpace(text)
}

func waveEvidence(value any) bool {
	items, ok := value.([]any)
	if !ok || len(items) == 0 {
		return false
	}
	for _, item := range items {
		if !waveNonemptyText(item) {
			return false
		}
	}
	return true
}

func waveRoot(repo string) (string, error) {
	if err := rejectForeignNamespace(repo, "repo"); err != nil {
		return "", waveError("PATH_UNSAFE", "repo usa namespace estrangeiro")
	}
	root, err := filepath.Abs(repo)
	if err != nil {
		return "", waveError("WAVE_INCOMPLETE", "repo 0.4 exige .bianchini")
	}
	info, err := os.Lstat(root)
	if err != nil || info.Mode()&os.ModeSymlink != 0 || !info.IsDir() {
		if err == nil && info.Mode()&os.ModeSymlink != 0 {
			return "", waveError("PATH_UNSAFE", "repo não pode ser symlink")
		}
		return "", waveError("WAVE_INCOMPLETE", "repo 0.4 exige .bianchini")
	}
	workspace := filepath.Join(root, ".bianchini")
	workspaceInfo, err := os.Lstat(workspace)
	if err != nil || workspaceInfo.Mode()&os.ModeSymlink != 0 || !workspaceInfo.IsDir() {
		if err == nil && workspaceInfo.Mode()&os.ModeSymlink != 0 {
			return "", waveError("PATH_UNSAFE", ".bianchini atravessa symlink: "+workspace)
		}
		return "", waveError("WAVE_INCOMPLETE", "repo 0.4 exige .bianchini")
	}
	return filepath.Clean(root), nil
}

func waveConfined(root, path, label string) (string, error) {
	if err := rejectForeignNamespace(path, label); err != nil {
		return "", waveError("PATH_UNSAFE", label+" usa namespace estrangeiro")
	}
	if !filepath.IsAbs(path) {
		path = filepath.Join(root, path)
	}
	absolute, err := filepath.Abs(path)
	if err != nil {
		return "", waveError("PATH_UNSAFE", label+" sai do repo")
	}
	relative, err := filepath.Rel(root, absolute)
	if err != nil || relative == ".." || strings.HasPrefix(relative, ".."+string(filepath.Separator)) || filepath.IsAbs(relative) {
		return "", waveError("PATH_UNSAFE", label+" sai do repo")
	}
	cursor := root
	for _, part := range strings.Split(relative, string(filepath.Separator)) {
		if part == "" || part == "." || part == ".." {
			return "", waveError("PATH_UNSAFE", label+" contém traversal")
		}
		cursor = filepath.Join(cursor, part)
		info, statErr := os.Lstat(cursor)
		if statErr == nil && info.Mode()&os.ModeSymlink != 0 {
			return "", waveError("PATH_UNSAFE", label+" atravessa symlink: "+cursor)
		}
		if statErr != nil && !os.IsNotExist(statErr) {
			return "", waveError("PATH_UNSAFE", label+" não pode ser inspecionado")
		}
	}
	return filepath.Clean(absolute), nil
}

func waveSafeFile(root, path, label string) (string, error) {
	path, err := waveConfined(root, path, label)
	if err != nil {
		return "", err
	}
	info, err := os.Lstat(path)
	if err != nil || !info.Mode().IsRegular() {
		return "", waveError("WAVE_INCOMPLETE", label+" ausente")
	}
	return path, nil
}

func waveChildren(root, directory, label string) ([]string, error) {
	directory, err := waveConfined(root, directory, label)
	if err != nil {
		return nil, err
	}
	info, err := os.Lstat(directory)
	if err != nil || !info.IsDir() {
		return nil, waveError("WAVE_INCOMPLETE", label+" ausente")
	}
	entries, err := os.ReadDir(directory)
	if err != nil {
		return nil, waveError("WAVE_INCOMPLETE", label+" não pode ser lido")
	}
	result := make([]string, 0, len(entries))
	for _, entry := range entries {
		path := filepath.Join(directory, entry.Name())
		if entry.Type()&os.ModeSymlink != 0 {
			return nil, waveError("PATH_UNSAFE", label+" contém symlink: "+entry.Name())
		}
		result = append(result, path)
	}
	sort.Strings(result)
	return result, nil
}

func waveFrontmatter(root, path, label string) (map[string]any, error) {
	path, err := waveSafeFile(root, path, label)
	if err != nil {
		return nil, err
	}
	content, err := os.ReadFile(path)
	if err != nil || !validUTF8Text(content) {
		return nil, waveError("WAVE_INCOMPLETE", label+" não pode ser lido")
	}
	match := frontmatterPattern.FindSubmatch(content)
	if match == nil {
		return nil, waveError("WAVE_INCOMPLETE", label+" exige frontmatter JSON")
	}
	decoder := json.NewDecoder(bytes.NewReader(match[1]))
	decoder.UseNumber()
	var raw any
	err = decoder.Decode(&raw)
	if err != nil {
		return nil, waveError("WAVE_INCOMPLETE", fmt.Sprintf("%s possui JSON inválido na linha %d", label, jsonErrorLine(match[1], err)))
	}
	if err := decoder.Decode(&struct{}{}); err != io.EOF {
		return nil, waveError("WAVE_INCOMPLETE", label+" possui dados extras no frontmatter JSON")
	}
	value, ok := raw.(map[string]any)
	if !ok {
		return nil, waveError("WAVE_INCOMPLETE", label+" exige objeto")
	}
	return value, nil
}

func waveChangeDirectory(root, reference string) (string, error) {
	if !waveChangePrefix.MatchString(reference) && !waveChangeFull.MatchString(reference) {
		return "", waveError("WAVE_INCOMPLETE", "ID de mudança inválido: "+reference)
	}
	children, err := waveChildren(root, filepath.Join(root, ".bianchini", "changes"), "changes")
	if err != nil {
		return "", err
	}
	candidates := []string{}
	for _, child := range children {
		info, statErr := os.Lstat(child)
		if statErr != nil || !info.IsDir() {
			continue
		}
		name := filepath.Base(child)
		if name == reference || waveChangePrefix.MatchString(reference) && strings.HasPrefix(name, reference+"-") {
			candidates = append(candidates, child)
		}
	}
	if len(candidates) != 1 {
		return "", waveError("WAVE_INCOMPLETE", fmt.Sprintf("%s exige uma mudança; encontradas %d", reference, len(candidates)))
	}
	return candidates[0], nil
}

func waveRoadmapPlans(root, change string) ([]planContract, []string, error) {
	roadmap, err := waveFrontmatter(root, filepath.Join(change, "ROADMAP.md"), "ROADMAP.md")
	if err != nil {
		return nil, nil, err
	}
	if stateInt(roadmap["schema_version"]) != 1 || stateInt(roadmap["planning_contract"]) != 2 {
		return nil, nil, waveError("WAVE_INCOMPLETE", "ROADMAP.md exige contrato de planejamento 2")
	}
	phases, ok := roadmap["phases"].([]any)
	if !ok || len(phases) == 0 {
		return nil, nil, waveError("WAVE_INCOMPLETE", "ROADMAP.md.phases exige lista não vazia")
	}
	phaseIDs, phaseValues, seen := []string{}, map[string]map[string]any{}, map[string]bool{}
	for _, raw := range phases {
		phase, ok := raw.(map[string]any)
		if !ok {
			return nil, nil, waveError("WAVE_INCOMPLETE", "ROADMAP.md possui fase inválida")
		}
		identifier := stateString(phase["id"])
		if !wavePlanID.MatchString(identifier) {
			return nil, nil, waveError("WAVE_INCOMPLETE", "ROADMAP.md possui ID de plano inválido")
		}
		if seen[identifier] {
			return nil, nil, waveError("WAVE_INCOMPLETE", "ROADMAP.md possui plano duplicado")
		}
		seen[identifier] = true
		phaseIDs = append(phaseIDs, identifier)
		phaseValues[identifier] = phase
	}
	children, err := waveChildren(root, filepath.Join(change, "plans"), "plans")
	if err != nil {
		return nil, nil, err
	}
	actual := []string{}
	byID := map[string]string{}
	for _, child := range children {
		info, _ := os.Lstat(child)
		name := filepath.Base(child)
		if !info.Mode().IsRegular() || filepath.Ext(name) != ".md" || !strings.HasPrefix(name, "P") {
			continue
		}
		identifier, valid := planFileID(name)
		if !valid {
			return nil, nil, waveError("WAVE_INCOMPLETE", "arquivo de plano com identidade inválida: "+name)
		}
		if _, duplicate := byID[identifier]; duplicate {
			return nil, nil, waveError("WAVE_INCOMPLETE", "arquivos de plano duplicam identidade: "+identifier)
		}
		actual = append(actual, identifier)
		byID[identifier] = child
	}
	expectedFiles := append([]string{}, phaseIDs...)
	sort.Strings(expectedFiles)
	if !sameStrings(actual, expectedFiles) {
		return nil, nil, waveError("WAVE_INCOMPLETE", "ROADMAP.md diverge dos arquivos de plano")
	}
	plans := make([]planContract, 0, len(phaseIDs))
	for _, identifier := range phaseIDs {
		value, loadErr := waveFrontmatter(root, byID[identifier], "plano "+identifier)
		if loadErr != nil {
			return nil, nil, loadErr
		}
		plan, loadErr := parsePlanContract(value)
		if loadErr != nil {
			return nil, nil, waveError("WAVE_INCOMPLETE", "plano "+identifier+" inválido: "+loadErr.Error())
		}
		if plan.id != identifier {
			return nil, nil, waveError("WAVE_INCOMPLETE", "arquivo "+filepath.Base(byID[identifier])+" diverge do id "+plan.id)
		}
		expected := map[string]any{
			"id": plan.id, "result": strings.TrimSpace(stateString(plan.value["result"])), "depends_on": normalizedPlanStrings(plan, "depends_on"),
			"requirements": normalizedPlanStrings(plan, "requirements"), "execution": stateString(plan.value["execution"]),
			"tasks": planTaskIDs(plan),
		}
		observed := map[string]any{}
		for key := range expected {
			observed[key] = phaseValues[identifier][key]
		}
		if !mapsEqual(observed, expected) {
			return nil, nil, waveError("WAVE_INCOMPLETE", "ROADMAP.md diverge do plano "+identifier)
		}
		plans = append(plans, plan)
	}
	if err := validateWaveDependencies(plans); err != nil {
		return nil, nil, err
	}
	return plans, phaseIDs, nil
}

func validateWaveDependencies(plans []planContract) error {
	known := map[string]bool{}
	for _, plan := range plans {
		if known[plan.id] {
			return waveError("WAVE_INCOMPLETE", "ID de plano duplicado: "+plan.id)
		}
		known[plan.id] = true
	}
	dependencies := map[string][]string{}
	for _, plan := range plans {
		dependencies[plan.id] = normalizedPlanStrings(plan, "depends_on")
		for _, dependency := range dependencies[plan.id] {
			if !known[dependency] {
				return waveError("WAVE_INCOMPLETE", plan.id+" depende de plano inexistente: "+dependency)
			}
		}
		if plan.schema == 2 {
			tasks := planTasks(plan)
			taskKnown := map[string]bool{}
			for _, task := range tasks {
				taskKnown[stateString(task["id"])] = true
			}
			for _, task := range tasks {
				for _, dependency := range normalizedTaskStrings(task, "depends_on") {
					if !taskKnown[dependency] {
						return waveError("WAVE_INCOMPLETE", stateString(task["id"])+" depende de tarefa inexistente: "+dependency)
					}
				}
			}
			if hasDependencyCycle(taskDependencyMap(tasks)) {
				return waveError("WAVE_INCOMPLETE", "ciclo entre tarefas de "+plan.id)
			}
		}
	}
	if hasDependencyCycle(dependencies) {
		return waveError("WAVE_INCOMPLETE", "ciclo entre planos")
	}
	return nil
}

func hasDependencyCycle(dependencies map[string][]string) bool {
	visiting, visited := map[string]bool{}, map[string]bool{}
	var visit func(string) bool
	visit = func(identifier string) bool {
		if visiting[identifier] {
			return true
		}
		if visited[identifier] {
			return false
		}
		visiting[identifier] = true
		for _, dependency := range dependencies[identifier] {
			if visit(dependency) {
				return true
			}
		}
		delete(visiting, identifier)
		visited[identifier] = true
		return false
	}
	for identifier := range dependencies {
		if visit(identifier) {
			return true
		}
	}
	return false
}

func waveValidateApproval(coherence map[string]any) (string, map[string]bool, error) {
	if !oneOf(stateString(coherence["status"]), "approved", "approved_with_stale") {
		return "", nil, waveError("WAVE_NOT_APPROVED", "próxima onda exige pacote aprovado")
	}
	digest := stateString(coherence["digest"])
	if !waveDigest.MatchString(digest) {
		return "", nil, waveError("WAVE_INCOMPLETE", "COHERENCE.md possui digest inválido")
	}
	approval, ok := coherence["approval"].(map[string]any)
	if !ok || stateString(approval["digest"]) != digest {
		return "", nil, waveError("WAVE_INCOMPLETE", "COHERENCE.md não vincula aprovação ao pacote")
	}
	if !waveNonemptyText(approval["approved_by"]) || !waveNonemptyText(approval["approved_at"]) {
		return "", nil, waveError("WAVE_INCOMPLETE", "COHERENCE.md possui aprovação incompleta")
	}
	staleValues, ok := coherence["stale_plans"].([]any)
	if coherence["stale_plans"] == nil {
		staleValues, ok = []any{}, true
	}
	if !ok {
		return "", nil, waveError("WAVE_INCOMPLETE", "COHERENCE.md.stale_plans exige lista")
	}
	stale := map[string]bool{}
	for _, raw := range staleValues {
		value, ok := raw.(string)
		if !ok {
			return "", nil, waveError("WAVE_INCOMPLETE", "COHERENCE.md.stale_plans exige lista")
		}
		stale[value] = true
	}
	return digest, stale, nil
}

func waveArtifactManifest(root, change string, coherence map[string]any, planIDs []string) (map[string]string, error) {
	manifest, ok := coherence["artifact_manifest"].(map[string]any)
	if !ok {
		return nil, waveError("WAVE_INCOMPLETE", "pacote aprovado exige artifact_manifest")
	}
	required := []string{"SCOPE.md", "RESEARCH.md", "ARCHITECTURE.md", "SYSTEM_MODEL.md", "ROADMAP.md"}
	planFiles := map[string]string{}
	for relative := range manifest {
		if !strings.HasPrefix(relative, "plans/") {
			continue
		}
		identifier, valid := planFileID(strings.TrimPrefix(relative, "plans/"))
		if !valid || strings.Count(relative, "/") != 1 {
			return nil, waveError("WAVE_INCOMPLETE", "arquivo de plano com identidade inválida no artifact_manifest: "+relative)
		}
		if _, duplicate := planFiles[identifier]; duplicate {
			return nil, waveError("WAVE_INCOMPLETE", "artifact_manifest duplica identidade de plano: "+identifier)
		}
		planFiles[identifier] = relative
	}
	for _, identifier := range planIDs {
		relative, exists := planFiles[identifier]
		if !exists {
			return nil, waveError("WAVE_INCOMPLETE", "artifact_manifest não contém o plano "+identifier)
		}
		required = append(required, relative)
	}
	requiredSet := stringSet(required)
	if len(manifest) != len(required) || len(unknownMapKeys(manifest, requiredSet)) > 0 || len(missingMapKeys(manifest, required)) > 0 {
		missing, extra := missingMapKeys(manifest, required), unknownMapKeys(manifest, requiredSet)
		details := []string{}
		if len(missing) > 0 {
			details = append(details, "ausentes: "+strings.Join(missing, ", "))
		}
		if len(extra) > 0 {
			details = append(details, "desconhecidos: "+strings.Join(extra, ", "))
		}
		return nil, waveError("WAVE_INCOMPLETE", "artifact_manifest diverge do pacote ("+strings.Join(details, "; ")+")")
	}
	actual := map[string]string{}
	for _, relative := range required {
		expected := stateString(manifest[relative])
		if !waveDigest.MatchString(expected) {
			return nil, waveError("WAVE_INCOMPLETE", "digest inválido no artifact_manifest: "+relative)
		}
		path, err := waveSafeFile(root, filepath.Join(change, filepath.FromSlash(relative)), "artefato "+relative)
		if err != nil {
			return nil, err
		}
		content, err := os.ReadFile(path)
		if err != nil {
			return nil, waveError("WAVE_INCOMPLETE", "artefato "+relative+" não pode ser lido")
		}
		digest := sha256Bytes(content)
		if digest != expected {
			return nil, waveError("WAVE_INCOMPLETE", "pacote aprovado sofreu drift: "+relative)
		}
		actual[relative] = digest
	}
	return actual, nil
}

func waveValidateCurrentPackage(root, change string, coherence map[string]any, plans []planContract, artifactManifest map[string]string) (string, error) {
	if stateInt(coherence["schema_version"]) != 2 || stateInt(coherence["planning_contract"]) != 2 || stateInt(coherence["spec_contract"]) != 1 || stateString(coherence["change"]) != filepath.Base(change) {
		return "", waveError("WAVE_INCOMPLETE", "próxima onda exige COHERENCE schema 2, planning_contract 2 e spec_contract 1")
	}
	findings, findingsOK := coherence["findings"].([]any)
	semantic, semanticOK := coherence["semantic"].(map[string]any)
	if !findingsOK || !semanticOK {
		return "", waveError("WAVE_INCOMPLETE", "pacote aprovado possui revisão incompleta")
	}
	currentPath, err := waveSafeFile(root, filepath.Join(root, ".bianchini", "current", "SYSTEM_MODEL.md"), "SYSTEM_MODEL atual")
	if err != nil {
		return "", err
	}
	expectedPath, err := waveSafeFile(root, filepath.Join(change, "SYSTEM_MODEL.md"), "SYSTEM_MODEL esperado")
	if err != nil {
		return "", err
	}
	current, err := loadProjectModel(currentPath)
	if err != nil {
		return "", waveError("WAVE_INCOMPLETE", "ProjectModel inválido: "+err.Error())
	}
	expected, err := loadProjectModel(expectedPath)
	if err != nil {
		return "", waveError("WAVE_INCOMPLETE", "ProjectModel inválido: "+err.Error())
	}
	workspace := newMethodWorkspace(root)
	specDigests, err := loadModelSpecPackage(workspace, change, coherence)
	if err != nil {
		return "", waveError("WAVE_INCOMPLETE", err.Error())
	}
	for key, value := range specDigests {
		matches := stateString(coherence[key]) == stateString(value)
		if key == "spec_contract" {
			matches = stateInt(coherence[key]) == stateInt(value)
		}
		if !matches {
			return "", waveError("WAVE_INCOMPLETE", "digests do pacote de specs sofreram drift")
		}
	}
	reviewInput := waveStableDigest(map[string]any{
		"planning_contract": 2, "artifact_manifest": artifactManifest,
		"spec_package": specDigests,
	})
	if stateString(coherence["review_input_digest"]) != reviewInput {
		return "", waveError("WAVE_INCOMPLETE", "entrada aprovada de revisão sofreu drift")
	}
	planMappings := make([]any, 0, len(plans))
	for _, plan := range plans {
		planMappings = append(planMappings, canonicalPlanMapping(plan))
	}
	packageDigest := waveStableDigest(map[string]any{
		"current": current.mapping(), "expected": expected.mapping(), "plans": planMappings,
		"findings": findings, "semantic": semantic, "planning_contract": 2,
		"artifact_manifest": artifactManifest, "spec_package": specDigests,
	})
	if stateString(coherence["digest"]) != packageDigest {
		return "", waveError("WAVE_INCOMPLETE", "digest aprovado não corresponde ao pacote atual")
	}
	return packageDigest, nil
}

func waveValidateState(root, change, packageDigest string) (map[string]any, error) {
	state, err := waveFrontmatter(root, filepath.Join(root, ".bianchini", "STATE.md"), "STATE.md")
	if err != nil {
		return nil, err
	}
	if stateInt(state["schema_version"]) != 1 || stateString(state["method"]) != "0.4" {
		return nil, waveError("WAVE_INCOMPLETE", "STATE.md possui contrato inválido")
	}
	if stateString(state["digest"]) != packageDigest {
		return nil, waveError("WAVE_INCOMPLETE", "STATE.md não referencia o pacote aprovado atual")
	}
	active, ok := state["active_work"].(map[string]any)
	if !ok || stateString(active["kind"]) != "change" || stateString(active["id"]) != filepath.Base(change) {
		return nil, waveError("WAVE_INCOMPLETE", "STATE.md não referencia a mudança aprovada")
	}
	approved := []string{"approved", "approved_with_stale", "executing", "blocked", "pending_close"}
	if !oneOf(stateString(state["status"]), approved...) || !oneOf(stateString(active["status"]), approved...) {
		return nil, waveError("WAVE_NOT_APPROVED", "STATE.md não está no ciclo do pacote aprovado")
	}
	expectedPointer := ".bianchini/changes/" + filepath.Base(change) + "/COHERENCE.md"
	pointers, ok := state["pointers"].(map[string]any)
	if !ok || stateString(pointers["coherence"]) != expectedPointer {
		return nil, waveError("WAVE_INCOMPLETE", "STATE.md não aponta para o COHERENCE aprovado")
	}
	if _, err := waveSafeFile(root, filepath.Join(root, filepath.FromSlash(expectedPointer)), "COHERENCE apontado por STATE.md"); err != nil {
		return nil, err
	}
	return state, nil
}

func waveCompletedResults(root, change string, plans []planContract, packageDigest string) (map[string]bool, map[string]map[string]bool, error) {
	known := map[string]planContract{}
	completedPlans := map[string]bool{}
	completedTasks := map[string]map[string]bool{}
	for _, plan := range plans {
		known[plan.id] = plan
		completedTasks[plan.id] = map[string]bool{}
	}
	results := filepath.Join(change, "results")
	if _, err := waveConfined(root, results, "results"); err != nil {
		return nil, nil, err
	}
	if info, err := os.Lstat(results); err == nil {
		if !info.IsDir() {
			return nil, nil, waveError("WAVE_INCOMPLETE", "results deve ser diretório")
		}
		children, err := waveChildren(root, results, "results")
		if err != nil {
			return nil, nil, err
		}
		for _, child := range children {
			info, _ := os.Lstat(child)
			identifier := strings.TrimSuffix(filepath.Base(child), filepath.Ext(child))
			if !info.Mode().IsRegular() || !wavePlanID.MatchString(identifier) {
				continue
			}
			plan, exists := known[identifier]
			if !exists {
				return nil, nil, waveError("WAVE_INCOMPLETE", "resultado pertence a plano desconhecido: "+identifier)
			}
			value, err := waveFrontmatter(root, child, "resultado "+identifier)
			if err != nil {
				return nil, nil, err
			}
			if err := waveValidatePlanResult(value, plan, filepath.Base(change)); err != nil {
				return nil, nil, err
			}
			completedPlans[identifier] = true
		}
	}
	tasksRoot := filepath.Join(results, "tasks")
	if _, err := os.Lstat(tasksRoot); err == nil {
		planDirectories, err := waveChildren(root, tasksRoot, "resultados de tarefas")
		if err != nil {
			return nil, nil, err
		}
		for _, planDirectory := range planDirectories {
			info, _ := os.Lstat(planDirectory)
			plan, exists := known[filepath.Base(planDirectory)]
			if !info.IsDir() || !exists {
				return nil, nil, waveError("WAVE_INCOMPLETE", "resultado de tarefa pertence a plano desconhecido: "+filepath.Base(planDirectory))
			}
			tasks := map[string]map[string]any{}
			for _, task := range planTasks(plan) {
				tasks[stateString(task["id"])] = task
			}
			children, err := waveChildren(root, planDirectory, "tarefas de "+plan.id)
			if err != nil {
				return nil, nil, err
			}
			for _, child := range children {
				childInfo, _ := os.Lstat(child)
				identifier := strings.TrimSuffix(filepath.Base(child), filepath.Ext(child))
				if !childInfo.Mode().IsRegular() || filepath.Ext(child) != ".md" || !waveTaskID.MatchString(identifier) {
					return nil, nil, waveError("WAVE_INCOMPLETE", "resultado de tarefa inválido: "+filepath.Base(child))
				}
				task, exists := tasks[identifier]
				if !exists {
					return nil, nil, waveError("WAVE_INCOMPLETE", "resultado pertence a tarefa desconhecida: "+plan.id+"/"+identifier)
				}
				value, err := waveFrontmatter(root, child, "resultado "+plan.id+"/"+identifier)
				if err != nil {
					return nil, nil, err
				}
				if err := waveValidateTaskResult(value, filepath.Base(change), plan.id, task, packageDigest); err != nil {
					return nil, nil, err
				}
				completedTasks[plan.id][identifier] = true
			}
		}
	}
	for planID := range completedPlans {
		plan := known[planID]
		if plan.schema != 2 {
			continue
		}
		missing := []string{}
		for _, identifier := range planTaskIDs(plan) {
			if !completedTasks[planID][identifier] {
				missing = append(missing, identifier)
			}
		}
		if len(missing) > 0 {
			return nil, nil, waveError("WAVE_INCOMPLETE", "resultado de "+planID+" não possui evidência das tarefas: "+strings.Join(missing, ", "))
		}
	}
	return completedPlans, completedTasks, nil
}

func waveValidatePlanResult(value map[string]any, plan planContract, change string) error {
	if !hasExactKeys(value, wavePlanResultFields) {
		return waveError("WAVE_INCOMPLETE", "resultado de "+plan.id+" possui shape não canônico")
	}
	if stateInt(value["schema_version"]) != 1 || stateString(value["change"]) != change || stateString(value["plan"]) != plan.id || stateString(value["status"]) != "completed" || !waveNonemptyText(value["result"]) || !waveNonemptyText(value["completed_at"]) {
		return waveError("WAVE_INCOMPLETE", "resultado inválido de "+plan.id)
	}
	if !waveEvidence(value["verification"]) {
		return waveError("WAVE_INCOMPLETE", "resultado de "+plan.id+" não possui verificação")
	}
	actual, ok := value["actual_delta"].(map[string]any)
	if !ok || !mapsEqual(actual, plan.modelDelta) {
		return waveError("WAVE_INCOMPLETE", "resultado de "+plan.id+" diverge do delta aprovado")
	}
	if stateString(value["promised_delta_digest"]) != waveStableDigest(plan.modelDelta) {
		return waveError("WAVE_INCOMPLETE", "resultado de "+plan.id+" alterou o delta prometido")
	}
	if stateString(value["actual_delta_digest"]) != waveStableDigest(actual) {
		return waveError("WAVE_INCOMPLETE", "resultado de "+plan.id+" possui digest de delta inválido")
	}
	for _, field := range []string{"model_before_digest", "model_after_digest"} {
		if !waveDigest.MatchString(stateString(value[field])) {
			return waveError("WAVE_INCOMPLETE", "resultado de "+plan.id+" possui "+field+" inválido")
		}
	}
	if len(actual) == 0 && value["model_before_digest"] != value["model_after_digest"] {
		return waveError("WAVE_INCOMPLETE", "resultado de "+plan.id+" forjou mudança de modelo")
	}
	completedTasks, ok := waveExactStringList(value["completed_tasks"])
	if !ok || !sameStrings(completedTasks, planTaskIDs(plan)) {
		return waveError("WAVE_INCOMPLETE", "resultado de "+plan.id+" não comprova todas as tarefas")
	}
	expectedImpact := map[string]any{"radius": "local", "stale_plans": []any{}, "reason": "entrega equivalente ao delta aprovado"}
	impact, ok := value["impact"].(map[string]any)
	if !ok || !mapsEqual(impact, expectedImpact) {
		return waveError("WAVE_INCOMPLETE", "resultado de "+plan.id+" possui impacto não canônico")
	}
	return nil
}

func waveValidateTaskResult(value map[string]any, change, planID string, task map[string]any, packageDigest string) error {
	taskID := stateString(task["id"])
	identity := planID + "/" + taskID
	packIdentity := strings.SplitN(change, "-", 2)[0] + "/" + identity
	if !hasExactKeys(value, waveTaskResultFields) {
		return waveError("WAVE_INCOMPLETE", "resultado de "+identity+" possui shape não canônico")
	}
	covers, coversOK := waveExactStringList(value["covers"])
	if stateInt(value["schema_version"]) != 1 || stateString(value["change"]) != change || stateString(value["plan"]) != planID || stateString(value["task"]) != taskID || stateString(value["status"]) != "completed" || value["expected_result"] != strings.TrimSpace(stateString(task["result"])) || !coversOK || !sameStrings(covers, normalizedTaskStrings(task, "covers")) || stateString(value["pack_identity"]) != packIdentity || stateString(value["package_digest"]) != packageDigest || !waveDigest.MatchString(stateString(value["pack_digest"])) || !waveNonemptyText(value["result"]) || !waveNonemptyText(value["completed_at"]) {
		return waveError("WAVE_INCOMPLETE", "resultado inválido de "+identity)
	}
	if !waveEvidence(value["verification"]) {
		return waveError("WAVE_INCOMPLETE", "resultado de "+identity+" não possui verificação")
	}
	return nil
}

func waveBlockingFindings(coherence map[string]any, planIDs []string) (map[string][]string, error) {
	findings, ok := coherence["findings"].([]any)
	if !ok {
		return nil, waveError("WAVE_INCOMPLETE", "COHERENCE.md.findings exige lista")
	}
	known := stringSet(planIDs)
	blocked := map[string][]string{}
	for _, raw := range findings {
		finding, ok := raw.(map[string]any)
		if !ok {
			return nil, waveError("WAVE_INCOMPLETE", "COHERENCE.md possui finding inválido")
		}
		if stateString(finding["status"]) != "open" || !oneOf(stateString(finding["severity"]), "ERROR", "WARNING") {
			continue
		}
		code := stateString(finding["code"])
		if code == "" {
			return nil, waveError("WAVE_INCOMPLETE", "finding bloqueante exige code")
		}
		phases, ok := finding["phases"].([]any)
		if finding["phases"] == nil {
			phases, ok = []any{}, true
		}
		if !ok {
			return nil, waveError("WAVE_INCOMPLETE", "finding "+code+" possui phases inválido")
		}
		targets := planIDs
		if len(phases) > 0 {
			targets = []string{}
			for _, rawPhase := range phases {
				phase, ok := rawPhase.(string)
				if !ok {
					return nil, waveError("WAVE_INCOMPLETE", "finding "+code+" possui phases inválido")
				}
				if !known[phase] {
					return nil, waveError("WAVE_INCOMPLETE", "finding "+code+" referencia plano inexistente")
				}
				targets = append(targets, phase)
			}
		}
		for _, target := range targets {
			blocked[target] = append(blocked[target], code)
		}
	}
	for target := range blocked {
		sort.Strings(blocked[target])
	}
	return blocked, nil
}

func projectNextWave(repo, reference string) (map[string]any, error) {
	root, err := waveRoot(repo)
	if err != nil {
		return nil, err
	}
	change, err := waveChangeDirectory(root, reference)
	if err != nil {
		return nil, err
	}
	roadmapPath, err := waveSafeFile(root, filepath.Join(change, "ROADMAP.md"), "ROADMAP.md")
	if err != nil {
		return nil, err
	}
	roadmapBytes, err := os.ReadFile(roadmapPath)
	if err != nil {
		return nil, waveError("WAVE_INCOMPLETE", "ROADMAP.md não pode ser lido")
	}
	plans, planIDs, err := waveRoadmapPlans(root, change)
	if err != nil {
		return nil, err
	}
	coherence, err := waveFrontmatter(root, filepath.Join(change, "COHERENCE.md"), "COHERENCE.md")
	if err != nil {
		return nil, err
	}
	packageDigest, stale, err := waveValidateApproval(coherence)
	if err != nil {
		return nil, err
	}
	knownPlans := stringSet(planIDs)
	for identifier := range stale {
		if !knownPlans[identifier] {
			return nil, waveError("WAVE_INCOMPLETE", "stale_plans referencia plano inexistente")
		}
	}
	manifest, err := waveArtifactManifest(root, change, coherence, planIDs)
	if err != nil {
		return nil, err
	}
	currentDigest, err := waveValidateCurrentPackage(root, change, coherence, plans, manifest)
	if err != nil {
		return nil, err
	}
	if currentDigest != packageDigest {
		return nil, waveError("WAVE_INCOMPLETE", "aprovação diverge do pacote recalculado")
	}
	state, err := waveValidateState(root, change, packageDigest)
	if err != nil {
		return nil, err
	}
	blockers, ok := state["blockers"].([]any)
	if !ok {
		return nil, waveError("WAVE_INCOMPLETE", "STATE.md.blockers exige lista")
	}
	globalBlockers := []string{}
	for _, raw := range blockers {
		value, ok := raw.(string)
		if !ok {
			return nil, waveError("WAVE_INCOMPLETE", "STATE.md.blockers exige lista")
		}
		if value != "IMPACT_STALE" {
			globalBlockers = append(globalBlockers, value)
		}
	}
	sort.Strings(globalBlockers)
	if stateString(state["status"]) == "blocked" && len(globalBlockers) == 0 {
		globalBlockers = []string{"STATE_BLOCKED"}
	}
	completedPlans, completedTasks, err := waveCompletedResults(root, change, plans, packageDigest)
	if err != nil {
		return nil, err
	}
	for identifier := range stale {
		if completedPlans[identifier] {
			return nil, waveError("WAVE_INCOMPLETE", "plano concluído não pode permanecer stale")
		}
	}
	findings, err := waveBlockingFindings(coherence, planIDs)
	if err != nil {
		return nil, err
	}
	prefix := strings.SplitN(filepath.Base(change), "-", 2)[0]
	parallel, staleUnits, blocked, waiting := []any{}, []any{}, []any{}, []any{}
	completed := []string{}
	selected := []waveResource{}
	for _, plan := range plans {
		identities := wavePlanIdentities(prefix, plan)
		if completedPlans[plan.id] {
			completed = append(completed, prefix+"/"+plan.id)
			continue
		}
		for _, taskID := range planTaskIDs(plan) {
			if completedTasks[plan.id][taskID] {
				completed = append(completed, prefix+"/"+plan.id+"/"+taskID)
			}
		}
		incomplete := []string{}
		for _, identity := range identities {
			last := identity[strings.LastIndex(identity, "/")+1:]
			if !completedTasks[plan.id][last] {
				incomplete = append(incomplete, identity)
			}
		}
		if stale[plan.id] {
			for _, identity := range incomplete {
				staleUnits = append(staleUnits, map[string]any{"identity": identity, "reason": "plan_stale"})
			}
			continue
		}
		if len(globalBlockers) > 0 {
			for _, identity := range incomplete {
				blocked = append(blocked, map[string]any{"identity": identity, "reason": "state_blocker", "details": globalBlockers})
			}
			continue
		}
		if codes := findings[plan.id]; len(codes) > 0 {
			for _, identity := range incomplete {
				blocked = append(blocked, map[string]any{"identity": identity, "reason": "open_finding", "details": codes})
			}
			continue
		}
		planDependencies := normalizedPlanStrings(plan, "depends_on")
		pendingPlans, satisfiedPlans := []string{}, []string{}
		for _, dependency := range planDependencies {
			identity := prefix + "/" + dependency
			if completedPlans[dependency] {
				satisfiedPlans = append(satisfiedPlans, identity)
			} else {
				pendingPlans = append(pendingPlans, identity)
			}
		}
		if len(pendingPlans) > 0 {
			for _, identity := range incomplete {
				waiting = append(waiting, map[string]any{"identity": identity, "reason": "plan_dependencies_pending", "pending": pendingPlans})
			}
			continue
		}
		if plan.schema == 1 {
			identity := prefix + "/" + plan.id
			parallel = append(parallel, map[string]any{"identity": identity, "plan": plan.id, "task": nil, "pack_identity": identity, "dependencies_satisfied": satisfiedPlans})
			continue
		}
		for _, task := range planTasks(plan) {
			taskID := stateString(task["id"])
			identity := prefix + "/" + plan.id + "/" + taskID
			if completedTasks[plan.id][taskID] {
				continue
			}
			pendingTasks, satisfiedTasks := []string{}, []string{}
			for _, dependency := range normalizedTaskStrings(task, "depends_on") {
				dependencyIdentity := prefix + "/" + plan.id + "/" + dependency
				if completedTasks[plan.id][dependency] {
					satisfiedTasks = append(satisfiedTasks, dependencyIdentity)
				} else {
					pendingTasks = append(pendingTasks, dependencyIdentity)
				}
			}
			if len(pendingTasks) > 0 {
				waiting = append(waiting, map[string]any{"identity": identity, "reason": "task_dependencies_pending", "pending": pendingTasks})
				continue
			}
			conflicts := waveResourceConflicts(selected, normalizedTaskStrings(task, "files"))
			if len(conflicts) > 0 {
				waiting = append(waiting, map[string]any{"identity": identity, "reason": "resource_overlap", "pending": conflicts})
				continue
			}
			dependenciesSatisfied := append(append([]string{}, satisfiedPlans...), satisfiedTasks...)
			parallel = append(parallel, map[string]any{"identity": identity, "plan": plan.id, "task": taskID, "pack_identity": identity, "dependencies_satisfied": dependenciesSatisfied})
			for _, path := range normalizedTaskStrings(task, "files") {
				selected = append(selected, waveResource{identity: identity, parts: strings.Split(filepath.ToSlash(path), "/")})
			}
		}
	}
	eligible := make([]string, 0, len(parallel))
	for _, raw := range parallel {
		eligible = append(eligible, stateString(raw.(map[string]any)["identity"]))
	}
	return map[string]any{
		"schema_version": 1, "change": filepath.Base(change), "eligible_wave": eligible,
		"parallel_units": parallel, "stale_units": staleUnits, "blocked_units": blocked,
		"waiting_units": waiting, "completed_units": completed,
		"roadmap_digest": sha256Bytes(roadmapBytes), "package_digest": packageDigest,
	}, nil
}

type waveResource struct {
	identity string
	parts    []string
}

func waveResourceConflicts(selected []waveResource, files []string) []string {
	result := []string{}
	seen := map[string]bool{}
	for _, file := range files {
		parts := strings.Split(filepath.ToSlash(file), "/")
		for _, existing := range selected {
			shared := len(parts)
			if len(existing.parts) < shared {
				shared = len(existing.parts)
			}
			matches := true
			for index := 0; index < shared; index++ {
				if parts[index] != existing.parts[index] {
					matches = false
					break
				}
			}
			if matches && !seen[existing.identity] {
				result = append(result, existing.identity)
				seen[existing.identity] = true
			}
		}
	}
	return result
}

func wavePlanIdentities(prefix string, plan planContract) []string {
	if plan.schema == 2 {
		result := []string{}
		for _, task := range planTasks(plan) {
			result = append(result, prefix+"/"+plan.id+"/"+stateString(task["id"]))
		}
		return result
	}
	return []string{prefix + "/" + plan.id}
}

func canonicalPlanMapping(plan planContract) map[string]any {
	if plan.schema == 2 {
		tasks := make([]any, 0)
		for _, task := range planTasks(plan) {
			tasks = append(tasks, canonicalTaskMapping(task))
		}
		return map[string]any{
			"schema_version": 2, "id": plan.id, "status": "planned", "result": strings.TrimSpace(stateString(plan.value["result"])),
			"requirements": normalizedPlanStrings(plan, "requirements"), "acceptance": normalizedPlanStrings(plan, "acceptance"),
			"depends_on": normalizedPlanStrings(plan, "depends_on"), "provides": normalizedPlanStrings(plan, "provides"),
			"consumes": normalizedPlanStrings(plan, "consumes"), "modules": normalizedPlanStrings(plan, "modules"),
			"interfaces": normalizedPlanStrings(plan, "interfaces"), "ownership": normalizedPlanStrings(plan, "ownership"),
			"data": normalizedPlanStrings(plan, "data"), "model_delta": cloneMap(plan.modelDelta),
			"migrations": cloneAnyList(plan.value["migrations"]), "effects": cloneAnyList(plan.value["effects"]),
			"rollback": strings.TrimSpace(stateString(plan.value["rollback"])), "verifications": normalizedPlanStrings(plan, "verifications"),
			"future_constraints": normalizedPlanStrings(plan, "future_constraints"), "execution": stateString(plan.value["execution"]),
			"review": stateString(plan.value["review"]), "tasks": tasks,
		}
	}
	return map[string]any{
		"id": plan.id, "depends_on": normalizedPlanStrings(plan, "depends_on"), "provides": normalizedPlanStrings(plan, "provides"),
		"consumes": normalizedPlanStrings(plan, "consumes"), "owns": normalizedPlanStrings(plan, "owns"), "touches": normalizedPlanStrings(plan, "touches"),
		"requirements": normalizedPlanStrings(plan, "requirements"), "acceptance": normalizedPlanStrings(plan, "acceptance"),
		"verifications": normalizedPlanStrings(plan, "verifications"), "model_delta": cloneMap(plan.modelDelta),
		"migrations": cloneAnyList(plan.value["migrations"]), "external_effects": cloneAnyList(plan.value["external_effects"]),
		"future_constraints": normalizedPlanStrings(plan, "future_constraints"),
	}
}

func canonicalTaskMapping(task map[string]any) map[string]any {
	verify := stateObject(task["verify"])
	verification := map[string]any{
		"kind": stateString(verify["kind"]), "proves": strings.TrimSpace(stateString(verify["proves"])),
	}
	if run := strings.TrimSpace(stateString(verify["run"])); run != "" {
		verification["run"] = run
	}
	if argv, err := stringValues(verify["argv"], "verify.argv"); err == nil && len(argv) > 0 {
		verification["argv"] = argv
	}
	if cwd := strings.TrimSpace(stateString(verify["cwd"])); cwd != "" {
		verification["cwd"] = cwd
	}
	if timeout := stateInt(verify["timeout_seconds"]); timeout > 0 {
		verification["timeout_seconds"] = timeout
	}
	return map[string]any{
		"id": strings.TrimSpace(stateString(task["id"])), "name": strings.TrimSpace(stateString(task["name"])),
		"result": strings.TrimSpace(stateString(task["result"])), "covers": normalizedTaskStrings(task, "covers"),
		"depends_on": normalizedTaskStrings(task, "depends_on"), "files": normalizedTaskStrings(task, "files"),
		"action": strings.TrimSpace(stateString(task["action"])),
		"verify": verification,
		"done":   strings.TrimSpace(stateString(task["done"])), "risk_seam": strings.TrimSpace(stateString(task["risk_seam"])),
	}
}

func normalizedPlanStrings(plan planContract, field string) []string {
	value := plan.value[field]
	if field == "owns" && value == nil {
		value = plan.value["ownership"]
	}
	values, _ := stringValues(value, field)
	return values
}

func normalizedTaskStrings(task map[string]any, field string) []string {
	values, _ := stringValues(task[field], field)
	return values
}

func planTasks(plan planContract) []map[string]any {
	result := []map[string]any{}
	for _, raw := range stateArray(plan.value["tasks"]) {
		result = append(result, stateObject(raw))
	}
	return result
}

func planTaskIDs(plan planContract) []string {
	result := []string{}
	for _, task := range planTasks(plan) {
		result = append(result, strings.TrimSpace(stateString(task["id"])))
	}
	return result
}

func waveExactStringList(raw any) ([]string, bool) {
	values, ok := raw.([]any)
	if !ok {
		return nil, false
	}
	result := make([]string, 0, len(values))
	for _, rawValue := range values {
		value, ok := rawValue.(string)
		if !ok {
			return nil, false
		}
		result = append(result, value)
	}
	return result, true
}

func taskDependencyMap(tasks []map[string]any) map[string][]string {
	result := map[string][]string{}
	for _, task := range tasks {
		result[stateString(task["id"])] = normalizedTaskStrings(task, "depends_on")
	}
	return result
}

func cloneAnyList(raw any) []any {
	values := stateArray(raw)
	encoded, _ := json.Marshal(values)
	var result []any
	_ = json.Unmarshal(encoded, &result)
	if result == nil {
		return []any{}
	}
	return result
}
