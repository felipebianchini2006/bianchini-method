package gokernel

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"unicode/utf8"
)

func designJSONBytes(value any, indent bool) ([]byte, error) {
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

func designCompactJSON(value any) ([]byte, error) {
	encoded, err := designJSONBytes(value, false)
	if err != nil {
		return nil, err
	}
	return bytes.TrimSuffix(encoded, []byte("\n")), nil
}

func designFileDigest(path string) (string, error) {
	content, err := os.ReadFile(path)
	if err != nil {
		return "", err
	}
	return sha256Bytes(content), nil
}

func readDesignJSON(path, label string) (map[string]any, error) {
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

func designRelativePath(root, path string) (string, error) {
	relative, err := filepath.Rel(root, path)
	if err != nil || relative == ".." || strings.HasPrefix(relative, ".."+string(filepath.Separator)) {
		return "", fmt.Errorf("arquivo fora da raiz: %s", path)
	}
	return filepath.ToSlash(relative), nil
}

func buildDesignManifest(root string, files []string) ([]byte, error) {
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
		digest, err := designFileDigest(target)
		if err != nil {
			return nil, err
		}
		fmt.Fprintf(&result, "%s  %s\n", digest, relative)
	}
	return []byte(result.String()), nil
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
	return designAudit(lastValue(flags, "--root"), lastValue(flags, "--scope"), lastValue(flags, "--manifest"), action == "seal")
}

func designAudit(rootValue, scopeValue, manifestValue string, seal bool) (map[string]any, error) {
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
	manifest, err := readDesignJSON(manifestPath, "manifesto de design")
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
	scopeRelative, _ := designRelativePath(root, scope)
	manifestRelative, _ := designRelativePath(root, manifestPath)
	scopeDigest, _ := designFileDigest(scope)
	digestManifest := make(map[string]any, len(manifest))
	for key, value := range manifest {
		if key != "status" && key != "scope_digest" && key != "design_digest" {
			digestManifest[key] = value
		}
	}
	digestManifest["scope_source"] = scopeRelative
	metadata, err := designCompactJSON(digestManifest)
	if err != nil {
		return nil, err
	}
	fileManifest, err := buildDesignManifest(root, files)
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
		encoded, _ := designJSONBytes(manifest, true)
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
