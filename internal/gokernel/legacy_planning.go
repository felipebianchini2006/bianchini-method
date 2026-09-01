package gokernel

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"time"
	"unicode/utf8"
)

var legacyPlanningUnit = regexp.MustCompile(`(?mi)^###\s+(?:Tarefa|Task|Slice|Grupo|Group)\s+[^\n]+$`)

var legacyPlanningLimits = map[string]map[string]int{
	"lean": {
		"plans": 7, "execution_units": 16, "platforms": 2,
		"shared_context_words": 8_000, "max_plan_words": 8_000,
		"max_execution_unit_words": 4_000,
	},
	"standard": {
		"plans": 16, "execution_units": 40, "platforms": 6,
		"shared_context_words": 24_000, "max_plan_words": 16_000,
		"max_execution_unit_words": 8_000,
	},
	"full": {
		"plans": 32, "execution_units": 80, "platforms": 12,
		"shared_context_words": 48_000, "max_plan_words": 32_000,
		"max_execution_unit_words": 16_000,
	},
}

func legacyJSONBytes(value any, indent bool) ([]byte, error) {
	var buffer bytes.Buffer
	encoder := json.NewEncoder(&buffer)
	encoder.SetEscapeHTML(false)
	if indent {
		encoder.SetIndent("", "  ")
	}
	if err := encoder.Encode(value); err != nil {
		return nil, err
	}
	return buffer.Bytes(), nil
}

func legacyCompactJSON(value any) ([]byte, error) {
	encoded, err := legacyJSONBytes(value, false)
	if err != nil {
		return nil, err
	}
	return bytes.TrimSuffix(encoded, []byte("\n")), nil
}

func legacyFileDigest(path string) (string, error) {
	content, err := os.ReadFile(path)
	if err != nil {
		return "", err
	}
	return sha256Bytes(content), nil
}

func legacyReadJSONDocument(path, label string) (map[string]any, error) {
	info, err := os.Lstat(path)
	if err != nil || !info.Mode().IsRegular() || info.Mode()&os.ModeSymlink != 0 {
		return nil, fmt.Errorf("%s ausente: %s", label, path)
	}
	content, err := os.ReadFile(path)
	if err != nil || !utf8.Valid(content) || bytes.IndexByte(content, 0) >= 0 {
		return nil, fmt.Errorf("%s deve ser JSON UTF-8", label)
	}
	trimmed := bytes.TrimSpace(content)
	if match := jsonFencePattern.FindSubmatch(content); match != nil {
		trimmed = bytes.TrimSpace(match[1])
	}
	var value map[string]any
	if err := json.Unmarshal(trimmed, &value); err != nil {
		return nil, fmt.Errorf("%s inválido: %w", label, err)
	}
	return value, nil
}

func legacyRelative(root, path string) (string, error) {
	relative, err := filepath.Rel(root, path)
	if err != nil || relative == ".." || strings.HasPrefix(relative, ".."+string(filepath.Separator)) {
		return "", fmt.Errorf("arquivo fora da raiz: %s", path)
	}
	return filepath.ToSlash(relative), nil
}

func legacyBuildManifest(root string, files []string) ([]byte, error) {
	unique := make(map[string]bool, len(files))
	for _, relative := range files {
		if err := validateRelativePath(relative, "arquivo do pacote"); err != nil {
			return nil, err
		}
		unique[relative] = true
	}
	normalized := make([]string, 0, len(unique))
	for relative := range unique {
		normalized = append(normalized, relative)
	}
	sort.Strings(normalized)
	var result strings.Builder
	for _, relative := range normalized {
		target, err := confinedPath(root, filepath.FromSlash(relative), "arquivo do pacote", true)
		if err != nil {
			return nil, fmt.Errorf("arquivo do pacote ausente: %s", relative)
		}
		digest, err := legacyFileDigest(target)
		if err != nil {
			return nil, err
		}
		fmt.Fprintf(&result, "%s  %s\n", digest, relative)
	}
	return []byte(result.String()), nil
}

