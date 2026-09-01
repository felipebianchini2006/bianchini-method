package gokernel

import (
	_ "embed"
	"encoding/json"
	"fmt"
	"math"
	"os"
	"reflect"
	"regexp"
	"sort"
	"strings"
)

//go:embed assets/project-state.schema.json
var defaultStateSchema []byte

var (
	jsonFencePattern     = regexp.MustCompile("(?is)```json\\s*(.*?)\\s*```")
	jsonFenceStart       = regexp.MustCompile("(?i)```json\\b")
	methodVersionPattern = regexp.MustCompile(`(?m)^\s*method_version:\s*(\d+)\s*(?:#.*)?$`)
	hexDigestPattern     = regexp.MustCompile(`^[0-9a-f]{64}$`)
)

func runValidateState(args []string) (any, error) {
	flags := parsedFlags{values: map[string][]string{}, booleans: map[string]bool{}}
	positionals := make([]string, 0, 1)
	for index := 0; index < len(args); index++ {
		if args[index] == "--schema" {
			if index+1 >= len(args) {
				return nil, argparseError("argument --schema: expected one argument")
			}
			index++
			flags.values["--schema"] = append(flags.values["--schema"], args[index])
			continue
		}
		if strings.HasPrefix(args[index], "--") {
			return nil, argparseError("unrecognized arguments: " + args[index])
		}
		positionals = append(positionals, args[index])
	}
	if len(positionals) == 0 {
		return nil, argparseError("the following arguments are required: state")
	}
	if len(positionals) > 1 {
		return nil, argparseError("unrecognized arguments: " + strings.Join(positionals[1:], " "))
	}
	state, err := validateStateFile(positionals[0], lastValue(flags, "--schema"))
	if err != nil {
		return nil, err
	}
	return map[string]any{"valid": true, "method_version": stateInt(state["method_version"])}, nil
}

func validateStateFile(path, schemaPath string) (map[string]any, error) {
	state, err := loadStateFile(path)
	if err != nil {
		return nil, err
	}
	if stateInt(state["method_version"]) != 2 {
		return nil, stateError("schema v2 não deve validar projeto legado", 2)
	}
	schemaBytes := defaultStateSchema
	if schemaPath != "" {
		safe, err := safeStandaloneFile(schemaPath, "schema")
		if err != nil {
			return nil, pathSafetyError(err)
		}
		schemaBytes, err = os.ReadFile(safe)
		if err != nil {
			return nil, stateError("erro de entrada/IO: "+err.Error(), 2)
		}
	}
	schemaValue, err := decodeJSONObject(schemaBytes)
	if err != nil {
		return nil, stateError("erro de entrada/IO: schema JSON inválido", 2)
	}
	errors := validateSchemaNode(state, schemaValue, schemaValue, "state")
	if len(errors) == 0 {
		errors = semanticStateErrors(state)
	}
	if len(errors) > 0 {
		return nil, stateError("estado inválido:\n- "+strings.Join(errors, "\n- "), 2)
	}
	return state, nil
}

