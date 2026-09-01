package gokernel

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
)

var modelIDPattern = regexp.MustCompile(`^[A-Za-z][A-Za-z0-9_.:-]*$`)

type projectModel struct {
	sections map[string]map[string]map[string]any
}

type planContract struct {
	id         string
	schema     int
	modelDelta map[string]any
	value      map[string]any
}

func readStructuredFrontmatter(path string) (map[string]any, error) {
	info, err := os.Lstat(path)
	if err != nil || info.Mode()&os.ModeSymlink != 0 || !info.Mode().IsRegular() {
		return nil, fmt.Errorf("documento ausente: %s", path)
	}
	content, err := os.ReadFile(path)
	if err != nil || !validUTF8Text(content) {
		return nil, fmt.Errorf("documento inválido: %s", path)
	}
	match := frontmatterPattern.FindSubmatch(content)
	if match == nil {
		return nil, fmt.Errorf("frontmatter ausente: %s", path)
	}
	raw := strings.TrimSpace(string(match[1]))
	if raw == "" {
		return map[string]any{}, nil
	}
	value, err := decodeJSONObject([]byte(raw))
	if err == nil {
		return value, nil
	}
	parsed, yamlErr := parseYAMLSubset(raw)
	if yamlErr != nil {
		return nil, yamlErr
	}
	return parsed, nil
}

func loadProjectModel(path string) (projectModel, error) {
	value, err := readStructuredFrontmatter(path)
	if err != nil {
		return projectModel{}, err
	}
	return projectModelFromMapping(value)
}

func projectModelFromMapping(value map[string]any) (projectModel, error) {
	for _, key := range sortedMapKeys(value) {
		if key != "schema_version" && !containsString(modelCollections, key) {
			return projectModel{}, fmt.Errorf("seção desconhecida no ProjectModel: %s", key)
		}
	}
	if schema, exists := value["schema_version"]; exists && stateInt(schema) != 1 {
		return projectModel{}, fmt.Errorf("ProjectModel exige schema_version 1")
	}
	result := projectModel{sections: map[string]map[string]map[string]any{}}
	for _, section := range modelCollections {
		normalized, err := normalizeModelSection(section, value[section])
		if err != nil {
			return projectModel{}, err
		}
		result.sections[section] = normalized
	}
	return result, nil
}

func normalizeModelSection(section string, raw any) (map[string]map[string]any, error) {
	entries := []any{}
	if raw == nil {
		raw = []any{}
	}
	switch value := raw.(type) {
	case []any:
		entries = value
	case map[string]any:
		keys := sortedMapKeys(value)
		for _, identifier := range keys {
			entry, ok := value[identifier].(map[string]any)
			if !ok {
				return nil, fmt.Errorf("%s.%s exige objeto", section, identifier)
			}
			copy := cloneMap(entry)
			copy["id"] = identifier
			entries = append(entries, copy)
		}
	default:
		return nil, fmt.Errorf("ProjectModel.%s exige lista", section)
	}
	result := map[string]map[string]any{}
	for _, rawEntry := range entries {
		entry, err := normalizeModelEntry(section, rawEntry)
		if err != nil {
			return nil, err
		}
		identifier := stateString(entry["id"])
		if _, exists := result[identifier]; exists {
			return nil, fmt.Errorf("ID duplicado em %s: %s", section, identifier)
		}
		result[identifier] = entry
	}
	return result, nil
}

func normalizeModelEntry(section string, raw any) (map[string]any, error) {
	entry, ok := raw.(map[string]any)
	if !ok {
		return nil, fmt.Errorf("%s exige itens com id", section)
	}
	identifier := stateString(entry["id"])
	if !modelIDPattern.MatchString(identifier) {
		return nil, fmt.Errorf("%s exige id válido", section)
	}
	copy := cloneMap(entry)
	copy["id"] = identifier
	return copy, nil
}

func (model projectModel) mapping() map[string]any {
	result := map[string]any{"schema_version": 1}
	for _, section := range modelCollections {
		indexed := model.sections[section]
		keys := make([]string, 0, len(indexed))
		for key := range indexed {
			keys = append(keys, key)
		}
		sort.Strings(keys)
		entries := make([]any, 0, len(keys))
		for _, key := range keys {
			entries = append(entries, cloneMap(indexed[key]))
		}
		result[section] = entries
	}
	return result
}

