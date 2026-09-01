package gokernel

import (
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

var legacyMutationClassifications = map[string]bool{
	"equivalent": true, "unreachable": true, "non_material": true, "blocking": true,
}

var legacyMutationRelevantChanges = map[string]bool{
	"api-contract": true, "authorization": true, "business-rule": true, "calculation": true,
	"data-model": true, "data-transform": true, "financial": true, "inventory": true,
	"migration": true, "money": true, "offline": true, "parser": true, "payment": true,
	"permission": true, "security": true, "state-machine": true, "stock": true, "sync": true,
}

var legacyPureNonLogicChanges = map[string]bool{
	"copy": true, "documentation": true, "mechanical": true, "style": true, "visual": true,
}

func runMutationEvidence(args []string) (any, error) {
	if len(args) == 0 {
		return nil, argparseError("the following arguments are required: action")
	}
	if args[0] != "verify" {
		return nil, argparseError(fmt.Sprintf("argument action: invalid choice: '%s'", args[0]))
	}
	flags, err := parseFlags(args[1:], map[string]bool{
		"--state": true, "--root": true, "--plan": true, "--risk-seam": true,
		"--tool": true, "--command": true, "--report": true, "--revision": true,
		"--classifications": true, "--output": true,
	}, map[string]bool{})
	if err != nil {
		return nil, err
	}
	if err := legacyRequiredFlags(flags, "--state", "--root", "--plan", "--risk-seam", "--tool", "--command", "--report", "--revision", "--output"); err != nil {
		return nil, err
	}
	tool := lastValue(flags, "--tool")
	if !oneOf(tool, "normalized", "stryker") {
		return nil, argparseError("argument --tool: invalid choice: '" + tool + "'")
	}
	result, err := legacyMutationEvidenceVerify(
		lastValue(flags, "--root"), lastValue(flags, "--state"), lastValue(flags, "--plan"),
		lastValue(flags, "--risk-seam"), tool, lastValue(flags, "--command"),
		lastValue(flags, "--report"), lastValue(flags, "--output"), lastValue(flags, "--revision"),
		lastValue(flags, "--classifications"),
	)
	if err != nil {
		return nil, err
	}
	if stateString(result["status"]) != "passed" {
		return nil, &commandError{message: "BLOQUEADO: mutation evidence bloqueada; consulte " + stateString(result["output"]), exitCode: 3}
	}
	return result, nil
}

func legacyMutationEvidenceVerify(rootValue, stateValue, planID, riskSeam, tool, commandValue, reportValue, outputValue, revision, classificationsValue string) (map[string]any, error) {
	root, err := safeRoot(rootValue)
	if err != nil {
		return nil, err
	}
	gitRoot, err := legacyGitOutput(root, "rev-parse", "--show-toplevel")
	if err != nil {
		return nil, err
	}
	expectedRoot, evalErr := filepath.EvalSymlinks(root)
	actualRoot, actualErr := filepath.EvalSymlinks(gitRoot)
	if evalErr != nil || actualErr != nil || filepath.Clean(expectedRoot) != filepath.Clean(actualRoot) {
		return nil, fmt.Errorf("--root deve apontar para a raiz Git")
	}
	statePath, err := confinedPath(root, stateValue, "state", true)
	if err != nil {
		return nil, err
	}
	state, err := validateStateFile(statePath, "")
	if err != nil {
		return nil, err
	}
	reportPath, err := confinedPath(root, reportValue, "mutation report", true)
	if err != nil {
		return nil, err
	}
	outputPath, err := confinedPath(root, outputValue, "mutation evidence output", false)
	if err != nil {
		return nil, err
	}
	inputPaths := map[string]bool{reportPath: true}
	classificationsPath := ""
	if classificationsValue != "" {
		classificationsPath, err = confinedPath(root, classificationsValue, "mutation classifications", true)
		if err != nil {
			return nil, err
		}
		inputPaths[classificationsPath] = true
	}
	if inputPaths[outputPath] {
		return nil, fmt.Errorf("mutation evidence output deve ser diferente dos arquivos de entrada")
	}
	allowed := make(map[string]bool, len(inputPaths)+1)
	for path := range inputPaths {
		relative, _ := legacyRelative(root, path)
		allowed[relative] = true
	}
	outputRelative, _ := legacyRelative(root, outputPath)
	allowed[outputRelative] = true
	dirty, err := legacyGitOutput(root, "status", "--porcelain=v1", "--untracked-files=all")
	if err != nil {
		return nil, err
	}
	unrelated := make([]string, 0)
	for _, line := range strings.Split(dirty, "\n") {
		if len(line) <= 3 {
			continue
		}
		path := line[3:]
		if arrow := strings.LastIndex(path, " -> "); arrow >= 0 {
			path = path[arrow+4:]
		}
		if !allowed[path] {
			unrelated = append(unrelated, path)
		}
	}
	sort.Strings(unrelated)
	if len(unrelated) > 0 {
		if len(unrelated) > 8 {
			unrelated = unrelated[:8]
		}
		return nil, fmt.Errorf("mutation-evidence exige código limpo; alterações alheias: %s", strings.Join(unrelated, ", "))
	}
	var plan map[string]any
	for _, raw := range stateArray(state["plans"]) {
		item := stateObject(raw)
		if stateString(item["id"]) == planID {
			plan = item
			break
		}
	}
	if plan == nil {
		return nil, fmt.Errorf("plano inexistente: %s", planID)
	}
	planPath, err := confinedPath(root, stateString(plan["path"]), "plan.path", true)
	if err != nil {
		return nil, fmt.Errorf("plano ausente: %s", stateString(plan["path"]))
	}
	planBytes, err := os.ReadFile(planPath)
	if err != nil || !validUTF8Text(planBytes) {
		return nil, fmt.Errorf("plano deve ser UTF-8 textual")
	}
	changes := legacyPlanChanges(string(planBytes))
	policy := legacyStrongestMutationMode(stateString(plan["risk"]), changes)
	candidate, candidateOK := stateObject(state["release"])["candidate"].(map[string]any)
	currentRevision, err := legacyGitOutput(root, "rev-parse", "HEAD")
	if err != nil {
		return nil, err
	}
	expectedRevision := currentRevision
	if candidateOK && stateString(candidate["revision"]) != "" {
		expectedRevision = stateString(candidate["revision"])
	}
	classifications, classificationsDigest, err := legacyMutationClassificationDocument(classificationsPath)
	if err != nil {
		return nil, err
	}
	report, err := legacyReadJSONDocument(reportPath, "mutation report")
	if err != nil {
		return nil, err
	}
	mutants, err := legacyNormalizeMutants(report, tool, classifications)
	if err != nil {
		return nil, err
	}
	known := make(map[string]bool, len(mutants))
	for _, mutant := range mutants {
		known[stateString(mutant["id"])] = true
	}
	unknown := make([]string, 0)
	for identifier := range classifications {
		if !known[identifier] {
			unknown = append(unknown, identifier)
		}
	}
	sort.Strings(unknown)
	if len(unknown) > 0 {
		return nil, fmt.Errorf("classificações referenciam mutantes ausentes: %s", strings.Join(unknown, ", "))
	}
	blocking := make([]string, 0)
	unclassified := make([]string, 0)
	accepted := make([]string, 0)
	errors := make([]string, 0)
	ignored := make([]string, 0)
	for _, mutant := range mutants {
		identifier := stateString(mutant["id"])
		switch stateString(mutant["status"]) {
		case "error":
			errors = append(errors, identifier)
		case "ignored":
			ignored = append(ignored, identifier)
		case "survived":
			classification := stateString(mutant["classification"])
			justification := stateString(mutant["justification"])
			if !legacyMutationClassifications[classification] {
				unclassified = append(unclassified, identifier)
			} else if classification == "blocking" {
				blocking = append(blocking, identifier)
			} else if strings.TrimSpace(justification) == "" {
				unclassified = append(unclassified, identifier)
			} else {
				accepted = append(accepted, identifier)
			}
		}
	}
	if revision != expectedRevision {
		blocking = append(blocking, "revision-mismatch")
	}
	if policy == "selective" || policy == "required_selective" {
		blocking = append(blocking, errors...)
		blocking = append(blocking, ignored...)
		blocking = append(blocking, unclassified...)
	}
	blocking = legacyUniqueSorted(blocking)
	sort.Strings(accepted)
	sort.Strings(unclassified)
	counts := map[string]any{
		"total": len(mutants), "killed": legacyMutationStatusCount(mutants, "killed"),
		"survived": legacyMutationStatusCount(mutants, "survived"), "ignored": len(ignored),
		"errors": len(errors), "accepted_survivors": len(accepted),
		"unclassified_survivors": len(unclassified), "blocking": len(blocking),
	}
	var fingerprint any
	if candidateOK {
		fingerprint = map[string]any{"id": candidate["id"], "revision": candidate["revision"], "build": candidate["build"], "checksum": candidate["checksum"]}
	}
	status := "passed"
	if len(blocking) > 0 {
		status = "blocked"
	}
	reportRelative, _ := legacyRelative(root, reportPath)
	reportDigest, _ := legacyFileDigest(reportPath)
	payload := map[string]any{
		"schema_version": 1, "status": status, "result": status, "policy": policy,
		"plan": planID, "risk_seam": riskSeam, "changes": changes, "tool": tool,
		"command": commandValue, "revision": revision, "expected_revision": expectedRevision,
		"candidate": fingerprint, "report": reportRelative, "report_digest": reportDigest,
		"classifications_digest": classificationsDigest, "mutants": counts,
		"accepted_survivors": accepted, "unclassified_survivors": unclassified,
		"blocking_mutants": blocking,
	}
	encoded, _ := legacyJSONBytes(payload, true)
	if err := atomicWrite(outputPath, encoded); err != nil {
		return nil, err
	}
	outputDigest, _ := legacyFileDigest(outputPath)
	payload["output"] = outputRelative
	payload["output_digest"] = outputDigest
	return payload, nil
}

func legacyPlanChanges(content string) []string {
	matches := legacyPlanningUnit.FindAllStringIndex(content, -1)
	field := regexpFieldChange()
	result := make([]string, 0, len(matches))
	for index, match := range matches {
		end := len(content)
		if index+1 < len(matches) {
			end = matches[index+1][0]
		}
		if value := field(content[match[0]:end]); value != "" {
			result = append(result, value)
		}
	}
	return result
}

func regexpFieldChange() func(string) string {
	return func(section string) string {
		for _, line := range strings.Split(section, "\n") {
			trimmed := strings.TrimSpace(line)
			prefix := "**Change:**"
			if strings.HasPrefix(strings.ToLower(trimmed), strings.ToLower(prefix)) {
				return strings.TrimSpace(trimmed[len(prefix):])
			}
		}
		return ""
	}
}

func legacyMutationMode(risk, change string) string {
	normalized := strings.ReplaceAll(strings.ToLower(strings.TrimSpace(change)), "_", "-")
	if risk == "low" || legacyPureNonLogicChanges[normalized] {
		return "not_required"
	}
	if risk == "high" || risk == "critical" {
		return "required_selective"
	}
	if legacyMutationRelevantChanges[normalized] {
		return "selective"
	}
	return "not_required"
}

func legacyStrongestMutationMode(risk string, changes []string) string {
	if len(changes) == 0 {
		changes = []string{"behavioral"}
	}
	rank := map[string]int{"not_required": 0, "selective": 1, "required_selective": 2}
	strongest := "not_required"
	for _, change := range changes {
		mode := legacyMutationMode(risk, change)
		if rank[mode] > rank[strongest] {
			strongest = mode
		}
	}
	return strongest
}

func legacyMutationClassificationDocument(path string) (map[string]map[string]any, any, error) {
	if path == "" {
		return map[string]map[string]any{}, nil, nil
	}
	value, err := legacyReadJSONDocument(path, "classificações de mutantes")
	if err != nil {
		return nil, nil, err
	}
	source := any(value)
	if mutants, ok := value["mutants"]; ok {
		source = mutants
	}
	object, ok := source.(map[string]any)
	if !ok {
		return nil, nil, fmt.Errorf("classificações de mutantes devem ser objeto por ID")
	}
	result := make(map[string]map[string]any, len(object))
	for identifier, raw := range object {
		classification, ok := raw.(map[string]any)
		if !ok {
			return nil, nil, fmt.Errorf("classificação de mutante inválida")
		}
		result[identifier] = classification
	}
	digest, _ := legacyFileDigest(path)
	return result, digest, nil
}

func legacyNormalizeMutants(report map[string]any, tool string, classifications map[string]map[string]any) ([]map[string]any, error) {
	type sourceMutant struct {
		file string
		raw  any
	}
	sources := make([]sourceMutant, 0)
	if tool == "normalized" {
		values, ok := report["mutants"].([]any)
		if stateInt(report["schema_version"]) != 1 || !ok {
			return nil, fmt.Errorf("relatório normalized exige schema_version 1 e lista mutants")
		}
		for _, value := range values {
			sources = append(sources, sourceMutant{raw: value})
		}
	} else if tool == "stryker" {
		files, ok := report["files"].(map[string]any)
		if !ok {
			return nil, fmt.Errorf("relatório Stryker exige objeto files")
		}
		fileNames := make([]string, 0, len(files))
		for file := range files {
			fileNames = append(fileNames, file)
		}
		sort.Strings(fileNames)
		for _, file := range fileNames {
			rawData := files[file]
			data, ok := rawData.(map[string]any)
			if !ok {
				continue
			}
			values, _ := data["mutants"].([]any)
			for _, value := range values {
				sources = append(sources, sourceMutant{file: file, raw: value})
			}
		}
	} else {
		return nil, fmt.Errorf("tool de mutação não suportada: %s", tool)
	}
	statusMap := map[string]string{
		"killed": "killed", "timeout": "killed", "survived": "survived",
		"nocoverage": "survived", "no_coverage": "survived", "ignored": "ignored",
		"compileerror": "error", "compile_error": "error", "runtimeerror": "error",
		"runtime_error": "error", "error": "error",
	}
	result := make([]map[string]any, 0, len(sources))
	seen := make(map[string]bool, len(sources))
	for index, source := range sources {
		raw, ok := source.raw.(map[string]any)
		if !ok {
			return nil, fmt.Errorf("mutante deve ser objeto")
		}
		identifier := fmt.Sprint(raw["id"])
		if raw["id"] == nil || identifier == "" {
			prefix := source.file
			if prefix == "" {
				prefix = "mutant"
			}
			identifier = fmt.Sprintf("%s:%d", prefix, index)
		}
		if seen[identifier] {
			return nil, fmt.Errorf("ID de mutante duplicado: %s", identifier)
		}
		seen[identifier] = true
		rawStatus := strings.ToLower(strings.ReplaceAll(strings.ReplaceAll(fmt.Sprint(raw["status"]), "-", ""), " ", ""))
		status, ok := statusMap[rawStatus]
		if !ok {
			return nil, fmt.Errorf("status de mutante desconhecido %q: %s", raw["status"], identifier)
		}
		external := classifications[identifier]
		classification := raw["classification"]
		justification := raw["justification"]
		if value, ok := external["classification"]; ok {
			classification = value
		}
		if value, ok := external["justification"]; ok {
			justification = value
		}
		file := any(source.file)
		if source.file == "" {
			file = raw["file"]
		}
		result = append(result, map[string]any{"id": identifier, "file": file, "status": status, "classification": classification, "justification": justification})
	}
	if len(result) == 0 {
		return nil, fmt.Errorf("relatório de mutação não contém mutantes")
	}
	return result, nil
}

func legacyMutationStatusCount(mutants []map[string]any, status string) int {
	count := 0
	for _, mutant := range mutants {
		if stateString(mutant["status"]) == status {
			count++
		}
	}
	return count
}
