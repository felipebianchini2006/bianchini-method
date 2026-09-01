package gokernel

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
)

var (
	contextHeadingPattern     = regexp.MustCompile(`(?m)^(#{1,6})\s+([^\n]+)$`)
	contextScopeIDPattern     = regexp.MustCompile(`^((?:FLW|REQ|NFR|BR|DAT|INT|ERR|RSK)-[0-9]+)\b`)
	contextDecisionIDPattern  = regexp.MustCompile(`^(D-[0-9]{3})\b`)
	contextDecisionReference  = regexp.MustCompile(`\bD-[0-9]{3}\b`)
	contextSpecHeadingPattern = regexp.MustCompile(`(?m)^(#{2,6})\s+\[?([A-Z][A-Z0-9_-]*-[0-9]{3,})\]?(?:\s*[:—-]\s*|\s+)([^\n]+)$`)
)

type contextHeading struct {
	start int
	level int
	title string
}

func contextStateSlice(value map[string]any) map[string]any {
	result := map[string]any{}
	for _, field := range []string{"active_work", "current_unit", "status", "blockers", "next_action", "last_completed", "pointers"} {
		result[field] = value[field]
	}
	return result
}

func contextHeadings(content string) []contextHeading {
	matches := contextHeadingPattern.FindAllStringSubmatchIndex(content, -1)
	result := make([]contextHeading, 0, len(matches))
	for _, match := range matches {
		result = append(result, contextHeading{
			start: match[0],
			level: match[3] - match[2],
			title: content[match[4]:match[5]],
		})
	}
	return result
}

func contextSectionSlices(content string, identifiers map[string]bool, idPattern *regexp.Regexp, label string) ([]any, error) {
	headings := contextHeadings(content)
	selected := map[string]string{}
	for index, heading := range headings {
		match := idPattern.FindStringSubmatch(heading.title)
		if match == nil || !identifiers[match[1]] {
			continue
		}
		end := len(content)
		for _, following := range headings[index+1:] {
			if following.level <= heading.level {
				end = following.start
				break
			}
		}
		selected[match[1]] = strings.TrimSpace(content[heading.start:end])
	}
	missing := make([]string, 0)
	for identifier := range identifiers {
		if _, ok := selected[identifier]; !ok {
			missing = append(missing, identifier)
		}
	}
	sort.Strings(missing)
	if len(missing) > 0 {
		return nil, contextError("PACK_INCOMPLETE", label+" não contém: "+strings.Join(missing, ", "))
	}
	ids := make([]string, 0, len(selected))
	for identifier := range selected {
		ids = append(ids, identifier)
	}
	sort.Strings(ids)
	result := make([]any, 0, len(ids))
	for _, identifier := range ids {
		result = append(result, map[string]any{"id": identifier, "content": selected[identifier]})
	}
	return result, nil
}

func contextStringSet(value any) map[string]bool {
	result := map[string]bool{}
	for _, item := range stateArray(value) {
		if text, ok := item.(string); ok {
			result[text] = true
		}
	}
	return result
}

func contextDecisionIDs(value any) map[string]bool {
	encoded, _ := contextCanonical(value)
	result := map[string]bool{}
	for _, identifier := range contextDecisionReference.FindAllString(string(encoded), -1) {
		result[identifier] = true
	}
	return result
}

func contextModelTouches(plan map[string]any) map[string]map[string]bool {
	result := map[string]map[string]bool{}
	for _, field := range []string{"modules", "interfaces", "ownership", "data"} {
		values := contextStringSet(plan[field])
		if len(values) > 0 {
			result[field] = values
		}
	}
	delta := stateObject(plan["model_delta"])
	for section, rawOperations := range delta {
		values := make([]any, 0)
		if list, ok := rawOperations.([]any); ok {
			values = append(values, list...)
		} else if operations, ok := rawOperations.(map[string]any); ok {
			for _, raw := range operations {
				values = append(values, stateArray(raw)...)
			}
		}
		for _, raw := range values {
			identifier := ""
			if text, ok := raw.(string); ok {
				identifier = text
			} else {
				identifier = stateString(stateObject(raw)["id"])
			}
			if identifier != "" {
				if result[section] == nil {
					result[section] = map[string]bool{}
				}
				result[section][identifier] = true
			}
		}
	}
	return result
}