func loadStateFile(path string) (map[string]any, error) {
	info, err := os.Lstat(path)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, stateError("estado não encontrado: "+path, 2)
		}
		return nil, stateError("erro de entrada/IO: "+err.Error(), 2)
	}
	if info.Mode()&os.ModeSymlink != 0 {
		return nil, stateError("PATH_SAFETY: status não aceita symlink", 3)
	}
	if !info.Mode().IsRegular() {
		return nil, stateError("estado não encontrado: "+path, 2)
	}
	content, err := os.ReadFile(path)
	if err != nil {
		return nil, stateError("erro de entrada/IO: "+err.Error(), 2)
	}
	if !validUTF8Text(content) {
		return nil, stateError("erro de entrada/IO: estado deve ser UTF-8 textual", 2)
	}
	text := string(content)
	candidate := strings.TrimSpace(text)
	if match := jsonFencePattern.FindStringSubmatch(text); match != nil {
		candidate = strings.TrimSpace(match[1])
	}
	value, decodeErr := decodeJSONAny([]byte(candidate))
	if decodeErr != nil {
		if jsonFenceStart.MatchString(text) || strings.HasPrefix(candidate, "{") || strings.HasPrefix(candidate, "[") {
			line := jsonErrorLine([]byte(candidate), decodeErr)
			return nil, stateError(fmt.Sprintf("BLOQUEADO: PROJECT_STATE inválido: JSON corrompido na linha %d", line), 3)
		}
		matches := methodVersionPattern.FindAllStringSubmatch(text, -1)
		versions := map[string]bool{}
		for _, match := range matches {
			versions[match[1]] = true
		}
		if len(matches) > 1 || len(versions) > 1 {
			return nil, stateError("BLOQUEADO: PROJECT_STATE inválido: method_version duplicado ou conflitante", 3)
		}
		if versions["1"] {
			return map[string]any{"method_version": float64(1), "_legacy_text": text}, nil
		}
		if len(versions) > 0 {
			return nil, stateError("BLOQUEADO: estado v2 deve ser JSON válido; versão declarada não suportada", 3)
		}
		return nil, stateError("BLOQUEADO: não foi possível determinar method_version com segurança", 3)
	}
	state, ok := value.(map[string]any)
	if !ok {
		return nil, stateError("PROJECT_STATE deve ser um objeto", 2)
	}
	if _, ok := state["method_version"]; !ok {
		return nil, stateError("BLOQUEADO: não foi possível determinar method_version com segurança", 3)
	}
	return state, nil
}

func decodeJSONAny(content []byte) (any, error) {
	var value any
	if err := json.Unmarshal(content, &value); err != nil {
		return nil, err
	}
	return value, nil
}

func decodeJSONObject(content []byte) (map[string]any, error) {
	value, err := decodeJSONAny(content)
	if err != nil {
		return nil, err
	}
	object, ok := value.(map[string]any)
	if !ok {
		return nil, fmt.Errorf("expected object")
	}
	return object, nil
}

func jsonErrorLine(content []byte, err error) int {
	offset := int64(1)
	if syntax, ok := err.(*json.SyntaxError); ok {
		offset = syntax.Offset
	}
	if offset < 1 {
		offset = 1
	}
	if offset > int64(len(content))+1 {
		offset = int64(len(content)) + 1
	}
	return bytesLine(content[:offset-1])
}

func bytesLine(prefix []byte) int {
	line := 1
	for _, value := range prefix {
		if value == '\n' {
			line++
		}
	}
	return line
}

func validateSchemaNode(value any, rule, schema map[string]any, at string) []string {
	if reference, ok := rule["$ref"].(string); ok {
		resolved, err := localSchemaRef(schema, reference)
		if err != nil {
			return []string{at + ": " + err.Error()}
		}
		return validateSchemaNode(value, resolved, schema, at)
	}
	errors := make([]string, 0)
	if expected, ok := rule["const"]; ok && !reflect.DeepEqual(value, expected) {
		errors = append(errors, fmt.Sprintf("%s: esperado %v", at, expected))
	}
	if rawEnum, ok := rule["enum"].([]any); ok {
		matched := false
		for _, candidate := range rawEnum {
			if reflect.DeepEqual(value, candidate) {
				matched = true
				break
			}
		}
		if !matched {
			errors = append(errors, fmt.Sprintf("%s: valor %v fora de %v", at, value, rawEnum))
		}
	}
	allowed := schemaTypes(rule["type"])
	if len(allowed) > 0 {
		valid := false
		for _, expected := range allowed {
			if matchesSchemaType(value, expected) {
				valid = true
				break
			}
		}
		if !valid {
			return []string{fmt.Sprintf("%s: tipo inválido; esperado %v", at, allowed)}
		}
	}
	if number, ok := value.(float64); ok && math.Trunc(number) == number {
		if minimum, ok := rule["minimum"].(float64); ok && number < minimum {
			errors = append(errors, fmt.Sprintf("%s: menor que minimum %v", at, minimum))
		}
		if maximum, ok := rule["maximum"].(float64); ok && number > maximum {
			errors = append(errors, fmt.Sprintf("%s: maior que maximum %v", at, maximum))
		}
	}
	if object, ok := value.(map[string]any); ok {
		if required, ok := rule["required"].([]any); ok {
			for _, rawKey := range required {
				key, _ := rawKey.(string)
				if _, exists := object[key]; !exists {
					errors = append(errors, at+"."+key+": campo obrigatório ausente")
				}
			}
		}
		properties, _ := rule["properties"].(map[string]any)
		for key, child := range object {
			childRule, ok := properties[key].(map[string]any)
			if ok {
				errors = append(errors, validateSchemaNode(child, childRule, schema, at+"."+key)...)
			}
		}
	}
	if array, ok := value.([]any); ok {
		if minimum, ok := rule["minItems"].(float64); ok && len(array) < int(minimum) {
			errors = append(errors, at+": lista menor que minItems")
		}
		if itemRule, ok := rule["items"].(map[string]any); ok {
			for index, child := range array {
				errors = append(errors, validateSchemaNode(child, itemRule, schema, fmt.Sprintf("%s[%d]", at, index))...)
			}
		}
	}
	if text, ok := value.(string); ok {
		if pattern, ok := rule["pattern"].(string); ok {
			matches := false
			if pattern == `^(?!/)(?!.*(?:^|/)\.\.(?:/|$)).+` {
				matches = text != "" && !strings.HasPrefix(text, "/")
				for _, part := range strings.Split(text, "/") {
					if part == ".." {
						matches = false
					}
				}
			} else if compiled, err := regexp.Compile(pattern); err == nil {
				matches = compiled.MatchString(text)
			}
			if !matches {
				errors = append(errors, at+": não corresponde a "+pattern)
			}
		}
	}
	return errors
}

