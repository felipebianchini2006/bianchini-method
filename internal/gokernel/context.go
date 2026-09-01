package gokernel

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"unicode/utf8"
)

const (
	contextDefaultMaxBytes = 16_384
	contextSchemaVersion   = 1
	contextContract        = "0.4"
)

var (
	contextChangeUnit = regexp.MustCompile(`^(C[0-9]{3})/(P[0-9]{2})(?:/(T[0-9]{2}))?$`)
	contextQuickUnit  = regexp.MustCompile(`^Q[0-9]{3}$`)
	contextDebugUnit  = regexp.MustCompile(`^D[0-9]{3}$`)
	contextRCUnit     = regexp.MustCompile(`^RC:([A-Za-z0-9][A-Za-z0-9._:-]{0,127})$`)
)

type contextSourceReader struct {
	root    string
	digests map[string]string
}

func runContext(args []string) (any, error) {
	if len(args) == 0 {
		return nil, argparseError("the following arguments are required: action")
	}
	action := args[0]
	if action != "pack" && action != "verify" {
		return nil, argparseError(fmt.Sprintf("argument action: invalid choice: '%s'", action))
	}
	flags, err := parseFlags(args[1:], map[string]bool{
		"--repo": true, "--unit": true, "--output": true, "--max-bytes": true, "--path": true,
	}, map[string]bool{})
	if err != nil {
		return nil, err
	}
	repo := lastValue(flags, "--repo")
	if action == "pack" {
		unit := lastValue(flags, "--unit")
		if unit == "" {
			return nil, userError("context pack exige --unit")
		}
		limit := contextDefaultMaxBytes
		if raw := lastValue(flags, "--max-bytes"); raw != "" {
			parsed, parseErr := strconv.Atoi(raw)
			if parseErr != nil {
				return nil, argparseError(fmt.Sprintf("argument --max-bytes: invalid int value: '%s'", raw))
			}
			limit = parsed
		}
		return compileContextPack(repo, unit, lastValue(flags, "--output"), limit)
	}
	path := lastValue(flags, "--path")
	if path == "" {
		return nil, userError("context verify exige --path")
	}
	return verifyContextPack(repo, path)
}

func contextError(code, message string) error {
	return domainError(code, message)
}

func contextErrorDetails(code, message string, details map[string]any) error {
	encoded, _ := contextCanonical(details)
	return contextError(code, message+" "+strings.TrimSuffix(string(encoded), "\n"))
}

func (reader *contextSourceReader) bytes(path, label string) ([]byte, error) {
	safe, err := contextExistingFile(reader.root, path, label)
	if err != nil {
		return nil, err
	}
	content, err := os.ReadFile(safe)
	if err != nil {
		return nil, contextError("PACK_INCOMPLETE", fmt.Sprintf("não foi possível ler %s: %v", label, err))
	}
	relative, _ := filepath.Rel(reader.root, safe)
	reader.digests[filepath.ToSlash(relative)] = sha256Bytes(content)
	return content, nil
}

func (reader *contextSourceReader) text(path, label string) (string, error) {
	content, err := reader.bytes(path, label)
	if err != nil {
		return "", err
	}
	if !utf8.Valid(content) {
		return "", contextError("PACK_INCOMPLETE", label+" não é UTF-8")
	}
	return string(content), nil
}

func (reader *contextSourceReader) frontmatter(path, label string) (map[string]any, error) {
	content, err := reader.text(path, label)
	if err != nil {
		return nil, err
	}
	match := frontmatterPattern.FindStringSubmatch(content)
	if match == nil {
		return nil, contextError("PACK_INCOMPLETE", label+" exige frontmatter JSON")
	}
	value, decodeErr := contextDecodeJSON([]byte(match[1]))
	if decodeErr != nil {
		return nil, contextError("PACK_INCOMPLETE", label+" possui JSON inválido")
	}
	object, ok := value.(map[string]any)
	if !ok {
		return nil, contextError("PACK_INCOMPLETE", label+" exige objeto")
	}
	return object, nil
}