func contextModelSlice(model map[string]any, touches map[string]map[string]bool) []any {
	sections := make([]string, 0, len(touches))
	for section := range touches {
		sections = append(sections, section)
	}
	sort.Strings(sections)
	result := make([]any, 0)
	for _, section := range sections {
		entries := make([]map[string]any, 0)
		switch raw := model[section].(type) {
		case []any:
			for _, item := range raw {
				if value, ok := item.(map[string]any); ok {
					entries = append(entries, value)
				}
			}
		case map[string]any:
			keys := contextSortedMapKeys(raw)
			for _, key := range keys {
				if value, ok := raw[key].(map[string]any); ok {
					entry := map[string]any{"id": key}
					for field, item := range value {
						entry[field] = item
					}
					entries = append(entries, entry)
				}
			}
		}
		byID := map[string]map[string]any{}
		for _, entry := range entries {
			if identifier := stateString(entry["id"]); identifier != "" {
				byID[identifier] = entry
			}
		}
		ids := contextSortedKeys(touches[section])
		for _, identifier := range ids {
			var value any
			if entry, ok := byID[identifier]; ok {
				value = entry
			}
			result = append(result, map[string]any{"section": section, "id": identifier, "value": value})
		}
	}
	return result
}

func contextParseSpecRequirements(content, path string) (map[string]string, error) {
	matches := contextSpecHeadingPattern.FindAllStringSubmatchIndex(content, -1)
	if len(matches) == 0 {
		return nil, contextError("PACK_INCOMPLETE", "SPEC_REQUIREMENTS_MISSING: spec "+path+" não contém requisito com ID estável em heading")
	}
	headings := contextHeadings(content)
	byStart := map[int]int{}
	for index, heading := range headings {
		byStart[heading.start] = index
	}
	result := map[string]string{}
	for _, match := range matches {
		identifier := content[match[4]:match[5]]
		if _, exists := result[identifier]; exists {
			return nil, contextError("PACK_INCOMPLETE", "SPEC_REQUIREMENT_DUPLICATE: ID duplicado em "+path+": "+identifier)
		}
		level := match[3] - match[2]
		end := len(content)
		for _, following := range headings[byStart[match[0]]+1:] {
			if following.level <= level {
				end = following.start
				break
			}
		}
		section := strings.TrimSpace(content[match[0]:end])
		lines := strings.Split(section, "\n")
		for index, line := range lines {
			lines[index] = strings.TrimRight(line, " \t")
		}
		result[identifier] = strings.Join(lines, "\n")
	}
	return result, nil
}