func runSnapshot(args []string) (any, error) {
	if len(args) == 0 {
		return nil, argparseError("the following arguments are required: action")
	}
	action := args[0]
	if !oneOf(action, "create", "verify") {
		return nil, argparseError(fmt.Sprintf("argument action: invalid choice: '%s'", action))
	}
	positionals := make([]string, 0, 1)
	rootValue := ""
	for index := 1; index < len(args); index++ {
		switch args[index] {
		case "--root":
			if index+1 >= len(args) {
				return nil, argparseError("argument --root: expected one argument")
			}
			index++
			rootValue = args[index]
		default:
			if strings.HasPrefix(args[index], "--") {
				return nil, argparseError("unrecognized arguments: " + args[index])
			}
			positionals = append(positionals, args[index])
		}
	}
	if len(positionals) == 0 || rootValue == "" {
		missing := "state"
		if len(positionals) > 0 {
			missing = "--root"
		}
		return nil, argparseError("the following arguments are required: " + missing)
	}
	if len(positionals) > 1 {
		return nil, argparseError("unrecognized arguments: " + strings.Join(positionals[1:], " "))
	}
	return legacySnapshot(positionals[0], rootValue, action == "verify")
}

func legacySnapshot(stateValue, rootValue string, verify bool) (map[string]any, error) {
	root, err := safeRoot(rootValue)
	if err != nil {
		return nil, err
	}
	statePath, err := confinedPath(root, stateValue, "estado", true)
	if err != nil {
		if _, statErr := os.Lstat(stateValue); os.IsNotExist(statErr) {
			return nil, stateError("estado não encontrado: "+stateValue, 2)
		}
		return nil, err
	}
	state, err := validateStateFile(statePath, "")
	if err != nil {
		return nil, err
	}
	planning := stateObject(state["planning"])
	if quality := stateInt(planning["quality_version"]); quality == 1 || quality == 2 {
		if _, err := legacyPlanningAudit(statePath, root, true, true); err != nil {
			return nil, err
		}
	}
	pack := stateObject(stateObject(state["approval"])["package"])
	content, err := legacyBuildManifest(root, stateStringSlice(pack["files"]))
	if err != nil {
		return nil, err
	}
	digest := sha256Bytes(content)
	manifestValue := stateString(pack["manifest_path"])
	manifest, err := confinedPath(root, manifestValue, "manifest_path", false)
	if err != nil {
		return nil, err
	}
	if verify {
		persisted, readErr := os.ReadFile(manifest)
		if readErr != nil || !bytes.Equal(persisted, content) {
			return nil, &commandError{message: "snapshot inválido: conteúdo do manifesto divergiu", exitCode: 3}
		}
		if stateString(pack["manifest_digest"]) != digest {
			return nil, &commandError{message: "snapshot inválido: digest do estado divergiu", exitCode: 3}
		}
	} else if err := atomicWrite(manifest, content); err != nil {
		return nil, fmt.Errorf("snapshot: falha ao gravar manifesto: %w", err)
	}
	return map[string]any{"algorithm": "sha256-manifest-v1", "digest": digest, "manifest": manifest}, nil
}

func runPlanningAudit(args []string) (any, error) {
	positionals := make([]string, 0, 1)
	rootValue := ""
	strict := false
	for index := 0; index < len(args); index++ {
		switch args[index] {
		case "--root":
			if index+1 >= len(args) {
				return nil, argparseError("argument --root: expected one argument")
			}
			index++
			rootValue = args[index]
		case "--strict":
			strict = true
		default:
			if strings.HasPrefix(args[index], "--") {
				return nil, argparseError("unrecognized arguments: " + args[index])
			}
			positionals = append(positionals, args[index])
		}
	}
	if len(positionals) == 0 || rootValue == "" {
		missing := "state"
		if len(positionals) > 0 {
			missing = "--root"
		}
		return nil, argparseError("the following arguments are required: " + missing)
	}
	root, err := safeRoot(rootValue)
	if err != nil {
		return nil, err
	}
	statePath, err := confinedPath(root, positionals[0], "estado", true)
	if err != nil {
		if _, statErr := os.Lstat(positionals[0]); os.IsNotExist(statErr) {
			return nil, stateError("estado não encontrado: "+positionals[0], 2)
		}
		return nil, err
	}
	return legacyPlanningAudit(statePath, root, strict, true)
}