func (reader *contextSourceReader) jsonObject(path, label string) (map[string]any, error) {
	content, err := reader.text(path, label)
	if err != nil {
		return nil, err
	}
	value, decodeErr := contextDecodeJSON([]byte(content))
	if decodeErr != nil {
		return nil, contextError("PACK_INCOMPLETE", label+" possui JSON inválido")
	}
	object, ok := value.(map[string]any)
	if !ok {
		return nil, contextError("PACK_INCOMPLETE", label+" exige objeto")
	}
	return object, nil
}

func contextDecodeJSON(content []byte) (any, error) {
	decoder := json.NewDecoder(bytes.NewReader(content))
	decoder.UseNumber()
	var value any
	if err := decoder.Decode(&value); err != nil {
		return nil, err
	}
	var trailing any
	if err := decoder.Decode(&trailing); err != io.EOF {
		if err == nil {
			return nil, fmt.Errorf("JSON contém valores adicionais")
		}
		return nil, err
	}
	return contextNormalizeNumbers(value), nil
}

func contextNormalizeNumbers(value any) any {
	switch typed := value.(type) {
	case json.Number:
		if integer, err := typed.Int64(); err == nil {
			return integer
		}
		if floating, err := typed.Float64(); err == nil {
			return floating
		}
		return typed.String()
	case map[string]any:
		for key, item := range typed {
			typed[key] = contextNormalizeNumbers(item)
		}
		return typed
	case []any:
		for index, item := range typed {
			typed[index] = contextNormalizeNumbers(item)
		}
		return typed
	default:
		return value
	}
}

func contextCanonical(value any) ([]byte, error) {
	var buffer bytes.Buffer
	encoder := json.NewEncoder(&buffer)
	encoder.SetEscapeHTML(false)
	if err := encoder.Encode(value); err != nil {
		return nil, err
	}
	content := bytes.ReplaceAll(buffer.Bytes(), []byte(`\u2028`), []byte("\u2028"))
	content = bytes.ReplaceAll(content, []byte(`\u2029`), []byte("\u2029"))
	return content, nil
}

func contextGitHead(root string) string {
	command := exec.Command("git", "rev-parse", "--verify", "HEAD")
	command.Dir = root
	output, err := command.Output()
	if err != nil {
		return "UNBORN"
	}
	return strings.TrimSpace(string(output))
}

func contextValidUnit(unit string) bool {
	return contextChangeUnit.MatchString(unit) || contextQuickUnit.MatchString(unit) || contextDebugUnit.MatchString(unit) || contextRCUnit.MatchString(unit)
}

func assembleContextPayload(root, unit string) (map[string]any, error) {
	if !contextValidUnit(unit) {
		return nil, contextError("PACK_INCOMPLETE", "identidade de unidade inválida: "+unit)
	}
	reader := &contextSourceReader{root: root, digests: map[string]string{}}
	state, err := reader.frontmatter(filepath.Join(root, ".bianchini", "STATE.md"), "STATE.md")
	if err != nil {
		return nil, err
	}
	required := map[string]bool{"state:.bianchini/STATE.md": true}
	var context map[string]any
	if match := contextChangeUnit.FindStringSubmatch(unit); match != nil {
		context, err = contextChangePayload(root, reader, state, match[1], match[2], match[3], required)
	} else if contextQuickUnit.MatchString(unit) {
		context, err = contextQuickPayload(root, reader, state, unit, required)
	} else if contextDebugUnit.MatchString(unit) {
		context, err = contextDebugPayload(root, reader, state, unit, required)
	} else {
		context, err = contextRCPayload(root, reader, state, contextRCUnit.FindStringSubmatch(unit)[1], required)
	}
	if err != nil {
		return nil, err
	}
	lessons, err := contextApprovedLessons(root, reader, unit, context, required)
	if err != nil {
		return nil, err
	}
	context["approved_lessons"] = lessons
	head := contextGitHead(root)
	sourceDigests := make(map[string]any, len(reader.digests))
	sources := make([]string, 0, len(reader.digests))
	for relative, digest := range reader.digests {
		sourceDigests[relative] = digest
		sources = append(sources, relative)
	}
	sort.Strings(sources)
	requiredRefs := contextSortedKeys(required)
	cacheMaterial := map[string]any{"unit": unit, "head": head, "source_digests": sourceDigests}
	cacheBytes, _ := contextCanonical(cacheMaterial)
	return map[string]any{
		"schema_version": contextSchemaVersion,
		"contract":       contextContract,
		"unit":           unit,
		"head":           head,
		"cache_key":      sha256Bytes(cacheBytes),
		"source_digests": sourceDigests,
		"sources":        sources,
		"required_refs":  requiredRefs,
		"context":        context,
	}, nil
}