func contextSpecSlices(reader *contextSourceReader, change string, scopeIDs map[string]bool, required map[string]bool) ([]any, []any, error) {
	manifest, err := reader.jsonObject(filepath.Join(change, "specs", "MANIFEST.json"), "MANIFEST.json de specs")
	if err != nil {
		return nil, nil, err
	}
	if !contextExactInt(manifest["schema_version"], 1) || !contextExactInt(manifest["spec_contract"], 1) {
		return nil, nil, contextError("PACK_INCOMPLETE", "MANIFEST.json de specs possui contrato inválido")
	}
	rawSpecs, ok := manifest["specs"].([]any)
	if !ok {
		return nil, nil, contextError("PACK_INCOMPLETE", "MANIFEST.json.specs exige lista")
	}
	result := make([]any, 0)
	covered := map[string]bool{}
	for _, rawSpec := range rawSpecs {
		spec, valid := rawSpec.(map[string]any)
		pathValue, pathValid := spec["path"].(string)
		if !valid || !pathValid {
			return nil, nil, contextError("PACK_INCOMPLETE", "entrada inválida em MANIFEST.json.specs")
		}
		if err := contextValidateSpecTarget(pathValue); err != nil {
			return nil, nil, err
		}
		declarations, ok := spec["requirements"].([]any)
		if !ok {
			return nil, nil, contextError("PACK_INCOMPLETE", "requirements de spec exige lista")
		}
		selected := make([]struct {
			id    string
			scope []string
		}, 0)
		for _, rawDeclaration := range declarations {
			declaration, valid := rawDeclaration.(map[string]any)
			if !valid {
				return nil, nil, contextError("PACK_INCOMPLETE", "requirement inválido no manifesto")
			}
			identifier, idValid := declaration["id"].(string)
			rawScope, scopeValid := declaration["scope"].([]any)
			if !idValid || !scopeValid {
				return nil, nil, contextError("PACK_INCOMPLETE", "requirement incompleto no manifesto")
			}
			relevant := make([]string, 0)
			for _, raw := range rawScope {
				if value, ok := raw.(string); ok && scopeIDs[value] {
					relevant = append(relevant, value)
					covered[value] = true
				}
			}
			sort.Strings(relevant)
			if len(relevant) > 0 {
				selected = append(selected, struct {
					id    string
					scope []string
				}{identifier, relevant})
			}
		}
		if len(selected) == 0 {
			continue
		}
		specPath, err := contextSafePath(reader.root, filepath.Join(change, "specs", "expected", filepath.FromSlash(pathValue)), "spec target")
		if err != nil {
			return nil, nil, err
		}
		content, err := reader.text(specPath, "spec "+pathValue)
		if err != nil {
			return nil, nil, err
		}
		parsed, err := contextParseSpecRequirements(content, pathValue)
		if err != nil {
			return nil, nil, err
		}
		for _, declaration := range selected {
			section, present := parsed[declaration.id]
			if !present {
				return nil, nil, contextError("PACK_INCOMPLETE", fmt.Sprintf("spec %s não contém %s", pathValue, declaration.id))
			}
			result = append(result, map[string]any{
				"id": declaration.id, "spec": spec["id"], "path": pathValue,
				"scope": declaration.scope, "content": section,
			})
			required[fmt.Sprintf("spec:%v#%s", spec["id"], declaration.id)] = true
		}
	}
	rawRisk, ok := manifest["risk_coverage"].([]any)
	if !ok {
		return nil, nil, contextError("PACK_INCOMPLETE", "MANIFEST.json.risk_coverage exige lista")
	}
	riskCoverage := make([]any, 0)
	for _, raw := range rawRisk {
		item, valid := raw.(map[string]any)
		if !valid {
			return nil, nil, contextError("PACK_INCOMPLETE", "risk_coverage contém item inválido")
		}
		scopeID, _ := item["scope"].(string)
		if scopeIDs[scopeID] {
			riskCoverage = append(riskCoverage, item)
			covered[scopeID] = true
			required[fmt.Sprintf("risk-coverage:%s:%v:%v", scopeID, item["kind"], item["target"])] = true
		}
	}
	missing := make([]string, 0)
	for scopeID := range scopeIDs {
		if !covered[scopeID] {
			missing = append(missing, scopeID)
		}
	}
	sort.Strings(missing)
	if len(missing) > 0 {
		return nil, nil, contextError("PACK_INCOMPLETE", "requirements do pack sem cobertura de spec: "+strings.Join(missing, ", "))
	}
	sort.Slice(result, func(i, j int) bool {
		left, right := stateObject(result[i]), stateObject(result[j])
		if stateString(left["path"]) != stateString(right["path"]) {
			return stateString(left["path"]) < stateString(right["path"])
		}
		return stateString(left["id"]) < stateString(right["id"])
	})
	sort.Slice(riskCoverage, func(i, j int) bool {
		left, right := stateObject(riskCoverage[i]), stateObject(riskCoverage[j])
		for _, field := range []string{"scope", "kind", "target"} {
			if stateString(left[field]) != stateString(right[field]) {
				return stateString(left[field]) < stateString(right[field])
			}
		}
		return false
	})
	return result, riskCoverage, nil
}