func legacyPlanningAuditBaseline(statePath, root string, strict, requireChecker bool) (map[string]any, error) {
	state, err := validateStateFile(statePath, "")
	if err != nil {
		return nil, err
	}
	planning := stateObject(state["planning"])
	quality := stateInt(planning["quality_version"])
	qualityEnabled := quality == 1 || quality == 2
	enforced := strict || qualityEnabled
	profile := stateString(state["assurance_profile"])
	limits, ok := legacyPlanningLimits[profile]
	if !ok {
		return nil, fmt.Errorf("assurance_profile inválido: %s", profile)
	}
	if stateString(state["planning_status"]) == "idle" {
		if enforced {
			return nil, fmt.Errorf("planejamento inválido:\n- ciclo idle ainda não possui pacote auditável")
		}
		metrics := map[string]int{"plans": 0, "execution_units": 0, "platforms": 0, "shared_context_words": 0, "max_plan_words": 0, "max_execution_unit_words": 0, "package_words": 0}
		return map[string]any{"valid": true, "quality_contract": "legacy-compatible", "profile": profile, "recommended_profile": "lean", "metrics": metrics, "limits": limits, "warnings": []string{}}, nil
	}

	pack := stateObject(stateObject(state["approval"])["package"])
	packageFiles := stateStringSlice(pack["files"])
	packageSet := stringSet(packageFiles)
	plans := stateArray(state["plans"])
	errors := make([]string, 0)
	warnings := make([]string, 0)
	contractValues := []string{stateString(planning["research"]), stateString(planning["spec"]), stateString(planning["review"])}
	for _, rawPlan := range plans {
		contractValues = append(contractValues, stateString(stateObject(rawPlan)["path"]))
	}
	if quality == 2 {
		for _, field := range []string{"readiness", "user_actions", "design_manifest"} {
			if value := stateString(planning[field]); value != "" {
				contractValues = append(contractValues, value)
			}
		}
	}
	if enforced {
		if !qualityEnabled {
			errors = append(errors, "planning.quality_version: esperado 1 ou 2 para novo planejamento")
		}
		for _, value := range contractValues {
			if value == "" {
				errors = append(errors, "pacote: pesquisa, spec, revisão e planos devem ter caminhos locais")
			} else if !packageSet[value] {
				errors = append(errors, "pacote: artefato contratual ausente do manifesto: "+value)
			}
		}
		if quality == 2 && requireChecker {
			checker := stateObject(planning["checker"])
			if stateString(checker["status"]) != "passed" {
				errors = append(errors, "planning.checker.status: revisão independente ainda não passou")
			}
		}
	}

	contents := make(map[string]string, len(packageFiles))
	packageWords := 0
	for _, relative := range packageFiles {
		target, pathErr := confinedPath(root, filepath.FromSlash(relative), "arquivo do pacote", true)
		if pathErr != nil {
			errors = append(errors, "pacote: arquivo ausente ou inseguro: "+relative)
			continue
		}
		content, readErr := os.ReadFile(target)
		if readErr != nil || !validUTF8Text(content) {
			errors = append(errors, "pacote: arquivo deve ser UTF-8 textual: "+relative)
			continue
		}
		contents[relative] = string(content)
		packageWords += len(strings.Fields(string(content)))
	}
	maxPlanWords := 0
	maxUnitWords := 0
	executionUnits := 0
	sharedWords := 0
	sharedPaths := []string{stateString(stateObject(state["scope"])["source"]), stateString(planning["research"]), stateString(planning["spec"]), stateString(planning["review"])}
	for _, relative := range sharedPaths {
		sharedWords += len(strings.Fields(contents[relative]))
	}
	for _, rawPlan := range plans {
		plan := stateObject(rawPlan)
		content := contents[stateString(plan["path"])]
		words := len(strings.Fields(content))
		if words > maxPlanWords {
			maxPlanWords = words
		}
		matches := legacyPlanningUnit.FindAllStringIndex(content, -1)
		executionUnits += len(matches)
		for index, match := range matches {
			end := len(content)
			if index+1 < len(matches) {
				end = matches[index+1][0]
			}
			unitWords := len(strings.Fields(content[match[0]:end]))
			if unitWords > maxUnitWords {
				maxUnitWords = unitWords
			}
		}
	}
	metrics := map[string]int{
		"plans": len(plans), "execution_units": executionUnits,
		"platforms":            len(stateStringSlice(stateObject(state["release"])["platforms"])),
		"shared_context_words": sharedWords, "max_plan_words": maxPlanWords,
		"max_execution_unit_words": maxUnitWords, "package_words": packageWords,
	}
	exceeded := make([]string, 0)
	for key, limit := range limits {
		if metrics[key] > limit {
			exceeded = append(exceeded, key)
		}
	}
	sort.Strings(exceeded)
	recommended := legacyRecommendedProfile(metrics, plans)
	if enforced && legacyProfileRank(profile) < legacyProfileRank(recommended) {
		errors = append(errors, fmt.Sprintf("assurance_profile %s: insuficiente para risco/capacidade; preserve todo o escopo e escale para %s", profile, recommended))
	}
	if len(errors) > 0 {
		return nil, fmt.Errorf("planejamento inválido:\n- %s", strings.Join(legacyUniqueSorted(errors), "\n- "))
	}
	contract := "legacy-compatible"
	if quality == 1 {
		contract = "planning-quality-v1"
	} else if quality == 2 {
		contract = "planning-quality-v2"
	}
	return map[string]any{
		"valid": true, "quality_contract": contract, "profile": profile,
		"recommended_profile": recommended, "research_mode": planning["research_mode"],
		"metrics": metrics, "limits": limits, "budget_exceeded": len(exceeded) > 0,
		"warnings": legacyUniqueSorted(warnings), "readiness": nil,
	}, nil
}