func compileContextPack(repo, unit, output string, maxBytes int) (map[string]any, error) {
	root, err := contextRoot(repo)
	if err != nil {
		return nil, err
	}
	if maxBytes <= 0 {
		return nil, contextError("PACK_INCOMPLETE", "max_bytes exige inteiro positivo")
	}
	payload, err := assembleContextPayload(root, unit)
	if err != nil {
		return nil, err
	}
	content, err := contextCanonical(payload)
	if err != nil {
		return nil, contextError("PACK_INCOMPLETE", "pack não pode ser serializado")
	}
	if len(content) > maxBytes {
		contextValue := stateObject(payload["context"])
		consumers := make([]map[string]any, 0, len(contextValue))
		for name, value := range contextValue {
			encoded, _ := contextCanonical(map[string]any{"value": value})
			consumers = append(consumers, map[string]any{"name": name, "bytes": len(encoded)})
		}
		sort.Slice(consumers, func(i, j int) bool {
			left, right := consumers[i]["bytes"].(int), consumers[j]["bytes"].(int)
			if left != right {
				return left > right
			}
			return stateString(consumers[i]["name"]) < stateString(consumers[j]["name"])
		})
		if len(consumers) > 5 {
			consumers = consumers[:5]
		}
		return nil, contextErrorDetails("PACK_TOO_LARGE", fmt.Sprintf("pack possui %d bytes; limite %d", len(content), maxBytes), map[string]any{"largest_consumers": consumers})
	}
	if output == "" {
		safeUnit := strings.Trim(regexp.MustCompile(`[^A-Za-z0-9._-]+`).ReplaceAllString(unit, "-"), "-")
		output = filepath.Join(root, ".bianchini", ".runtime", "context", safeUnit+".json")
	}
	target, err := contextSafeOutput(root, output)
	if err != nil {
		return nil, err
	}
	if err := os.MkdirAll(filepath.Dir(target), 0o755); err != nil {
		return nil, contextError("PATH_UNSAFE", "output não pode ser criado")
	}
	target, err = contextSafeOutput(root, target)
	if err != nil {
		return nil, err
	}
	if existing, readErr := os.ReadFile(target); readErr == nil && bytes.Equal(existing, content) {
		return contextPackResult(root, target, content, payload, true), nil
	}
	if err := contextAtomicWrite(target, content); err != nil {
		return nil, contextError("PATH_UNSAFE", "output não pode ser escrito: "+err.Error())
	}
	return contextPackResult(root, target, content, payload, false), nil
}