func contextValidateSpecTarget(value string) error {
	if value == "" || strings.Contains(value, "\\") || filepath.IsAbs(value) || filepath.ToSlash(filepath.Clean(filepath.FromSlash(value))) != value {
		return contextError("PATH_UNSAFE", "spec target contém path inválido")
	}
	for _, part := range strings.Split(value, "/") {
		if part == "" || part == "." || part == ".." {
			return contextError("PATH_UNSAFE", "spec target contém traversal")
		}
		if strings.EqualFold(part, ".planning") {
			return contextError("PATH_UNSAFE", "spec target usa namespace estrangeiro")
		}
	}
	return nil
}

func contextOpenFindings(value map[string]any, planID string) ([]any, error) {
	findings, ok := value["findings"].([]any)
	if !ok {
		return nil, contextError("PACK_INCOMPLETE", "COHERENCE.findings exige lista")
	}
	result := make([]any, 0)
	for _, raw := range findings {
		item, ok := raw.(map[string]any)
		if !ok {
			continue
		}
		if status, present := item["status"]; present && stateString(status) != "open" {
			continue
		}
		phases, hasPhases := item["phases"].([]any)
		if !hasPhases || len(phases) == 0 || contextContainsString(phases, planID) {
			result = append(result, item)
		}
	}
	return result, nil
}

func contextLedgerTail(reader *contextSourceReader, change string) ([]any, error) {
	var selected string
	for _, candidate := range []string{
		filepath.Join(change, "results", "LEDGER.jsonl"), filepath.Join(change, "LEDGER.jsonl"),
		filepath.Join(change, "results", "LEDGER.md"), filepath.Join(change, "LEDGER.md"),
	} {
		if info, err := os.Lstat(candidate); err == nil {
			if info.Mode()&os.ModeSymlink != 0 || !info.Mode().IsRegular() {
				return nil, contextError("PATH_UNSAFE", "ledger atravessa symlink")
			}
			selected = candidate
			break
		}
	}
	if selected == "" {
		return []any{}, nil
	}
	content, err := reader.text(selected, "ledger")
	if err != nil {
		return nil, err
	}
	if content == "" {
		return []any{}, nil
	}
	normalized := strings.ReplaceAll(strings.ReplaceAll(content, "\r\n", "\n"), "\r", "\n")
	lines := strings.Split(strings.TrimSuffix(normalized, "\n"), "\n")
	if len(lines) > 20 {
		lines = lines[len(lines)-20:]
	}
	result := make([]any, 0, len(lines))
	for _, line := range lines {
		var value any
		if json.Unmarshal([]byte(line), &value) == nil {
			result = append(result, value)
		} else {
			result = append(result, line)
		}
	}
	return result, nil
}