func (model projectModel) digest() string {
	encoded, _ := canonicalJSON(model.mapping())
	return sha256Bytes(encoded)
}

func (model projectModel) differences(expected projectModel) map[string]any {
	result := map[string]any{}
	for _, section := range modelCollections {
		current := model.sections[section]
		future := expected.sections[section]
		added, removed, changed := []string{}, []string{}, []string{}
		for identifier, entry := range future {
			currentEntry, exists := current[identifier]
			if !exists {
				added = append(added, identifier)
			} else if !mapsEqual(currentEntry, entry) {
				changed = append(changed, identifier)
			}
		}
		for identifier := range current {
			if _, exists := future[identifier]; !exists {
				removed = append(removed, identifier)
			}
		}
		sort.Strings(added)
		sort.Strings(removed)
		sort.Strings(changed)
		if len(added)+len(removed)+len(changed) > 0 {
			result[section] = map[string]any{"added": added, "removed": removed, "changed": changed}
		}
	}
	return result
}

func (model projectModel) applyDelta(delta map[string]any) (projectModel, error) {
	if len(delta) == 0 {
		return model, nil
	}
	for _, section := range sortedMapKeys(delta) {
		if !containsString(modelCollections, section) {
			return projectModel{}, fmt.Errorf("seção desconhecida em model_delta: %s", section)
		}
	}
	result, _ := projectModelFromMapping(model.mapping())
	for _, section := range sortedMapKeys(delta) {
		rawOperations := delta[section]
		operationMap := map[string]any{}
		switch operations := rawOperations.(type) {
		case []any:
			operationMap["upsert"] = operations
		case map[string]any:
			operationMap = operations
		default:
			return projectModel{}, fmt.Errorf("model_delta.%s exige lista ou objeto", section)
		}
		for _, operation := range sortedMapKeys(operationMap) {
			if !oneOf(operation, "add", "update", "upsert", "remove") {
				return projectModel{}, fmt.Errorf("operação desconhecida em model_delta.%s: %s", section, operation)
			}
		}
		target := result.sections[section]
		for _, operation := range []string{"add", "update", "upsert", "remove"} {
			items, err := sequenceValue(operationMap[operation], section+"."+operation)
			if err != nil {
				return projectModel{}, err
			}
			for _, raw := range items {
				if operation == "remove" {
					identifier := ""
					if text, ok := raw.(string); ok {
						identifier = text
					} else if entry, ok := raw.(map[string]any); ok {
						identifier = stateString(entry["id"])
					}
					if identifier == "" {
						return projectModel{}, fmt.Errorf("%s.remove exige IDs", section)
					}
					if _, exists := target[identifier]; !exists {
						return projectModel{}, fmt.Errorf("%s.%s não existe", section, identifier)
					}
					delete(target, identifier)
					continue
				}
				entry, err := normalizeModelEntry(section, raw)
				if err != nil {
					return projectModel{}, err
				}
				identifier := stateString(entry["id"])
				current, exists := target[identifier]
				switch operation {
				case "add":
					if exists {
						return projectModel{}, fmt.Errorf("%s.%s já existe", section, identifier)
					}
					target[identifier] = entry
				case "update":
					if !exists {
						return projectModel{}, fmt.Errorf("%s.%s não existe", section, identifier)
					}
					target[identifier] = mergeMaps(current, entry)
				case "upsert":
					target[identifier] = mergeMaps(current, entry)
				}
			}
		}
	}
	return result, nil
}

func loadPlanContract(path string) (planContract, error) {
	value, err := readStructuredFrontmatter(path)
	if err != nil {
		return planContract{}, err
	}
	return parsePlanContract(value)
}

