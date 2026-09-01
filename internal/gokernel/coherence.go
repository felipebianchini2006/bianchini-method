package gokernel

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
)

var coherenceScopeItem = regexp.MustCompile(`(?m)^### ((?:FLW|REQ|NFR|BR|DAT|INT|ERR|RSK)-[0-9]{3})\b`)

func runCoherence(args []string) (any, error) {
	if len(args) == 0 {
		return nil, argparseError("the following arguments are required: action")
	}
	action := args[0]
	if !oneOf(action, "check", "approve") {
		return nil, argparseError(fmt.Sprintf("argument action: invalid choice: '%s'", action))
	}
	flags, err := parseFlags(args[1:], map[string]bool{
		"--repo": true, "--change": true, "--semantic-report": true,
		"--digest": true, "--approved-by": true,
	}, map[string]bool{"--structural-only": true})
	if err != nil {
		return nil, err
	}
	change := lastValue(flags, "--change")
	if change == "" {
		return nil, argparseError("the following arguments are required: --change")
	}
	if action == "approve" && (lastValue(flags, "--digest") == "" || lastValue(flags, "--approved-by") == "") {
		return nil, fmt.Errorf("coherence approve exige --digest e --approved-by")
	}
	repo := lastValue(flags, "--repo")
	if repo == "" {
		repo, err = os.Getwd()
		if err != nil {
			return nil, err
		}
	}
	if action == "approve" {
		return coherenceApprove(repo, change, lastValue(flags, "--digest"), lastValue(flags, "--approved-by"))
	}
	return coherenceCheck(repo, change, flags.booleans["--structural-only"], lastValue(flags, "--semantic-report"))
}

type coherencePackage struct {
	workspace        methodWorkspace
	directory        string
	current          projectModel
	expected         projectModel
	plans            []planContract
	contract         map[string]any
	planningContract int
	specContract     int
}

func loadCoherencePackage(repo, change string) (coherencePackage, error) {
	workspace, directory, plans, err := loadRoadmapPackage(repo, change)
	if err != nil {
		return coherencePackage{}, err
	}
	current, err := loadProjectModel(workspace.currentMod)
	if err != nil {
		return coherencePackage{}, workflowError("MODEL_MISMATCH", err.Error())
	}
	expected, err := loadProjectModel(filepath.Join(directory, "SYSTEM_MODEL.md"))
	if err != nil {
		return coherencePackage{}, workflowError("MODEL_MISMATCH", err.Error())
	}
	contract, err := readStructuredFrontmatter(filepath.Join(directory, "COHERENCE.md"))
	if err != nil {
		return coherencePackage{}, workflowError("COHERENCE_ERROR", err.Error())
	}
	schema := stateInt(contract["schema_version"])
	if schema == 0 {
		schema = 1
	}
	if schema != 1 && schema != 2 {
		return coherencePackage{}, workflowError("COHERENCE_ERROR", "schema_version de COHERENCE inválido")
	}
	planning := stateInt(contract["planning_contract"])
	if planning == 0 {
		planning = 1
	}
	if planning != 1 && planning != 2 {
		return coherencePackage{}, workflowError("COHERENCE_ERROR", "planning_contract inválido")
	}
	specContract := 0
	if schema == 2 {
		if planning != 2 {
			return coherencePackage{}, workflowError("COHERENCE_ERROR", "COHERENCE schema 2 exige planning_contract: 2")
		}
		specContract = stateInt(contract["spec_contract"])
		if specContract != 1 {
			return coherencePackage{}, workflowError("SPEC_CONTRACT_UNSUPPORTED", "COHERENCE schema 2 exige spec_contract: 1")
		}
	}
	return coherencePackage{workspace, directory, current, expected, plans, contract, planning, specContract}, nil
}