func contextChangePayload(root string, reader *contextSourceReader, state map[string]any, changeID, planID, taskID string, required map[string]bool) (map[string]any, error) {
	change, err := contextPrefixedDirectory(root, filepath.Join(root, ".bianchini", "changes"), changeID, "mudança")
	if err != nil {
		return nil, err
	}
	plan, err := reader.frontmatter(filepath.Join(change, "plans", planID+".md"), "plano "+planID)
	if err != nil {
		return nil, err
	}
	if stateString(plan["id"]) != planID {
		return nil, contextError("PACK_INCOMPLETE", "plano "+planID+" possui id divergente")
	}
	required["plan:"+changeID+"/"+planID] = true
	tasks, ok := plan["tasks"].([]any)
	if !ok {
		return nil, contextError("PACK_INCOMPLETE", "plano "+planID+".tasks exige lista")
	}
	var selectedTask map[string]any
	if taskID != "" {
		matches := make([]map[string]any, 0)
		for _, raw := range tasks {
			if item, ok := raw.(map[string]any); ok && stateString(item["id"]) == taskID {
				matches = append(matches, item)
			}
		}
		if len(matches) != 1 {
			return nil, contextError("PACK_INCOMPLETE", "tarefa "+taskID+" não existe em "+planID)
		}
		selectedTask = matches[0]
		required["task:"+changeID+"/"+planID+"/"+taskID] = true
	}
	rawScope := plan["requirements"]
	if selectedTask != nil {
		rawScope = selectedTask["covers"]
	}
	rawScopeList, scopeListOK := rawScope.([]any)
	scopeIDs := contextStringSet(rawScope)
	validScope := scopeListOK && len(rawScopeList) > 0
	for _, item := range rawScopeList {
		if _, ok := item.(string); !ok {
			validScope = false
		}
	}
	if !validScope || len(scopeIDs) == 0 {
		return nil, contextError("PACK_INCOMPLETE", "unidade não declara cobertura de SCOPE")
	}
	scopeContent, err := reader.text(filepath.Join(change, "SCOPE.md"), "SCOPE.md")
	if err != nil {
		return nil, err
	}
	scope, err := contextSectionSlices(scopeContent, scopeIDs, contextScopeIDPattern, "SCOPE.md")
	if err != nil {
		return nil, err
	}
	for identifier := range scopeIDs {
		required["scope:"+identifier] = true
	}
	specs, riskCoverage, err := contextSpecSlices(reader, change, scopeIDs, required)
	if err != nil {
		return nil, err
	}
	touches := contextModelTouches(plan)
	modelNodes := []any{}
	if len(touches) > 0 {
		model, err := reader.frontmatter(filepath.Join(change, "SYSTEM_MODEL.md"), "SYSTEM_MODEL.md")
		if err != nil {
			return nil, err
		}
		modelNodes = contextModelSlice(model, touches)
	}

	plansDirectory := filepath.Join(change, "plans")
	children, err := contextChildren(plansDirectory, "plans")
	if err != nil {
		return nil, err
	}
	allPlans := make([]map[string]any, 0)
	for _, candidate := range children {
		info, _ := os.Lstat(candidate)
		if info.Mode().IsRegular() && filepath.Ext(candidate) == ".md" {
			value, err := reader.frontmatter(candidate, "plano "+strings.TrimSuffix(filepath.Base(candidate), ".md"))
			if err != nil {
				return nil, err
			}
			if stateString(value["id"]) != "" {
				allPlans = append(allPlans, value)
			}
		}
	}
	byID := map[string]map[string]any{}
	for _, value := range allPlans {
		byID[stateString(value["id"])] = value
	}
	consumes, provides := contextStringSet(plan["consumes"]), contextStringSet(plan["provides"])
	providerIDs := map[string]bool{}
	for _, candidate := range allPlans {
		identifier := stateString(candidate["id"])
		if identifier != planID && contextSetsIntersect(consumes, contextStringSet(candidate["provides"])) {
			providerIDs[identifier] = true
		}
	}
	requiredResults := contextStringSet(plan["depends_on"])
	for identifier := range providerIDs {
		requiredResults[identifier] = true
	}
	completedProviders, dependencyResults := make([]any, 0), make([]any, 0)
	for _, dependencyID := range contextSortedKeys(requiredResults) {
		result, err := reader.frontmatter(filepath.Join(change, "results", dependencyID+".md"), "resultado "+dependencyID)
		if err != nil {
			return nil, err
		}
		if stateString(result["status"]) != "completed" {
			return nil, contextError("PACK_INCOMPLETE", "resultado de "+dependencyID+" não está concluído")
		}
		item := map[string]any{"id": dependencyID, "result": result}
		dependencyResults = append(dependencyResults, item)
		required["dependency-result:"+changeID+"/"+dependencyID] = true
		if providerIDs[dependencyID] {
			contracts := contextIntersection(consumes, contextStringSet(byID[dependencyID]["provides"]))
			completedProviders = append(completedProviders, map[string]any{"id": dependencyID, "result": result, "contracts": contracts})
		}
	}
	if selectedTask != nil {
		for _, dependencyID := range contextSortedKeys(contextStringSet(selectedTask["depends_on"])) {
			result, err := reader.frontmatter(filepath.Join(change, "results", "tasks", planID, dependencyID+".md"), "resultado da tarefa "+planID+"/"+dependencyID)
			if err != nil {
				return nil, err
			}
			if stateString(result["status"]) != "completed" {
				return nil, contextError("PACK_INCOMPLETE", "resultado da tarefa "+planID+"/"+dependencyID+" não está concluído")
			}
			dependencyResults = append(dependencyResults, map[string]any{"id": planID + "/" + dependencyID, "result": result})
			required["dependency-result:"+changeID+"/"+planID+"/"+dependencyID] = true
		}
	}
	affected := make([]any, 0)
	for _, candidate := range allPlans {
		identifier := stateString(candidate["id"])
		contracts := contextIntersection(provides, contextStringSet(candidate["consumes"]))
		if identifier != planID && len(contracts) > 0 {
			affected = append(affected, map[string]any{"id": identifier, "contracts": contracts})
		}
	}
	contextSortByID(completedProviders)
	contextSortByID(affected)

	decisionIDs := contextDecisionIDs(plan)
	if selectedTask != nil {
		for identifier := range contextDecisionIDs(selectedTask) {
			decisionIDs[identifier] = true
		}
	}
	architectureDecisions := []any{}
	if len(decisionIDs) > 0 {
		content, err := reader.text(filepath.Join(change, "ARCHITECTURE.md"), "ARCHITECTURE.md")
		if err != nil {
			return nil, err
		}
		architectureDecisions, err = contextSectionSlices(content, decisionIDs, contextDecisionIDPattern, "ARCHITECTURE.md")
		if err != nil {
			return nil, err
		}
		for identifier := range decisionIDs {
			required["architecture:"+identifier] = true
		}
	}
	coherence, err := reader.frontmatter(filepath.Join(change, "COHERENCE.md"), "COHERENCE.md")
	if err != nil {
		return nil, err
	}
	findings, err := contextOpenFindings(coherence, planID)
	if err != nil {
		return nil, err
	}
	var roadmap any
	roadmapPath := filepath.Join(change, "ROADMAP.md")
	if info, statErr := os.Lstat(roadmapPath); statErr == nil {
		if info.Mode()&os.ModeSymlink != 0 || !info.Mode().IsRegular() {
			return nil, contextError("PATH_UNSAFE", "ROADMAP.md não pode ser symlink")
		}
		value, err := reader.frontmatter(roadmapPath, "ROADMAP.md")
		if err != nil {
			return nil, err
		}
		roadmap = map[string]any{"phase": planID, "status": stateObject(value["status"])[planID]}
		required["roadmap:"+changeID+"/"+planID] = true
	}
	gates := append([]any{}, stateArray(plan["verifications"])...)
	if selectedTask != nil {
		if verify, ok := selectedTask["verify"].(map[string]any); ok {
			gates = append(gates, verify)
		}
	}
	ledger, err := contextLedgerTail(reader, change)
	if err != nil {
		return nil, err
	}
	planValue := any(plan)
	if selectedTask != nil {
		withoutTasks := map[string]any{}
		for key, value := range plan {
			if key != "tasks" {
				withoutTasks[key] = value
			}
		}
		planValue = withoutTasks
	}
	return map[string]any{
		"kind": func() string {
			if selectedTask != nil {
				return "task"
			}
			return "plan"
		}(),
		"state": contextStateSlice(state), "plan": planValue, "task": selectedTask,
		"roadmap": roadmap, "scope": scope, "spec_requirements": specs, "risk_coverage": riskCoverage,
		"model_nodes": modelNodes, "completed_providers": completedProviders, "affected_consumers": affected,
		"architecture_decisions": architectureDecisions, "gates": gates, "blockers": state["blockers"],
		"open_findings": findings, "dependency_results": dependencyResults, "ledger_tail": ledger,
	}, nil
}