func parsePlanContract(value map[string]any) (planContract, error) {
	identifier := strings.TrimSpace(stateString(value["id"]))
	if identifier == "" {
		return planContract{}, fmt.Errorf("plano exige id")
	}
	delta, ok := value["model_delta"].(map[string]any)
	if value["model_delta"] == nil {
		delta, ok = map[string]any{}, true
	}
	if !ok {
		return planContract{}, fmt.Errorf("plano %s: model_delta exige objeto", identifier)
	}
	schema := stateInt(value["schema_version"])
	if schema == 0 {
		schema = 1
	}
	if schema != 1 && schema != 2 {
		return planContract{}, fmt.Errorf("plano %s: schema_version exige 1 ou 2", identifier)
	}
	if schema == 2 {
		if err := validatePlanV2(identifier, value); err != nil {
			return planContract{}, err
		}
	} else {
		for _, field := range []string{"depends_on", "provides", "consumes", "touches", "requirements", "acceptance", "verifications", "future_constraints"} {
			if _, err := stringValues(value[field], field); err != nil {
				return planContract{}, err
			}
		}
		owns := value["owns"]
		if owns == nil {
			owns = value["ownership"]
		}
		if _, err := stringValues(owns, "owns"); err != nil {
			return planContract{}, err
		}
		migrations := value["migrations"]
		if migrations == nil {
			migrations = []any{}
		}
		if err := validateMappingList(migrations, "migrations"); err != nil {
			return planContract{}, err
		}
		effects := value["external_effects"]
		if effects == nil {
			effects = value["effects"]
		}
		if effects == nil {
			effects = []any{}
		}
		if err := validateMappingList(effects, "external_effects"); err != nil {
			return planContract{}, err
		}
	}
	return planContract{id: identifier, schema: schema, modelDelta: cloneMap(delta), value: value}, nil
}

func validatePlanV2(identifier string, value map[string]any) error {
	fields := []string{
		"schema_version", "id", "status", "result", "requirements", "acceptance", "depends_on",
		"provides", "consumes", "modules", "interfaces", "ownership", "data", "model_delta",
		"migrations", "effects", "rollback", "verifications", "future_constraints", "execution", "review", "tasks",
	}
	allowed := stringSet(fields)
	for _, key := range sortedMapKeys(value) {
		if !allowed[key] {
			return fmt.Errorf("campo desconhecido no plano v2: %s", key)
		}
	}
	missing := missingMapKeys(value, fields)
	if len(missing) > 0 {
		return fmt.Errorf("campo obrigatório ausente no plano v2: %s", missing[0])
	}
	if stateString(value["status"]) != "planned" {
		return fmt.Errorf("plano %s: status exige planned", identifier)
	}
	execution := stateString(value["execution"])
	review := stateString(value["review"])
	expectedReview := map[string]string{"grouped": "plan_gate", "slice": "per_slice", "strict": "per_task"}[execution]
	if expectedReview == "" {
		return fmt.Errorf("plano %s: execution inválido", identifier)
	}
	if review != expectedReview {
		return fmt.Errorf("plano %s: combinação execution/review incompatível", identifier)
	}
	for _, field := range []string{"requirements", "acceptance", "verifications"} {
		values, err := stringValues(value[field], field)
		if err != nil {
			return err
		}
		if len(values) == 0 {
			return fmt.Errorf("plano %s: %s não pode ser vazio", identifier, field)
		}
	}
	for _, field := range []string{"depends_on", "provides", "consumes", "modules", "interfaces", "ownership", "data", "future_constraints"} {
		if _, err := stringValues(value[field], field); err != nil {
			return err
		}
	}
	for _, field := range []string{"result", "rollback"} {
		if strings.TrimSpace(stateString(value[field])) == "" {
			return fmt.Errorf("plano %s.%s exige texto", identifier, field)
		}
	}
	tasks, ok := value["tasks"].([]any)
	if !ok {
		return fmt.Errorf("plano %s: tasks exige lista", identifier)
	}
	for _, rawTask := range tasks {
		if err := validateTask(rawTask); err != nil {
			return err
		}
	}
	for _, field := range []string{"migrations", "effects"} {
		if err := validateMappingList(value[field], field); err != nil {
			return err
		}
	}
	return nil
}