func coherenceCheck(repo, change string, structuralOnly bool, semanticPath string) (map[string]any, error) {
	pack, err := loadCoherencePackage(repo, change)
	if err != nil {
		return nil, err
	}
	requirements := []string{}
	manifest := map[string]string{}
	reviewDigest := any(nil)
	var schedule any
	specDigests := map[string]any{}
	if pack.planningContract >= 2 {
		for _, plan := range pack.plans {
			if plan.schema != 2 {
				return nil, workflowError("COHERENCE_ERROR", "mudança v2 exige todos os planos em schema_version 2")
			}
		}
		expectedRoadmap, _ := roadmapDocument(pack.plans)
		roadmapPath := filepath.Join(pack.directory, "ROADMAP.md")
		roadmap, readErr := coherenceReadRequired(pack.workspace, roadmapPath, "ROADMAP.md")
		if readErr != nil {
			return nil, readErr
		}
		if !bytes.Equal(roadmap, expectedRoadmap) {
			return nil, workflowError("COHERENCE_ERROR", "ROADMAP.md diverge dos planos; execute roadmap sync")
		}
		requirements, err = coherenceRequirements(pack.workspace, pack.directory)
		if err != nil {
			return nil, err
		}
		specDigests, err = loadModelSpecPackage(pack.workspace, pack.directory, pack.contract)
		if err != nil {
			return nil, err
		}
		manifest, err = coherenceArtifactManifest(pack.workspace, pack.directory)
		if err != nil {
			return nil, err
		}
		reviewDigest = coherenceReviewDigest(pack.planningContract, manifest, specDigests)
	}
	findings := coherenceStructuralFindings(pack.current, pack.expected, pack.plans, requirements, pack.planningContract >= 2)
	if pack.planningContract >= 2 {
		if projected, scheduleErr := coherenceSchedule(pack.plans); scheduleErr == nil {
			schedule = projected
		}
	}
	var semantic any
	if structuralOnly {
		semantic = nil
	} else if semanticPath == "" {
		semantic = coherenceSemanticUnavailable()
	} else {
		semantic, err = coherenceSemanticReport(semanticPath, stateString(reviewDigest))
		if err != nil {
			return nil, err
		}
	}
	allFindings := make([]any, 0, len(findings))
	allFindings = append(allFindings, findings...)
	if semanticMap, ok := semantic.(map[string]any); ok {
		allFindings = append(allFindings, stateArray(semanticMap["findings"])...)
	}
	blockers := []string{}
	for _, raw := range allFindings {
		finding := stateObject(raw)
		if stateString(finding["status"]) == "open" && oneOf(stateString(finding["severity"]), "ERROR", "WARNING") {
			blockers = append(blockers, stateString(finding["code"]))
		}
	}
	status := "ready_for_approval"
	if len(blockers) > 0 {
		status = "changes_required"
	} else if structuralOnly {
		status = "structurally_valid"
	}
	digest := coherencePackageDigest(pack.current, pack.expected, pack.plans, allFindings, semantic, pack.planningContract, manifest, specDigests)
	payload := map[string]any{
		"schema_version": pack.contract["schema_version"], "planning_contract": pack.planningContract,
		"change": filepath.Base(pack.directory), "status": status, "structural_only": structuralOnly,
		"findings": allFindings, "semantic": semantic,
		"model": map[string]any{"current": pack.current.digest(), "expected": pack.expected.digest()},
		"plans": coherencePlanMappings(pack.plans), "artifact_manifest": manifest,
		"review_input_digest": reviewDigest, "schedule": schedule, "impact": nil,
		"stale_plans": []any{}, "approval": nil, "updated_at": utcNow(), "digest": digest,
	}
	if stateInt(payload["schema_version"]) == 0 {
		payload["schema_version"] = 1
	}
	if pack.specContract != 0 {
		for key, value := range specDigests {
			payload[key] = value
		}
	}
	body := "# Coerência\n\nStatus: " + status + ".\n\n## Impact Radius\n\nAinda não calculado para uma mudança executada."
	document, _ := frontmatterDocument(payload, body, false)
	if err := pack.workspace.atomicWrite(filepath.Join(pack.directory, "COHERENCE.md"), document); err != nil {
		return nil, err
	}
	state, err := pack.workspace.readState()
	if err != nil {
		return nil, err
	}
	next := "Aprovar o digest global do planejamento."
	if status == "structurally_valid" {
		next = "Executar a revisão semântica do pacote global."
	} else if status == "changes_required" {
		next = "Resolver ERRORs e WARNINGs abertos em COHERENCE.md."
	}
	state["current_unit"], state["status"], state["blockers"], state["next_action"], state["digest"], state["updated_at"] = "coherence", map[bool]string{true: "pending_approval", false: "planning"}[status == "ready_for_approval"], stringSliceAny(blockers), next, digest, utcNow()
	pointers := stateObject(state["pointers"])
	pointers["coherence"] = filepath.ToSlash(filepath.Join(".bianchini", "changes", filepath.Base(pack.directory), "COHERENCE.md"))
	state["pointers"] = pointers
	if active, ok := state["active_work"].(map[string]any); ok {
		active["status"] = state["status"]
	}
	if err := pack.workspace.writeState(state, "# Estado atual"); err != nil {
		return nil, err
	}
	result := map[string]any{
		"change": filepath.Base(pack.directory), "planning_contract": pack.planningContract,
		"status": status, "digest": digest, "findings": allFindings,
		"structural_findings": len(findings), "semantic_available": nil,
		"artifact_manifest": manifest, "review_input_digest": reviewDigest, "schedule": schedule,
	}
	if semanticMap, ok := semantic.(map[string]any); ok {
		result["semantic_available"] = semanticMap["available"]
	}
	if pack.specContract != 0 {
		result["spec_contract"] = pack.specContract
	}
	return result, nil
}