func verifyContextPack(repo, packPath string) (map[string]any, error) {
	root, err := contextRoot(repo)
	if err != nil {
		return nil, err
	}
	target, err := contextExistingFile(root, packPath, "pack")
	if err != nil {
		return nil, err
	}
	content, err := os.ReadFile(target)
	if err != nil {
		return nil, contextError("STALE_EVIDENCE", "pack ilegível")
	}
	decoded, decodeErr := contextDecodeJSON(content)
	if decodeErr != nil {
		return nil, contextError("STALE_EVIDENCE", "pack possui JSON inválido")
	}
	payload, ok := decoded.(map[string]any)
	if !ok {
		return nil, contextError("STALE_EVIDENCE", "pack possui schema_version inválido")
	}
	if !contextExactInt(payload["schema_version"], 1) {
		return nil, contextError("STALE_EVIDENCE", "pack possui schema_version inválido")
	}
	if stateString(payload["contract"]) != contextContract {
		return nil, contextError("STALE_EVIDENCE", "pack possui contrato inválido")
	}
	canonical, canonicalErr := contextCanonical(payload)
	if canonicalErr != nil || !bytes.Equal(canonical, content) {
		return nil, contextError("STALE_EVIDENCE", "pack não está em forma canônica")
	}
	unit, ok := payload["unit"].(string)
	if !ok || !contextValidUnit(unit) {
		return nil, contextError("STALE_EVIDENCE", "identidade do pack inválida")
	}
	if stateString(payload["head"]) != contextGitHead(root) {
		return nil, contextError("STALE_EVIDENCE", "HEAD mudou depois da montagem do pack")
	}
	digests, ok := payload["source_digests"].(map[string]any)
	if !ok {
		return nil, contextError("STALE_EVIDENCE", "índice de fontes do pack é inválido")
	}
	sourceValues, ok := payload["sources"].([]any)
	sources := make([]string, 0, len(sourceValues))
	if ok {
		for _, value := range sourceValues {
			text, isString := value.(string)
			if !isString {
				ok = false
				break
			}
			sources = append(sources, text)
		}
	}
	if !ok || !reflectStringSlices(sources, contextSortedMapKeys(digests)) {
		return nil, contextError("STALE_EVIDENCE", "índice de fontes do pack é inválido")
	}
	for relative, expectedValue := range digests {
		expected, valid := expectedValue.(string)
		if !valid {
			return nil, contextError("STALE_EVIDENCE", "digest de fonte inválido")
		}
		source, safeErr := contextExistingFile(root, relative, "fonte "+relative)
		if safeErr != nil {
			return nil, contextError("STALE_EVIDENCE", "fonte inválida ou ausente: "+relative)
		}
		current, readErr := os.ReadFile(source)
		if readErr != nil || sha256Bytes(current) != expected {
			return nil, contextError("STALE_EVIDENCE", "fonte mudou: "+relative)
		}
	}
	material := map[string]any{"unit": unit, "head": payload["head"], "source_digests": digests}
	materialBytes, _ := contextCanonical(material)
	if stateString(payload["cache_key"]) != sha256Bytes(materialBytes) {
		return nil, contextError("STALE_EVIDENCE", "cache key do pack diverge")
	}
	expected, err := assembleContextPayload(root, unit)
	if err != nil {
		code := strings.SplitN(err.Error(), ":", 2)[0]
		return nil, contextError("STALE_EVIDENCE", "pack não pode ser recompilado: "+code)
	}
	expectedBytes, _ := contextCanonical(expected)
	if !bytes.Equal(expectedBytes, content) {
		return nil, contextError("STALE_EVIDENCE", "conteúdo derivado do pack diverge das fontes")
	}
	return contextPackResult(root, target, content, payload, true), nil
}

func contextPackResult(root, target string, content []byte, payload map[string]any, cacheHit bool) map[string]any {
	relative, _ := filepath.Rel(root, target)
	return map[string]any{
		"path":           filepath.ToSlash(relative),
		"digest":         sha256Bytes(content),
		"bytes":          len(content),
		"unit":           payload["unit"],
		"source_digests": payload["source_digests"],
		"sources":        payload["sources"],
		"required_refs":  payload["required_refs"],
		"cache_hit":      cacheHit,
	}
}

func contextAtomicWrite(path string, content []byte) error {
	temporary, err := os.CreateTemp(filepath.Dir(path), "."+filepath.Base(path)+".*.tmp")
	if err != nil {
		return err
	}
	temporaryPath := temporary.Name()
	defer os.Remove(temporaryPath)
	if _, err := temporary.Write(content); err != nil {
		_ = temporary.Close()
		return err
	}
	if err := temporary.Sync(); err != nil {
		_ = temporary.Close()
		return err
	}
	if err := temporary.Close(); err != nil {
		return err
	}
	return durableRename(temporaryPath, path)
}

func contextSortedKeys(values map[string]bool) []string {
	result := make([]string, 0, len(values))
	for value := range values {
		result = append(result, value)
	}
	sort.Strings(result)
	return result
}

func contextSortedMapKeys(values map[string]any) []string {
	result := make([]string, 0, len(values))
	for value := range values {
		result = append(result, value)
	}
	sort.Strings(result)
	return result
}

func reflectStringSlices(left, right []string) bool {
	if len(left) != len(right) {
		return false
	}
	for index := range left {
		if left[index] != right[index] {
			return false
		}
	}
	return true
}

func contextExactInt(value any, expected int64) bool {
	switch typed := value.(type) {
	case int:
		return int64(typed) == expected
	case int64:
		return typed == expected
	case float64:
		return typed == float64(expected)
	default:
		return false
	}
}