func validateTask(raw any) error {
	task, ok := raw.(map[string]any)
	if !ok {
		return fmt.Errorf("tarefa exige objeto")
	}
	fields := []string{"id", "name", "result", "covers", "depends_on", "files", "action", "verify", "done", "risk_seam"}
	allowed := stringSet(fields)
	for _, key := range sortedMapKeys(task) {
		if !allowed[key] {
			return fmt.Errorf("campo desconhecido na tarefa: %s", key)
		}
	}
	missing := missingMapKeys(task, fields)
	if len(missing) > 0 {
		return fmt.Errorf("campo obrigatório ausente na tarefa: %s", missing[0])
	}
	identifier := strings.TrimSpace(stateString(task["id"]))
	if identifier == "" {
		return fmt.Errorf("tarefa.id exige texto")
	}
	for _, field := range []string{"name", "result", "action", "done", "risk_seam"} {
		if strings.TrimSpace(stateString(task[field])) == "" {
			return fmt.Errorf("%s.%s exige texto", identifier, field)
		}
	}
	files, err := stringValues(task["files"], identifier+".files")
	if err != nil {
		return err
	}
	if len(files) == 0 {
		return fmt.Errorf("%s.files exige ao menos um caminho provável", identifier)
	}
	for _, path := range files {
		if filepath.IsAbs(path) || strings.Contains(path, "\\") || strings.HasPrefix(path, "./") {
			return fmt.Errorf("%s.files contém caminho inseguro: %s", identifier, path)
		}
		for _, part := range strings.Split(filepath.ToSlash(path), "/") {
			if part == ".." {
				return fmt.Errorf("%s.files contém caminho inseguro: %s", identifier, path)
			}
			if part == ".planning" {
				return fmt.Errorf("%s.files referencia namespace estrangeiro: %s", identifier, path)
			}
		}
	}
	covers, err := stringValues(task["covers"], identifier+".covers")
	if err != nil {
		return err
	}
	if len(covers) == 0 {
		return fmt.Errorf("%s.covers exige ao menos um item de escopo", identifier)
	}
	if _, err := stringValues(task["depends_on"], identifier+".depends_on"); err != nil {
		return err
	}
	verification, ok := task["verify"].(map[string]any)
	if !ok {
		return fmt.Errorf("verify exige objeto")
	}
	allowedVerification := stringSet([]string{"kind", "run", "proves"})
	if unknown := unknownMapKeys(verification, allowedVerification); len(unknown) > 0 {
		return fmt.Errorf("campo desconhecido em verify: %s", unknown[0])
	}
	if missing := missingMapKeys(verification, []string{"kind", "run", "proves"}); len(missing) > 0 {
		return fmt.Errorf("campo obrigatório ausente em verify: %s", missing[0])
	}
	if !oneOf(stateString(verification["kind"]), "command", "procedure") {
		return fmt.Errorf("verify.kind exige command ou procedure")
	}
	if strings.TrimSpace(stateString(verification["run"])) == "" || strings.TrimSpace(stateString(verification["proves"])) == "" {
		return fmt.Errorf("verify exige textos não vazios")
	}
	return nil
}

func validateMappingList(raw any, label string) error {
	values, ok := raw.([]any)
	if !ok {
		return fmt.Errorf("%s exige lista de objetos", label)
	}
	for _, value := range values {
		if _, ok := value.(map[string]any); !ok {
			return fmt.Errorf("%s exige lista de objetos", label)
		}
	}
	return nil
}

type yamlLine struct {
	indent int
	text   string
	number int
}

func parseYAMLSubset(raw string) (map[string]any, error) {
	lines := make([]yamlLine, 0)
	for index, source := range strings.Split(raw, "\n") {
		if strings.TrimSpace(source) == "" || strings.HasPrefix(strings.TrimSpace(source), "#") {
			continue
		}
		prefixLength := len(source) - len(strings.TrimLeft(source, " "))
		if strings.Contains(source[:prefixLength], "\t") {
			return nil, fmt.Errorf("YAML inválido na linha %d: tab não suportado", index+1)
		}
		lines = append(lines, yamlLine{prefixLength, strings.TrimSpace(source), index + 1})
	}
	if len(lines) == 0 {
		return map[string]any{}, nil
	}
	if lines[0].indent != 0 {
		return nil, fmt.Errorf("YAML inválido: primeiro campo deve iniciar na coluna zero")
	}
	value, next, err := parseYAMLBlock(lines, 0, 0)
	if err != nil {
		return nil, err
	}
	if next != len(lines) {
		return nil, fmt.Errorf("YAML inválido próximo da linha %d", lines[next].number)
	}
	object, ok := value.(map[string]any)
	if !ok {
		return nil, fmt.Errorf("YAML exige objeto")
	}
	return object, nil
}