func coherenceApprove(repo, change, digest, approvedBy string) (map[string]any, error) {
	pack, err := loadCoherencePackage(repo, change)
	if err != nil {
		return nil, err
	}
	payload := pack.contract
	if stateString(payload["status"]) != "ready_for_approval" {
		return nil, workflowError("WARNING_UNRESOLVED", "somente um pacote com revisão completa pode ser aprovado")
	}
	semantic, ok := payload["semantic"].(map[string]any)
	if !ok || semantic["available"] != true {
		return nil, workflowError("WARNING_UNRESOLVED", "revisão semântica indisponível não pode ser aprovada")
	}
	findings, ok := payload["findings"].([]any)
	if !ok {
		return nil, workflowError("COHERENCE_ERROR", "findings inválidos em COHERENCE.md")
	}
	for _, raw := range findings {
		finding := stateObject(raw)
		if stateString(finding["status"]) == "open" && oneOf(stateString(finding["severity"]), "ERROR", "WARNING") {
			return nil, workflowError("WARNING_UNRESOLVED", "ERRORs e WARNINGs abertos impedem aprovação")
		}
	}
	manifest := map[string]string{}
	specDigests := map[string]any{}
	if pack.specContract != 0 {
		specDigests, err = loadModelSpecPackage(pack.workspace, pack.directory, payload)
		if err != nil {
			return nil, err
		}
	}
	if pack.planningContract >= 2 {
		manifest, err = coherenceArtifactManifest(pack.workspace, pack.directory)
		if err != nil {
			return nil, err
		}
		if !coherenceManifestEqual(payload["artifact_manifest"], manifest) {
			return nil, workflowError("STALE_EVIDENCE", "artefatos mudaram depois da revisão semântica")
		}
		if stateString(payload["review_input_digest"]) != coherenceReviewDigest(pack.planningContract, manifest, specDigests) {
			return nil, workflowError("STALE_EVIDENCE", "manifest revisado diverge do pacote atual")
		}
	}
	currentDigest := coherencePackageDigest(pack.current, pack.expected, pack.plans, findings, semantic, pack.planningContract, manifest, specDigests)
	if digest != stateString(payload["digest"]) || digest != currentDigest {
		return nil, workflowError("STALE_EVIDENCE", "digest informado não corresponde ao pacote atual")
	}
	actor := strings.TrimSpace(approvedBy)
	if actor == "" {
		return nil, workflowError("EXTERNAL_AUTHORITY_REQUIRED", "--approved-by é obrigatório")
	}
	payload["status"] = "approved"
	payload["approval"] = map[string]any{"digest": digest, "approved_by": actor, "approved_at": utcNow()}
	payload["updated_at"] = utcNow()
	document, _ := frontmatterDocument(payload, "# Coerência\n\nStatus: approved.\n\n## Impact Radius\n\nAinda não calculado para uma mudança executada.", false)
	if err := pack.workspace.atomicWrite(filepath.Join(pack.directory, "COHERENCE.md"), document); err != nil {
		return nil, err
	}
	state, err := pack.workspace.readState()
	if err != nil {
		return nil, err
	}
	state["current_unit"], state["status"], state["blockers"] = nil, "approved", []any{}
	state["next_action"], state["digest"], state["updated_at"] = "Executar "+pack.plans[0].id+" de "+filepath.Base(pack.directory)+".", digest, utcNow()
	if active, ok := state["active_work"].(map[string]any); ok {
		active["status"] = "approved"
	}
	if err := pack.workspace.writeState(state, "# Estado atual"); err != nil {
		return nil, err
	}
	return map[string]any{"change": filepath.Base(pack.directory), "status": "approved", "digest": digest, "approved_by": actor}, nil
}