func localSchemaRef(schema map[string]any, reference string) (map[string]any, error) {
	if !strings.HasPrefix(reference, "#/") {
		return nil, fmt.Errorf("$ref externo não suportado: %s", reference)
	}
	var current any = schema
	for _, part := range strings.Split(strings.TrimPrefix(reference, "#/"), "/") {
		object, ok := current.(map[string]any)
		if !ok {
			return nil, fmt.Errorf("$ref inválido: %s", reference)
		}
		part = strings.ReplaceAll(strings.ReplaceAll(part, "~1", "/"), "~0", "~")
		current, ok = object[part]
		if !ok {
			return nil, fmt.Errorf("$ref inválido: %s", reference)
		}
	}
	result, ok := current.(map[string]any)
	if !ok {
		return nil, fmt.Errorf("$ref inválido: %s", reference)
	}
	return result, nil
}

func schemaTypes(raw any) []string {
	if value, ok := raw.(string); ok {
		return []string{value}
	}
	values, _ := raw.([]any)
	result := make([]string, 0, len(values))
	for _, value := range values {
		if text, ok := value.(string); ok {
			result = append(result, text)
		}
	}
	return result
}

func matchesSchemaType(value any, expected string) bool {
	switch expected {
	case "object":
		_, ok := value.(map[string]any)
		return ok
	case "array":
		_, ok := value.([]any)
		return ok
	case "string":
		_, ok := value.(string)
		return ok
	case "integer":
		number, ok := value.(float64)
		return ok && math.Trunc(number) == number
	case "number":
		_, ok := value.(float64)
		return ok
	case "boolean":
		_, ok := value.(bool)
		return ok
	case "null":
		return value == nil
	default:
		return false
	}
}