func parseYAMLBlock(lines []yamlLine, index, indent int) (any, int, error) {
	if index >= len(lines) || lines[index].indent != indent {
		return nil, index, fmt.Errorf("YAML inválido: indentação inesperada")
	}
	isList := lines[index].text == "-" || strings.HasPrefix(lines[index].text, "- ")
	if isList {
		values := []any{}
		for index < len(lines) && lines[index].indent == indent {
			line := lines[index]
			if line.text != "-" && !strings.HasPrefix(line.text, "- ") {
				break
			}
			remainder := strings.TrimSpace(strings.TrimPrefix(line.text, "-"))
			index++
			if remainder == "" {
				if index >= len(lines) || lines[index].indent <= indent {
					return nil, index, fmt.Errorf("YAML inválido na linha %d: item vazio", line.number)
				}
				value, next, err := parseYAMLBlock(lines, index, lines[index].indent)
				if err != nil {
					return nil, index, err
				}
				values, index = append(values, value), next
				continue
			}
			key, rawValue, mapping := splitYAMLMapping(remainder)
			if mapping {
				item := map[string]any{}
				if rawValue != "" {
					item[key], _ = yamlScalar(rawValue)
				} else if index < len(lines) && lines[index].indent > indent {
					value, next, err := parseYAMLBlock(lines, index, lines[index].indent)
					if err != nil {
						return nil, index, err
					}
					item[key], index = value, next
				} else {
					item[key] = nil
				}
				if index < len(lines) && lines[index].indent > indent {
					continuation, next, err := parseYAMLBlock(lines, index, lines[index].indent)
					if err != nil {
						return nil, index, err
					}
					object, ok := continuation.(map[string]any)
					if !ok {
						return nil, index, fmt.Errorf("YAML inválido: esperado objeto")
					}
					for childKey, child := range object {
						if _, exists := item[childKey]; exists {
							return nil, index, fmt.Errorf("YAML contém chave duplicada: %s", childKey)
						}
						item[childKey] = child
					}
					index = next
				}
				values = append(values, item)
			} else {
				value, err := yamlScalar(remainder)
				if err != nil {
					return nil, index, err
				}
				values = append(values, value)
			}
		}
		return values, index, nil
	}
	result := map[string]any{}
	for index < len(lines) && lines[index].indent == indent {
		line := lines[index]
		if strings.HasPrefix(line.text, "-") {
			break
		}
		key, rawValue, ok := splitYAMLMapping(line.text)
		if !ok || !regexp.MustCompile(`^[A-Za-z_][A-Za-z0-9_-]*$`).MatchString(key) {
			return nil, index, fmt.Errorf("YAML inválido na linha %d: chave inválida", line.number)
		}
		if _, exists := result[key]; exists {
			return nil, index, fmt.Errorf("YAML contém chave duplicada: %s", key)
		}
		index++
		if rawValue != "" {
			value, err := yamlScalar(rawValue)
			if err != nil {
				return nil, index, err
			}
			result[key] = value
		} else if index < len(lines) && lines[index].indent > indent {
			value, next, err := parseYAMLBlock(lines, index, lines[index].indent)
			if err != nil {
				return nil, index, err
			}
			result[key], index = value, next
		} else {
			result[key] = nil
		}
	}
	return result, index, nil
}

func splitYAMLMapping(value string) (string, string, bool) {
	index := strings.Index(value, ":")
	if index < 0 {
		return "", "", false
	}
	return strings.TrimSpace(value[:index]), strings.TrimSpace(value[index+1:]), true
}