func legacyProfileRank(profile string) int {
	switch profile {
	case "lean":
		return 0
	case "standard":
		return 1
	default:
		return 2
	}
}

func legacyRecommendedProfile(metrics map[string]int, plans []any) string {
	capacity := "full"
	for _, profile := range []string{"lean", "standard", "full"} {
		fits := true
		for key, limit := range legacyPlanningLimits[profile] {
			if metrics[key] > limit {
				fits = false
				break
			}
		}
		if fits {
			capacity = profile
			break
		}
	}
	risk := "lean"
	for _, rawPlan := range plans {
		if oneOf(stateString(stateObject(rawPlan)["risk"]), "medium", "high", "critical") {
			risk = "standard"
		}
	}
	if legacyProfileRank(risk) > legacyProfileRank(capacity) {
		return risk
	}
	return capacity
}

func legacyUniqueSorted(values []string) []string {
	seen := make(map[string]bool, len(values))
	for _, value := range values {
		seen[value] = true
	}
	result := make([]string, 0, len(seen))
	for value := range seen {
		result = append(result, value)
	}
	sort.Strings(result)
	return result
}

func runDesignAudit(args []string) (any, error) {
	if len(args) == 0 {
		return nil, argparseError("the following arguments are required: action")
	}
	action := args[0]
	if !oneOf(action, "seal", "verify") {
		return nil, argparseError(fmt.Sprintf("argument action: invalid choice: '%s'", action))
	}
	flags, err := parseFlags(args[1:], map[string]bool{"--root": true, "--scope": true, "--manifest": true}, map[string]bool{})
	if err != nil {
		return nil, err
	}
	for _, required := range []string{"--root", "--scope", "--manifest"} {
		if lastValue(flags, required) == "" {
			return nil, argparseError("the following arguments are required: " + required)
		}
	}
	return legacyDesignAudit(lastValue(flags, "--root"), lastValue(flags, "--scope"), lastValue(flags, "--manifest"), action == "seal")
}