func coherenceReadRequired(workspace methodWorkspace, path, label string) ([]byte, error) {
	if err := workspace.validateWorkspacePath(path); err != nil {
		return nil, workflowError("COHERENCE_ERROR", "artefato obrigatório ausente ou symlink: "+label)
	}
	info, err := os.Lstat(path)
	if err != nil || info.Mode()&os.ModeSymlink != 0 || !info.Mode().IsRegular() {
		return nil, workflowError("COHERENCE_ERROR", "artefato obrigatório ausente ou symlink: "+label)
	}
	content, err := os.ReadFile(path)
	if err != nil {
		return nil, workflowError("COHERENCE_ERROR", "artefato obrigatório ausente ou symlink: "+label)
	}
	return content, nil
}

func coherenceArtifactManifest(workspace methodWorkspace, directory string) (map[string]string, error) {
	paths := []string{"SCOPE.md", "RESEARCH.md", "ARCHITECTURE.md", "SYSTEM_MODEL.md", "ROADMAP.md"}
	planPaths, _ := filepath.Glob(filepath.Join(directory, "plans", "P*.md"))
	sort.Strings(planPaths)
	for _, path := range planPaths {
		relative, _ := filepath.Rel(directory, path)
		paths = append(paths, filepath.ToSlash(relative))
	}
	result := map[string]string{}
	for _, relative := range paths {
		content, err := coherenceReadRequired(workspace, filepath.Join(directory, filepath.FromSlash(relative)), filepath.Base(relative))
		if err != nil {
			return nil, err
		}
		result[relative] = sha256Bytes(content)
	}
	return result, nil
}

func coherenceRequirements(workspace methodWorkspace, directory string) ([]string, error) {
	content, err := coherenceReadRequired(workspace, filepath.Join(directory, "SCOPE.md"), "SCOPE.md")
	if err != nil {
		return nil, workflowError("COHERENCE_ERROR", "SCOPE.md ausente")
	}
	seen := map[string]bool{}
	result := []string{}
	for _, match := range coherenceScopeItem.FindAllSubmatch(content, -1) {
		identifier := string(match[1])
		if !seen[identifier] {
			seen[identifier] = true
			result = append(result, identifier)
		}
	}
	if len(result) == 0 {
		return nil, workflowError("COHERENCE_ERROR", "SCOPE.md não possui itens rastreáveis FLW/REQ/NFR/BR/DAT/INT/ERR/RSK")
	}
	return result, nil
}

func coherenceReviewDigest(planning int, manifest map[string]string, spec map[string]any) string {
	payload := map[string]any{"planning_contract": planning, "artifact_manifest": manifest}
	if len(spec) > 0 {
		payload["spec_package"] = spec
	}
	return waveStableDigest(payload)
}

func coherencePackageDigest(current, expected projectModel, plans []planContract, findings []any, semantic any, planning int, manifest map[string]string, spec map[string]any) string {
	payload := map[string]any{
		"current": current.mapping(), "expected": expected.mapping(),
		"plans": coherencePlanMappings(plans), "findings": findings, "semantic": semantic,
	}
	if planning >= 2 {
		payload["planning_contract"], payload["artifact_manifest"] = planning, manifest
	}
	if len(spec) > 0 {
		payload["spec_package"] = spec
	}
	return waveStableDigest(payload)
}

func coherencePlanMappings(plans []planContract) []any {
	result := make([]any, 0, len(plans))
	for _, plan := range plans {
		result = append(result, canonicalPlanMapping(plan))
	}
	return result
}

func coherenceManifestEqual(raw any, expected map[string]string) bool {
	observed, ok := raw.(map[string]any)
	if !ok || len(observed) != len(expected) {
		return false
	}
	for key, value := range expected {
		if stateString(observed[key]) != value {
			return false
		}
	}
	return true
}

func coherenceSchedule(plans []planContract) (map[string]any, error) {
	planWaves, err := coherencePlanWaves(plans)
	if err != nil {
		return nil, err
	}
	taskWaves := map[string]any{}
	for _, plan := range plans {
		if plan.schema != 2 {
			continue
		}
		waves, waveErr := coherenceTaskWaves(planTasks(plan))
		if waveErr != nil {
			return nil, waveErr
		}
		taskWaves[plan.id] = waves
	}
	return map[string]any{"plan_waves": planWaves, "task_waves": taskWaves}, nil
}