func semanticStateErrors(state map[string]any) []string {
	errors := make([]string, 0)
	approval := stateObject(state["approval"])
	plans := stateArray(state["plans"])
	planning := stateObject(state["planning"])
	planningStatus := stateString(state["planning_status"])
	planIDs := make([]string, 0, len(plans))
	for _, rawPlan := range plans {
		planIDs = append(planIDs, stateString(stateObject(rawPlan)["id"]))
	}
	if len(plans) == 0 && planningStatus != "idle" && planningStatus != "in_progress" {
		errors = append(errors, "state.plans: ao menos um plano é obrigatório fora de idle/in_progress")
	}
	if planningStatus == "idle" {
		expectedScope := map[string]any{"status": "pending", "source": nil, "approved_at": nil}
		if !reflect.DeepEqual(stateObject(state["scope"]), expectedScope) {
			errors = append(errors, "state.scope: idle exige escopo pendente e sem fonte aprovada")
		}
		for _, field := range []string{"research", "readiness", "user_actions", "spec", "review", "checker", "design_manifest", "change_root"} {
			if planning[field] != nil {
				errors = append(errors, "state.planning: idle não pode apontar pesquisa, readiness, spec, revisão ou mudança")
				break
			}
		}
		if current, exists := planning["current_specs"]; exists && current != nil && strings.TrimSpace(stateString(current)) == "" {
			errors = append(errors, "state.planning.current_specs: idle exige caminho válido ou null")
		}
		if complexity, ok := state["complexity_review"].(map[string]any); ok {
			if stateString(complexity["decision"]) != "pending" || complexity["justification"] != nil ||
				len(stateArray(complexity["deferred_scope"])) != 0 || stateBool(complexity["scope_split_approved"]) ||
				complexity["scope_split_approved_by"] != nil || complexity["scope_split_approved_at"] != nil {
				errors = append(errors, "state.complexity_review: idle exige revisão pendente e vazia")
			}
		}
		if stateString(approval["status"]) != "pending" {
			errors = append(errors, "state.approval.status: idle exige aprovação pending")
		}
		if approval["approved_at"] != nil || approval["approved_by"] != nil {
			errors = append(errors, "state.approval: idle não pode conter aprovação anterior")
		}
		if len(stateArray(approval["approved_plans"])) > 0 {
			errors = append(errors, "state.approval.approved_plans: idle exige lista vazia")
		}
		pkg := stateObject(approval["package"])
		if pkg["manifest_digest"] != nil {
			errors = append(errors, "state.approval.package.manifest_digest: idle exige null")
		}
		if len(stateArray(pkg["files"])) > 0 {
			errors = append(errors, "state.approval.package.files: idle exige lista vazia")
		}
		if len(plans) > 0 {
			errors = append(errors, "state.plans: idle exige lista vazia")
		}
		if state["active_execution"] != nil {
			errors = append(errors, "state.active_execution: idle exige null")
		}
		idleVerification := map[string]any{
			"fast":    map[string]any{"commands": []any{}, "status": "pending"},
			"plan":    map[string]any{"commands": []any{}, "status": "pending"},
			"release": map[string]any{"commands": []any{}, "status": "pending"},
		}
		if !reflect.DeepEqual(stateObject(state["verification"]), idleVerification) {
			errors = append(errors, "state.verification: idle exige gates pendentes e sem comandos")
		}
		idleRelease := map[string]any{
			"status": "pending", "platforms": []any{}, "profiles": []any{}, "candidate": nil,
			"final_gate": "homologar-sistema", "homologation": "pending",
			"final_review": "pending", "delivery": "pending",
		}
		if !reflect.DeepEqual(stateObject(state["release"]), idleRelease) {
			errors = append(errors, "state.release: idle exige release reinicializado")
		}
		if stateString(state["architecture_audit_status"]) != "not_run" {
			errors = append(errors, "state.architecture_audit_status: idle exige not_run")
		}
		if len(stateArray(state["blockers"])) > 0 {
			errors = append(errors, "state.blockers: idle exige lista vazia")
		}
		if stateBool(stateObject(state["telemetry"])["enabled"]) {
			errors = append(errors, "state.telemetry.enabled: idle exige false")
		}
	} else {
		scope := stateObject(state["scope"])
		if stateString(scope["status"]) != "approved" || stateString(scope["source"]) == "" {
			errors = append(errors, "state.scope: ciclo ativo exige escopo aprovado e fonte local")
		}
		if stateString(planning["spec"]) == "" || stateString(planning["review"]) == "" {
			errors = append(errors, "state.planning: ciclo ativo exige spec e revisão")
		}
		quality := stateInt(planning["quality_version"])
		if quality == 1 || quality == 2 {
			if stateString(planning["research"]) == "" {
				errors = append(errors, fmt.Sprintf("state.planning.research: contrato de qualidade v%d exige pesquisa", quality))
			}
			if _, ok := state["complexity_review"].(map[string]any); !ok {
				errors = append(errors, fmt.Sprintf("state.complexity_review: contrato de qualidade v%d exige revisão de complexidade", quality))
			}
		}
		if quality == 2 {
			for _, field := range []string{"readiness", "user_actions", "change_root", "current_specs"} {
				if strings.TrimSpace(stateString(planning[field])) == "" {
					errors = append(errors, "state.planning."+field+": contrato de qualidade v2 exige caminho")
				}
			}
			checker, ok := planning["checker"].(map[string]any)
			if !ok {
				errors = append(errors, "state.planning.checker: contrato de qualidade v2 exige objeto")
			} else if stateString(approval["status"]) == "approved" {
				if stateString(checker["status"]) != "passed" {
					errors = append(errors, "state.planning.checker.status: aprovação exige passed")
				}
				rounds := stateInt(checker["rounds"])
				if rounds != 1 && rounds != 2 {
					errors = append(errors, "state.planning.checker.rounds: aprovação exige 1 ou 2")
				}
				for _, digestField := range []string{"package_digest", "report_digest"} {
					if !hexDigestPattern.MatchString(stateString(checker[digestField])) {
						errors = append(errors, "state.planning.checker."+digestField+": aprovação exige digest válido")
					}
				}
			}
		}
	}
	if hasDuplicates(planIDs) {
		errors = append(errors, "state.plans: IDs duplicados")
	}
	planSet := stringSet(planIDs)
	if active, ok := state["active_execution"].(map[string]any); ok {
		activeID := stateString(active["plan_id"])
		if !planSet[activeID] {
			errors = append(errors, "state.active_execution.plan_id: plano inexistente")
		} else {
			for _, rawPlan := range plans {
				plan := stateObject(rawPlan)
				if stateString(plan["id"]) == activeID && stateString(plan["status"]) != "in_progress" {
					errors = append(errors, "state.active_execution.plan_id: plano ativo deve estar in_progress")
				}
			}
		}
	}
	for index, rawPlan := range plans {
		plan := stateObject(rawPlan)
		risk := stateString(plan["risk"])
		execution := stateString(plan["execution"])
		minimum := map[string]string{"low": "grouped", "medium": "slice", "high": "strict", "critical": "strict"}[risk]
		rank := map[string]int{"grouped": 0, "slice": 1, "strict": 2}
		if rank[execution] < rank[minimum] {
			errors = append(errors, fmt.Sprintf("state.plans[%d].execution: garantia abaixo do risco", index))
		}
		if stateString(plan["review"]) != map[string]string{"grouped": "plan_gate", "slice": "per_slice", "strict": "per_task"}[execution] {
			errors = append(errors, fmt.Sprintf("state.plans[%d].review: incompatível com execution", index))
		}
		for _, dependency := range stateStringSlice(plan["depends_on"]) {
			if !planSet[dependency] {
				errors = append(errors, fmt.Sprintf("state.plans[%d].depends_on: plano inexistente %q", index, dependency))
			}
			if dependency == stateString(plan["id"]) {
				errors = append(errors, fmt.Sprintf("state.plans[%d].depends_on: autodependência", index))
			}
		}
	}
	if stateGraphCyclic(plans) {
		errors = append(errors, "state.plans: ciclo de dependências detectado")
	}
	if stateString(approval["status"]) == "approved" {
		pkg := stateObject(approval["package"])
		if !hexDigestPattern.MatchString(stateString(pkg["manifest_digest"])) {
			errors = append(errors, "state.approval.package.manifest_digest: digest aprovado inválido")
		}
		approvedPlans := stringSet(stateStringSlice(approval["approved_plans"]))
		if !sameStringSet(approvedPlans, planSet) {
			errors = append(errors, "state.approval.approved_plans: aprovação deve cobrir todos os planos")
		}
		packageFiles := stringSet(stateStringSlice(pkg["files"]))
		contractFiles := map[string]bool{
			stateString(stateObject(state["scope"])["source"]): true,
			stateString(planning["spec"]):                      true,
			stateString(planning["review"]):                    true,
		}
		for _, rawPlan := range plans {
			contractFiles[stateString(stateObject(rawPlan)["path"])] = true
		}
		if research := stateString(planning["research"]); research != "" {
			contractFiles[research] = true
		}
		if stateInt(planning["quality_version"]) == 2 {
			for _, field := range []string{"readiness", "user_actions", "design_manifest"} {
				if value := stateString(planning[field]); value != "" {
					contractFiles[value] = true
				}
			}
		}
		missing := make([]string, 0)
		for path := range contractFiles {
			if path != "" && !packageFiles[path] {
				missing = append(missing, path)
			}
		}
		sort.Strings(missing)
		if len(missing) > 0 {
			errors = append(errors, "state.approval.package.files: pacote aprovado não contém "+strings.Join(missing, ", "))
		}
		for index, rawPlan := range plans {
			if stateString(stateObject(rawPlan)["status"]) == "planned" {
				errors = append(errors, fmt.Sprintf("state.plans[%d].status: plano aprovado não pode permanecer planned", index))
			}
		}
		if planningStatus != "approved" {
			errors = append(errors, "state.planning_status: deve ser approved após aprovação")
		}
	}
	release := stateObject(state["release"])
	releaseStatus := stateString(release["status"])
	if oneOf(releaseStatus, "candidate", "homologated", "ready") && release["candidate"] == nil {
		errors = append(errors, "state.release.candidate: obrigatório para RC ativo")
	}
	if candidate, ok := release["candidate"].(map[string]any); ok {
		missing := make([]string, 0)
		for _, field := range []string{"id", "revision", "build", "checksum"} {
			if stateString(candidate[field]) == "" {
				missing = append(missing, field)
			}
		}
		if len(missing) > 0 {
			errors = append(errors, "state.release.candidate: fingerprint incompleto; ausente "+strings.Join(missing, ", "))
		}
	}
	if oneOf(releaseStatus, "homologated", "ready") && stateString(release["homologation"]) != "accepted" {
		errors = append(errors, "state.release.homologation: deve estar accepted")
	}
	if releaseStatus == "ready" && (stateString(release["final_review"]) != "approved" || stateString(release["delivery"]) != "ready") {
		errors = append(errors, "state.release: ready exige revisão e entrega aprovadas")
	}
	return errors
}