func legacyDesignAudit(rootValue, scopeValue, manifestValue string, seal bool) (map[string]any, error) {
	root, err := safeRoot(rootValue)
	if err != nil {
		return nil, fmt.Errorf("raiz de design não encontrada: %s", rootValue)
	}
	scope, err := confinedPath(root, scopeValue, "scope de design", true)
	if err != nil {
		return nil, fmt.Errorf("scope de design ausente: %s", filepath.Clean(scopeValue))
	}
	manifestPath, err := confinedPath(root, manifestValue, "manifesto de design", true)
	if err != nil {
		return nil, fmt.Errorf("manifesto de design ausente: %s", filepath.Clean(manifestValue))
	}
	manifest, err := legacyReadJSONDocument(manifestPath, "manifesto de design")
	if err != nil {
		return nil, err
	}
	required := []string{"schema_version", "status", "source", "scope_source", "scope_digest", "design_digest", "contract", "prototype", "tokens", "screenshots", "surfaces", "breakpoints", "files"}
	missing := make([]string, 0)
	for _, field := range required {
		if _, ok := manifest[field]; !ok {
			missing = append(missing, field)
		}
	}
	if len(missing) > 0 {
		return nil, fmt.Errorf("manifesto de design incompleto: %s", strings.Join(missing, ", "))
	}
	if stateInt(manifest["schema_version"]) != 1 {
		return nil, fmt.Errorf("manifesto de design: schema_version esperado 1")
	}
	status := stateString(manifest["status"])
	if !oneOf(status, "draft", "approved") {
		return nil, fmt.Errorf("manifesto de design: status esperado draft ou approved")
	}
	if !oneOf(stateString(manifest["source"]), "generated", "imported", "existing") {
		return nil, fmt.Errorf("manifesto de design: source inválido")
	}
	files := stateStringSlice(manifest["files"])
	if len(files) == 0 || len(files) != len(stringSet(files)) {
		return nil, fmt.Errorf("manifesto de design: files deve ser lista não vazia e sem duplicatas")
	}
	fileSet := stringSet(files)
	for _, field := range []string{"contract", "prototype", "tokens"} {
		if value := stateString(manifest[field]); value == "" || !fileSet[value] {
			return nil, fmt.Errorf("manifesto de design: %s deve constar em files", field)
		}
	}
	screenshots := stateStringSlice(manifest["screenshots"])
	if len(screenshots) == 0 {
		return nil, fmt.Errorf("manifesto de design: screenshots deve ser lista não vazia e referenciar files")
	}
	for _, screenshot := range screenshots {
		extension := strings.ToLower(filepath.Ext(screenshot))
		if !fileSet[screenshot] || !oneOf(extension, ".png", ".jpg", ".jpeg", ".webp") {
			return nil, fmt.Errorf("manifesto de design: screenshot deve ser PNG, JPEG ou WebP: %s", screenshot)
		}
	}
	for _, field := range []string{"surfaces", "breakpoints"} {
		if len(stateStringSlice(manifest[field])) == 0 {
			return nil, fmt.Errorf("manifesto de design: %s deve ser lista não vazia", field)
		}
	}
	designRoot := filepath.Dir(manifestPath)
	for _, relative := range files {
		target, pathErr := confinedPath(root, filepath.FromSlash(relative), "arquivo de design "+relative, true)
		if pathErr != nil {
			return nil, fmt.Errorf("manifesto de design: arquivo ausente: %s", relative)
		}
		designRelative, relErr := filepath.Rel(designRoot, target)
		if relErr != nil || designRelative == ".." || strings.HasPrefix(designRelative, ".."+string(filepath.Separator)) {
			return nil, fmt.Errorf("manifesto de design: arquivo fora do diretório do manifesto: %s", relative)
		}
		info, _ := os.Stat(target)
		if info.Size() == 0 {
			return nil, fmt.Errorf("manifesto de design: arquivo vazio ou ausente: %s", relative)
		}
	}
	if strings.ToLower(filepath.Ext(stateString(manifest["contract"]))) != ".md" {
		return nil, fmt.Errorf("manifesto de design: contract deve ser Markdown")
	}
	if strings.ToLower(filepath.Ext(stateString(manifest["prototype"]))) != ".html" {
		return nil, fmt.Errorf("manifesto de design: prototype deve ser HTML estático")
	}
	if strings.ToLower(filepath.Ext(stateString(manifest["tokens"]))) != ".css" {
		return nil, fmt.Errorf("manifesto de design: tokens deve ser CSS")
	}
	scopeRelative, _ := legacyRelative(root, scope)
	manifestRelative, _ := legacyRelative(root, manifestPath)
	scopeDigest, _ := legacyFileDigest(scope)
	digestManifest := make(map[string]any, len(manifest))
	for key, value := range manifest {
		if key != "status" && key != "scope_digest" && key != "design_digest" {
			digestManifest[key] = value
		}
	}
	digestManifest["scope_source"] = scopeRelative
	metadata, err := legacyCompactJSON(digestManifest)
	if err != nil {
		return nil, err
	}
	fileManifest, err := legacyBuildManifest(root, files)
	if err != nil {
		return nil, err
	}
	hash := sha256.New()
	_, _ = hash.Write(fileManifest)
	_, _ = hash.Write([]byte{0})
	_, _ = hash.Write(metadata)
	designDigest := hex.EncodeToString(hash.Sum(nil))
	if seal {
		manifest["scope_source"] = scopeRelative
		manifest["scope_digest"] = scopeDigest
		manifest["design_digest"] = designDigest
		encoded, _ := legacyJSONBytes(manifest, true)
		if err := atomicWrite(manifestPath, encoded); err != nil {
			return nil, err
		}
	} else {
		if status != "approved" {
			return nil, &commandError{message: "BLOQUEADO: manifesto de design ainda não está approved", exitCode: 3}
		}
		if stateString(manifest["scope_source"]) != scopeRelative {
			return nil, &commandError{message: "BLOQUEADO: manifesto de design aponta outro scope_source", exitCode: 3}
		}
		if stateString(manifest["scope_digest"]) != scopeDigest {
			return nil, &commandError{message: "BLOQUEADO: scope_digest do design está obsoleto", exitCode: 3}
		}
		if stateString(manifest["design_digest"]) != designDigest {
			return nil, &commandError{message: "BLOQUEADO: design_digest divergiu dos arquivos atuais", exitCode: 3}
		}
	}
	sort.Strings(files)
	return map[string]any{
		"valid": true, "action": map[bool]string{true: "seal", false: "verify"}[seal],
		"status": status, "manifest": manifestRelative, "scope_source": scopeRelative,
		"scope_digest": scopeDigest, "design_digest": designDigest, "files": files,
		"surfaces": stateStringSlice(manifest["surfaces"]), "breakpoints": stateStringSlice(manifest["breakpoints"]),
	}, nil
}