func coherencePlanWaves(plans []planContract) ([]any, error) {
	dependencies, order := coherencePlanDependencies(plans)
	return coherenceWaves(dependencies, order, "dependência inexistente: ", "grafo contém ciclo")
}

func coherenceTaskWaves(tasks []map[string]any) ([]any, error) {
	dependencies := map[string][]string{}
	order := []string{}
	for _, task := range tasks {
		identifier := stateString(task["id"])
		order = append(order, identifier)
		dependencies[identifier] = normalizedTaskStrings(task, "depends_on")
	}
	return coherenceWaves(dependencies, order, "dependência de tarefa inexistente: ", "grafo de tarefas contém ciclo")
}

func coherenceWaves(dependencies map[string][]string, order []string, unknownPrefix, cycle string) ([]any, error) {
	known := stringSet(order)
	for _, values := range dependencies {
		for _, dependency := range values {
			if !known[dependency] {
				return nil, fmt.Errorf("%s%s", unknownPrefix, dependency)
			}
		}
	}
	remaining := map[string]map[string]bool{}
	for _, identifier := range order {
		remaining[identifier] = stringSet(dependencies[identifier])
	}
	waves := []any{}
	for len(remaining) > 0 {
		ready := []string{}
		for _, identifier := range order {
			if deps, exists := remaining[identifier]; exists && len(deps) == 0 {
				ready = append(ready, identifier)
			}
		}
		if len(ready) == 0 {
			return nil, fmt.Errorf("%s", cycle)
		}
		waves = append(waves, stringSliceAny(ready))
		for _, identifier := range ready {
			delete(remaining, identifier)
		}
		for _, deps := range remaining {
			for _, identifier := range ready {
				delete(deps, identifier)
			}
		}
	}
	return waves, nil
}

func coherencePlanDependencies(plans []planContract) (map[string][]string, []string) {
	providers := map[string][]string{}
	for _, plan := range plans {
		for _, contract := range normalizedPlanStrings(plan, "provides") {
			providers[contract] = append(providers[contract], plan.id)
		}
	}
	dependencies, order := map[string][]string{}, []string{}
	for _, plan := range plans {
		order = append(order, plan.id)
		values := append([]string(nil), normalizedPlanStrings(plan, "depends_on")...)
		for _, contract := range normalizedPlanStrings(plan, "consumes") {
			for _, provider := range providers[contract] {
				if provider != plan.id && !containsString(values, provider) {
					values = append(values, provider)
				}
			}
		}
		dependencies[plan.id] = values
	}
	return dependencies, order
}

func coherenceSemanticUnavailable() map[string]any {
	finding := coherenceFinding("SEMANTIC_REVIEW_UNAVAILABLE", "WARNING", "semantic", nil, nil, "Relatório semântico não foi fornecido.", "Executar a revisão antes da aprovação do pacote.")
	return map[string]any{
		"available": false, "findings": []any{finding},
		"prompt_digest": sha256Bytes(nil), "input_digest": sha256Bytes(nil), "sources_digest": sha256Bytes(nil),
	}
}

func coherenceSemanticReport(path, expectedInput string) (map[string]any, error) {
	if hasForeignPart(path) {
		return nil, workflowError("COHERENCE_ERROR", "relatório semântico ausente: "+path)
	}
	info, err := os.Lstat(path)
	if err != nil || info.Mode()&os.ModeSymlink != 0 || !info.Mode().IsRegular() {
		return nil, workflowError("COHERENCE_ERROR", "relatório semântico ausente: "+path)
	}
	content, err := os.ReadFile(path)
	if err != nil || !validUTF8Text(content) {
		return nil, workflowError("COHERENCE_ERROR", "relatório semântico inválido na linha 1")
	}
	decoder := json.NewDecoder(bytes.NewReader(content))
	decoder.UseNumber()
	value := map[string]any{}
	if err := decoder.Decode(&value); err != nil {
		return nil, workflowError("COHERENCE_ERROR", "relatório semântico inválido na linha 1")
	}
	findings, ok := value["findings"].([]any)
	if value["findings"] == nil {
		findings, ok = []any{}, true
	}
	if !ok {
		return nil, workflowError("COHERENCE_ERROR", "relatório semântico exige findings")
	}
	if expectedInput != "" && stateString(value["inputs"]) != expectedInput {
		return nil, workflowError("STALE_EVIDENCE", "relatório semântico não corresponde ao manifest atual do pacote")
	}
	normalized := []any{}
	for _, raw := range findings {
		item, ok := raw.(map[string]any)
		if !ok {
			return nil, workflowError("COHERENCE_ERROR", "finding semântico exige objeto")
		}
		finding, normalizeErr := coherenceNormalizeSemanticFinding(item)
		if normalizeErr != nil {
			return nil, workflowError("COHERENCE_ERROR", normalizeErr.Error())
		}
		normalized = append(normalized, finding)
	}
	coherenceSortFindings(normalized, map[string]int{})
	sources, err := coherenceFlexibleStrings(value["sources"], "sources")
	if err != nil {
		return nil, workflowError("COHERENCE_ERROR", err.Error())
	}
	sources = uniqueSorted(sources)
	return map[string]any{
		"available": true, "findings": normalized,
		"prompt_digest":  sha256Bytes([]byte(stateString(value["prompt"]))),
		"input_digest":   sha256Bytes([]byte(stateString(value["inputs"]))),
		"sources_digest": sha256Bytes([]byte(strings.Join(sources, "\n"))),
	}, nil
}