func stateGraphCyclic(plans []any) bool {
	graph := map[string][]string{}
	for _, rawPlan := range plans {
		plan := stateObject(rawPlan)
		graph[stateString(plan["id"])] = stateStringSlice(plan["depends_on"])
	}
	visiting := map[string]bool{}
	visited := map[string]bool{}
	var visit func(string) bool
	visit = func(identifier string) bool {
		if visiting[identifier] {
			return true
		}
		if visited[identifier] {
			return false
		}
		visiting[identifier] = true
		for _, dependency := range graph[identifier] {
			if _, ok := graph[dependency]; ok && visit(dependency) {
				return true
			}
		}
		delete(visiting, identifier)
		visited[identifier] = true
		return false
	}
	for identifier := range graph {
		if visit(identifier) {
			return true
		}
	}
	return false
}

func stateObject(value any) map[string]any {
	object, _ := value.(map[string]any)
	if object == nil {
		return map[string]any{}
	}
	return object
}

func stateArray(value any) []any {
	array, _ := value.([]any)
	return array
}

func stateString(value any) string {
	text, _ := value.(string)
	return text
}

func stateBool(value any) bool {
	boolean, _ := value.(bool)
	return boolean
}

func stateInt(value any) int {
	switch number := value.(type) {
	case int:
		return number
	case int64:
		return int(number)
	case float64:
		return int(number)
	case json.Number:
		parsed, _ := number.Int64()
		return int(parsed)
	default:
		return 0
	}
}

func stateStringSlice(value any) []string {
	array := stateArray(value)
	result := make([]string, 0, len(array))
	for _, item := range array {
		if text, ok := item.(string); ok {
			result = append(result, text)
		}
	}
	return result
}

func stringSet(values []string) map[string]bool {
	result := make(map[string]bool, len(values))
	for _, value := range values {
		result[value] = true
	}
	return result
}

func sameStringSet(left, right map[string]bool) bool {
	return reflect.DeepEqual(left, right)
}

func hasDuplicates(values []string) bool {
	return len(stringSet(values)) != len(values)
}

func stateError(message string, exitCode int) error {
	return &commandError{message: message, exitCode: exitCode}
}

func pathSafetyError(err error) error {
	return stateError(err.Error(), 3)
}