func contextQuickPayload(root string, reader *contextSourceReader, state map[string]any, identifier string, required map[string]bool) (map[string]any, error) {
	directory, err := contextPrefixedDirectory(root, filepath.Join(root, ".bianchini", "quick"), identifier, "quick")
	if err != nil {
		return nil, err
	}
	brief, err := reader.frontmatter(filepath.Join(directory, "BRIEF.md"), "brief "+identifier)
	if err != nil {
		return nil, err
	}
	var progress, result any
	progressPath := filepath.Join(directory, "PROGRESS.md")
	if info, statErr := os.Lstat(progressPath); statErr == nil {
		if info.Mode()&os.ModeSymlink != 0 || !info.Mode().IsRegular() {
			return nil, contextError("PATH_UNSAFE", "progresso atravessa symlink")
		}
		progress, err = reader.frontmatter(progressPath, "progresso "+identifier)
		if err != nil {
			return nil, err
		}
	}
	resultPath := filepath.Join(directory, "RESULT.md")
	if info, statErr := os.Lstat(resultPath); statErr == nil {
		if info.Mode()&os.ModeSymlink != 0 || !info.Mode().IsRegular() {
			return nil, contextError("PATH_UNSAFE", "resultado atravessa symlink")
		}
		result, err = reader.frontmatter(resultPath, "resultado "+identifier)
		if err != nil {
			return nil, err
		}
	}
	var latest any
	if events, ok := stateObject(progress)["events"].([]any); ok && len(events) > 0 {
		latest = events[len(events)-1]
	}
	required["quick:"+identifier] = true
	blockers := contextMapGet(brief, "blockers", state["blockers"])
	return map[string]any{
		"kind": "quick", "state": contextStateSlice(state), "brief": brief,
		"latest_event": latest, "result": result, "gates": contextMapGet(brief, "gates", []any{}),
		"blockers": blockers, "open_findings": contextMapGet(brief, "findings", []any{}),
	}, nil
}