func coherenceNormalizeSemanticFinding(raw map[string]any) (map[string]any, error) {
	severity := strings.ToUpper(stateString(raw["severity"]))
	if severity == "" {
		severity = "WARNING"
	}
	if !oneOf(severity, "ERROR", "WARNING", "INFO") {
		return nil, fmt.Errorf("severidade inválida: %s", stateString(raw["severity"]))
	}
	if severity == "ERROR" {
		severity = "WARNING"
	}
	status := strings.ToLower(stateString(raw["status"]))
	if status == "" {
		status = "open"
	}
	if !oneOf(status, "open", "resolved", "accepted_with_justification") {
		return nil, fmt.Errorf("status de finding inválido: %s", stateString(raw["status"]))
	}
	code := strings.Trim(regexp.MustCompile(`[^A-Z0-9]+`).ReplaceAllString(strings.ToUpper(stateString(raw["code"])), "_"), "_")
	if code == "" {
		code = "SEMANTIC_FINDING"
	}
	if code[0] < 'A' || code[0] > 'Z' {
		return nil, fmt.Errorf("código de finding inválido: %s", stateString(raw["code"]))
	}
	phases, err := coherenceFlexibleStrings(raw["phases"], "phases")
	if err != nil {
		return nil, err
	}
	contracts, err := coherenceFlexibleStrings(raw["contracts"], "contracts")
	if err != nil {
		return nil, err
	}
	evidence, fix := strings.TrimSpace(stateString(raw["evidence"])), strings.TrimSpace(stateString(raw["expected_fix"]))
	if fix == "" && severity == "INFO" {
		fix = "Nenhuma ação obrigatória."
	}
	if evidence == "" || fix == "" {
		return nil, fmt.Errorf("finding exige evidência e correção esperada")
	}
	finding := coherenceFinding(code, severity, "semantic", phases, contracts, evidence, fix)
	finding["status"] = status
	if justification := strings.TrimSpace(stateString(raw["justification"])); justification != "" {
		finding["justification"] = justification
	}
	if status == "accepted_with_justification" && finding["justification"] == nil {
		return nil, fmt.Errorf("finding aceito exige justificativa")
	}
	return finding, nil
}

func coherenceFlexibleStrings(raw any, label string) ([]string, error) {
	if raw == nil {
		return []string{}, nil
	}
	if text, ok := raw.(string); ok {
		raw = []any{text}
	}
	values, ok := raw.([]any)
	if !ok {
		return nil, fmt.Errorf("%s exige lista de strings", label)
	}
	result, seen := []string{}, map[string]bool{}
	for _, value := range values {
		text, ok := value.(string)
		text = strings.TrimSpace(text)
		if !ok || text == "" {
			return nil, fmt.Errorf("%s exige lista de strings", label)
		}
		if !seen[text] {
			seen[text] = true
			result = append(result, text)
		}
	}
	return result, nil
}

func coherenceFinding(code, severity, origin string, phases, contracts []string, evidence, fix string) map[string]any {
	return map[string]any{
		"code": code, "severity": severity, "origin": origin,
		"phases": stringSliceAny(phases), "contracts": stringSliceAny(contracts),
		"evidence": evidence, "expected_fix": fix, "status": "open", "justification": nil,
	}
}

func stringSliceAny(values []string) []any {
	result := make([]any, len(values))
	for index, value := range values {
		result[index] = value
	}
	return result
}