func runPlanningCheck(args []string) (any, error) {
	if len(args) == 0 {
		return nil, argparseError("the following arguments are required: action")
	}
	if args[0] != "record" {
		return nil, argparseError(fmt.Sprintf("argument action: invalid choice: '%s'", args[0]))
	}
	flags, err := parseFlags(args[1:], map[string]bool{"--state": true, "--root": true, "--report": true}, map[string]bool{})
	if err != nil {
		return nil, err
	}
	for _, required := range []string{"--state", "--root", "--report"} {
		if lastValue(flags, required) == "" {
			return nil, argparseError("the following arguments are required: " + required)
		}
	}
	return legacyPlanningCheck(lastValue(flags, "--state"), lastValue(flags, "--root"), lastValue(flags, "--report"))
}

func legacyPlanningCheck(stateValue, rootValue, reportValue string) (map[string]any, error) {
	root, err := safeRoot(rootValue)
	if err != nil {
		return nil, err
	}
	statePath, err := confinedPath(root, stateValue, "estado", true)
	if err != nil {
		if _, statErr := os.Lstat(stateValue); os.IsNotExist(statErr) {
			return nil, stateError("estado não encontrado: "+stateValue, 2)
		}
		return nil, err
	}
	state, err := validateStateFile(statePath, "")
	if err != nil {
		return nil, err
	}
	planning := stateObject(state["planning"])
	if stateInt(planning["quality_version"]) != 2 {
		return nil, fmt.Errorf("planning-check exige planning.quality_version 2")
	}
	if _, err := legacyPlanningAudit(statePath, root, true, false); err != nil {
		return nil, err
	}
	reportPath, err := confinedPath(root, reportValue, "checker report", true)
	if err != nil {
		return nil, err
	}
	reportRelative, _ := legacyRelative(root, reportPath)
	if reportRelative != stateString(planning["review"]) {
		return nil, &commandError{message: "BLOQUEADO: planning-check deve usar exatamente planning.review", exitCode: 3}
	}
	checker := stateObject(planning["checker"])
	historyValue := stateString(checker["history_path"])
	if historyValue == "" {
		return nil, fmt.Errorf("planning.checker.history_path: caminho obrigatório")
	}
	historyPath, err := confinedPath(root, filepath.FromSlash(historyValue), "planning.checker.history_path", false)
	if err != nil {
		return nil, err
	}
	historyBytes, readErr := os.ReadFile(historyPath)
	if readErr != nil && !os.IsNotExist(readErr) {
		return nil, readErr
	}
	history := make([]map[string]any, 0, 2)
	for lineNumber, line := range strings.Split(string(historyBytes), "\n") {
		if strings.TrimSpace(line) == "" {
			continue
		}
		var record map[string]any
		if err := json.Unmarshal([]byte(line), &record); err != nil {
			return nil, fmt.Errorf("checker: histórico inválido na linha %d", lineNumber+1)
		}
		if record == nil {
			return nil, fmt.Errorf("checker: histórico inválido na linha %d", lineNumber+1)
		}
		history = append(history, record)
	}
	if len(history) >= 2 || (len(history) > 0 && stateString(history[len(history)-1]["verdict"]) == "blocked") {
		return nil, &commandError{message: "BLOQUEADO: checker atingiu o máximo de duas revisões", exitCode: 3}
	}
	report, err := legacyCheckerReport(reportPath)
	if err != nil {
		return nil, err
	}
	packageFiles := stateStringSlice(stateObject(stateObject(state["approval"])["package"])["files"])
	review := stateString(planning["review"])
	inputFiles := make([]string, 0, len(packageFiles))
	for _, relative := range packageFiles {
		if relative != review {
			inputFiles = append(inputFiles, relative)
		}
	}
	manifest, err := legacyBuildManifest(root, inputFiles)
	if err != nil {
		return nil, err
	}
	packageDigest := sha256Bytes(manifest)
	reportDigest, _ := legacyFileDigest(reportPath)
	round := len(history) + 1
	if round == 2 {
		previous := history[len(history)-1]
		if !oneOf(stateString(previous["verdict"]), "changes_requested", "passed") {
			return nil, &commandError{message: "BLOQUEADO: segunda revisão não foi autorizada", exitCode: 3}
		}
		if stateString(previous["package_digest"]) == packageDigest {
			return nil, &commandError{message: "BLOQUEADO: segunda revisão exige correção factual no pacote", exitCode: 3}
		}
		if stateString(previous["report_digest"]) == reportDigest {
			return nil, &commandError{message: "BLOQUEADO: segunda revisão exige relatório novo para o pacote corrigido", exitCode: 3}
		}
		if stateString(report["verdict"]) == "changes_requested" {
			return nil, &commandError{message: "BLOQUEADO: segunda revisão deve aprovar ou bloquear", exitCode: 3}
		}
	}
	record := map[string]any{
		"schema_version": 1, "round": round, "recorded_at": time.Now().UTC().Format("2006-01-02T15:04:05.999999999+00:00"),
		"package_digest": packageDigest, "report_digest": reportDigest,
		"verdict": report["verdict"], "findings": report["findings"],
	}
	recordBytes, _ := legacyCompactJSON(record)
	nextHistory := append(append([]byte(nil), historyBytes...), append(recordBytes, '\n')...)
	checker["status"] = report["verdict"]
	checker["rounds"] = round
	checker["package_digest"] = packageDigest
	checker["report_digest"] = reportDigest
	stateBytes, _ := legacyJSONBytes(state, true)
	oldState, _ := os.ReadFile(statePath)
	if err := atomicWrite(historyPath, nextHistory); err != nil {
		return nil, err
	}
	if err := atomicWrite(statePath, stateBytes); err != nil {
		_ = atomicWrite(statePath, oldState)
		if len(historyBytes) == 0 {
			_ = os.Remove(historyPath)
		} else {
			_ = atomicWrite(historyPath, historyBytes)
		}
		return nil, err
	}
	nextAction := "planning_blocked"
	if stateString(report["verdict"]) == "passed" {
		nextAction = "freeze_and_request_approval"
	} else if stateString(report["verdict"]) == "changes_requested" {
		nextAction = "apply_single_correction"
	}
	return map[string]any{
		"recorded": true, "round": round, "status": report["verdict"],
		"package_digest": packageDigest, "report_digest": reportDigest,
		"history_path": filepath.ToSlash(historyValue), "next_action": nextAction,
	}, nil
}