func yamlScalar(raw string) (any, error) {
	value := strings.TrimSpace(raw)
	lower := strings.ToLower(value)
	switch lower {
	case "null", "~":
		return nil, nil
	case "true", "yes":
		return true, nil
	case "false", "no":
		return false, nil
	}
	if value == "[]" {
		return []any{}, nil
	}
	if value == "{}" {
		return map[string]any{}, nil
	}
	if strings.HasPrefix(value, "[") && strings.HasSuffix(value, "]") {
		body := strings.TrimSpace(value[1 : len(value)-1])
		if body == "" {
			return []any{}, nil
		}
		parts, err := splitYAMLFlowList(body)
		if err != nil {
			return nil, err
		}
		result := make([]any, 0, len(parts))
		for _, part := range parts {
			item, err := yamlScalar(part)
			if err != nil {
				return nil, err
			}
			result = append(result, item)
		}
		return result, nil
	}
	if strings.HasPrefix(value, `"`) && strings.HasSuffix(value, `"`) {
		return strconv.Unquote(value)
	}
	if strings.HasPrefix(value, "'") && strings.HasSuffix(value, "'") {
		return strings.ReplaceAll(value[1:len(value)-1], "''", "'"), nil
	}
	if integer, err := strconv.Atoi(value); err == nil {
		return integer, nil
	}
	if number, err := strconv.ParseFloat(value, 64); err == nil && strings.Contains(value, ".") {
		return number, nil
	}
	return value, nil
}

func splitYAMLFlowList(value string) ([]string, error) {
	parts, current := []string{}, strings.Builder{}
	var quote rune
	for _, character := range value {
		if character == '\'' || character == '"' {
			if quote == character {
				quote = 0
			} else if quote == 0 {
				quote = character
			}
		}
		if character == ',' && quote == 0 {
			part := strings.TrimSpace(current.String())
			if part == "" {
				return nil, fmt.Errorf("lista YAML contém item vazio")
			}
			parts = append(parts, part)
			current.Reset()
		} else {
			current.WriteRune(character)
		}
	}
	last := strings.TrimSpace(current.String())
	if last == "" {
		return nil, fmt.Errorf("lista YAML contém item vazio")
	}
	return append(parts, last), nil
}

func canonicalJSON(value any) ([]byte, error) {
	var buffer bytes.Buffer
	encoder := json.NewEncoder(&buffer)
	encoder.SetEscapeHTML(false)
	if err := encoder.Encode(value); err != nil {
		return nil, err
	}
	return bytes.TrimSuffix(buffer.Bytes(), []byte("\n")), nil
}

func mapsEqual(left, right map[string]any) bool {
	leftJSON, _ := canonicalJSON(left)
	rightJSON, _ := canonicalJSON(right)
	return bytes.Equal(leftJSON, rightJSON)
}

func cloneMap(value map[string]any) map[string]any {
	if value == nil {
		return map[string]any{}
	}
	encoded, _ := json.Marshal(value)
	result, _ := decodeJSONObject(encoded)
	return result
}

func mergeMaps(left, right map[string]any) map[string]any {
	result := cloneMap(left)
	for key, value := range right {
		result[key] = value
	}
	return result
}

func sequenceValue(raw any, label string) ([]any, error) {
	if raw == nil {
		return []any{}, nil
	}
	values, ok := raw.([]any)
	if !ok {
		return nil, fmt.Errorf("%s exige lista", label)
	}
	return values, nil
}

func stringValues(raw any, label string) ([]string, error) {
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
	for _, rawValue := range values {
		value, ok := rawValue.(string)
		value = strings.TrimSpace(value)
		if !ok || value == "" {
			return nil, fmt.Errorf("%s exige lista de strings", label)
		}
		if !seen[value] {
			result = append(result, value)
			seen[value] = true
		}
	}
	return result, nil
}

func containsString(values []string, target string) bool {
	for _, value := range values {
		if value == target {
			return true
		}
	}
	return false
}

func sortedMapKeys(value map[string]any) []string {
	keys := make([]string, 0, len(value))
	for key := range value {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	return keys
}