func contextDebugPayload(root string, reader *contextSourceReader, state map[string]any, identifier string, required map[string]bool) (map[string]any, error) {
	path, err := contextDebugPath(root, identifier)
	if err != nil {
		return nil, err
	}
	debug, err := reader.frontmatter(path, "debug "+identifier)
	if err != nil {
		return nil, err
	}
	var latest any
	if events, ok := debug["events"].([]any); ok && len(events) > 0 {
		latest = events[len(events)-1]
	}
	selected := map[string]any{}
	for _, field := range []string{"id", "stage", "objective", "root_cause", "hypotheses", "experiments", "red", "green", "residual_risk"} {
		if value, present := debug[field]; present {
			selected[field] = value
		}
	}
	required["debug:"+identifier] = true
	blockers := contextMapGet(debug, "blockers", state["blockers"])
	return map[string]any{
		"kind": "debug", "state": contextStateSlice(state), "debug": selected,
		"latest_event": latest, "gates": contextMapGet(debug, "gates", []any{}),
		"blockers": blockers, "open_findings": contextMapGet(debug, "findings", []any{}),
	}, nil
}

func contextRCPayload(root string, reader *contextSourceReader, state map[string]any, fingerprint string, required map[string]bool) (map[string]any, error) {
	type match struct {
		path  string
		value map[string]any
	}
	matches := make([]match, 0)
	for _, cycle := range []struct{ path, label string }{
		{filepath.Join(root, ".bianchini", "changes"), "mudanças"},
		{filepath.Join(root, ".bianchini", "archive"), "archive"},
	} {
		if _, err := os.Lstat(cycle.path); os.IsNotExist(err) {
			continue
		}
		children, err := contextChildren(cycle.path, cycle.label)
		if err != nil {
			return nil, err
		}
		for _, change := range children {
			info, _ := os.Lstat(change)
			if !info.IsDir() {
				continue
			}
			candidate := filepath.Join(change, "results", "HOMOLOGATION.md")
			if candidateInfo, statErr := os.Lstat(candidate); statErr == nil {
				if candidateInfo.Mode()&os.ModeSymlink != 0 {
					return nil, contextError("PATH_UNSAFE", "HOMOLOGATION.md não pode ser symlink")
				}
				if candidateInfo.Mode().IsRegular() {
					value, err := reader.frontmatter(candidate, "HOMOLOGATION.md")
					if err != nil {
						return nil, err
					}
					if stateString(value["fingerprint"]) == fingerprint {
						matches = append(matches, match{candidate, value})
					}
				}
			}
		}
	}
	if len(matches) != 1 {
		return nil, contextError("PACK_INCOMPLETE", "RC exige uma fonte explícita HOMOLOGATION.md com fingerprint exato em changes ou archive")
	}
	selected := matches[0]
	required["release-candidate:"+fingerprint] = true
	declared, ok := selected.value["required_refs"].([]any)
	if !ok {
		return nil, contextError("PACK_INCOMPLETE", "RC.required_refs exige lista de paths")
	}
	referenced := make([]any, 0, len(declared))
	archived := strings.HasPrefix(filepath.ToSlash(selected.path), filepath.ToSlash(filepath.Join(root, ".bianchini", "archive"))+"/")
	for _, raw := range declared {
		value, valid := raw.(string)
		if !valid {
			return nil, contextError("PACK_INCOMPLETE", "RC.required_refs exige lista de paths")
		}
		candidates := []string{value}
		parts := strings.Split(value, "/")
		if archived && len(parts) >= 4 && parts[0] == ".bianchini" && parts[1] == "changes" {
			candidates = append(candidates, filepath.ToSlash(filepath.Join(".bianchini", "archive", filepath.Join(parts[2:]...))))
		}
		existing := make([]string, 0)
		for _, candidate := range candidates {
			path, err := contextSafePath(root, candidate, "RC.required_refs")
			if err != nil {
				return nil, err
			}
			if info, statErr := os.Lstat(path); statErr == nil && info.Mode().IsRegular() && info.Mode()&os.ModeSymlink == 0 {
				existing = append(existing, path)
			}
		}
		if len(existing) != 1 {
			return nil, contextError("PACK_INCOMPLETE", "referência do RC exige uma fonte íntegra: "+value)
		}
		path := existing[0]
		relative, _ := filepath.Rel(root, path)
		relativeValue := filepath.ToSlash(relative)
		content, err := reader.text(path, "referência do RC "+relativeValue)
		if err != nil {
			return nil, err
		}
		var parsed any
		if filepath.Ext(path) == ".json" {
			if json.Unmarshal([]byte(content), &parsed) != nil {
				return nil, contextError("PACK_INCOMPLETE", "referência JSON inválida do RC: "+relativeValue)
			}
		} else {
			match := frontmatterPattern.FindStringSubmatch(content)
			if match == nil {
				return nil, contextError("PACK_INCOMPLETE", "referência do RC sem frontmatter: "+relativeValue)
			}
			if json.Unmarshal([]byte(match[1]), &parsed) != nil {
				return nil, contextError("PACK_INCOMPLETE", "referência do RC inválida: "+relativeValue)
			}
		}
		referenced = append(referenced, map[string]any{"path": relativeValue, "value": parsed})
		required["evidence:"+relativeValue] = true
	}
	findings := make([]any, 0)
	for _, raw := range stateArray(selected.value["findings"]) {
		item, ok := raw.(map[string]any)
		if !ok {
			continue
		}
		status, present := item["status"]
		if !present || stateString(status) == "open" {
			findings = append(findings, item)
		}
	}
	relative, _ := filepath.Rel(root, selected.path)
	blockers := contextMapGet(selected.value, "blockers", state["blockers"])
	return map[string]any{
		"kind": "release_candidate", "state": contextStateSlice(state), "release_candidate": selected.value,
		"source": filepath.ToSlash(relative), "gates": contextMapGet(selected.value, "gates", []any{}),
		"blockers": blockers, "open_findings": findings, "evidence": referenced,
	}, nil
}

func contextContainsString(values []any, expected string) bool {
	for _, value := range values {
		if stateString(value) == expected {
			return true
		}
	}
	return false
}

func contextSetsIntersect(left, right map[string]bool) bool {
	for value := range left {
		if right[value] {
			return true
		}
	}
	return false
}

func contextIntersection(left, right map[string]bool) []string {
	result := make([]string, 0)
	for value := range left {
		if right[value] {
			result = append(result, value)
		}
	}
	sort.Strings(result)
	return result
}

func contextSortByID(values []any) {
	sort.Slice(values, func(i, j int) bool {
		return stateString(stateObject(values[i])["id"]) < stateString(stateObject(values[j])["id"])
	})
}

func contextMapGet(value map[string]any, key string, fallback any) any {
	if selected, present := value[key]; present {
		return selected
	}
	return fallback
}