func legacyCheckerReport(path string) (map[string]any, error) {
	report, err := legacyReadJSONDocument(path, "checker")
	if err != nil {
		return nil, err
	}
	verdict := stateString(report["verdict"])
	if !oneOf(verdict, "passed", "changes_requested", "blocked") {
		return nil, fmt.Errorf("checker: verdict inválido")
	}
	findings, ok := report["findings"].([]any)
	if !ok {
		return nil, fmt.Errorf("checker: findings deve ser lista")
	}
	material := 0
	identifiers := make(map[string]bool, len(findings))
	for index, rawFinding := range findings {
		finding := stateObject(rawFinding)
		severity := stateString(finding["severity"])
		if !oneOf(severity, "critical", "important", "minor", "note") {
			return nil, fmt.Errorf("checker: finding %d tem severity inválida", index)
		}
		for _, field := range []string{"id", "summary", "evidence"} {
			if strings.TrimSpace(stateString(finding[field])) == "" {
				return nil, fmt.Errorf("checker: finding %d sem %s", index, field)
			}
		}
		identifier := strings.TrimSpace(stateString(finding["id"]))
		if identifiers[identifier] {
			return nil, fmt.Errorf("checker: IDs de findings duplicados")
		}
		identifiers[identifier] = true
		if severity == "critical" || severity == "important" {
			material++
		}
	}
	if verdict == "passed" && material > 0 {
		return nil, fmt.Errorf("checker: passed não aceita finding critical/important")
	}
	if (verdict == "changes_requested" || verdict == "blocked") && material == 0 {
		return nil, fmt.Errorf("checker: %s exige finding critical/important", verdict)
	}
	return report, nil
}
