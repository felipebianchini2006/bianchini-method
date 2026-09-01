package gokernel

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"unicode/utf8"
)

var (
	requirementHeading = regexp.MustCompile(`(?m)^(#{2,6})[ \t]+\[?([A-Z][A-Z0-9_-]*-[0-9]{3,})\]?(?:[ \t]*[:—-][ \t]*|[ \t]+)([^\n]+)$`)
	markdownHeading    = regexp.MustCompile(`(?m)^(#{1,6})[ \t]+[^\n]+$`)
	trailingWhitespace = regexp.MustCompile(`(?m)[ \t]+$`)
)

type requirementSection struct {
	ID      string
	Content string
}

func runSpecDiff(args []string) (any, error) {
	valueFlags := map[string]bool{"--root": true, "--base": true, "--target": true, "--output": true}
	flags, err := parseFlags(args, valueFlags, map[string]bool{})
	if err != nil {
		return nil, err
	}
	for _, required := range []string{"--root", "--base", "--target", "--output"} {
		if lastValue(flags, required) == "" {
			return nil, argparseError("the following arguments are required: " + required)
		}
	}
	result, err := createSpecDiff(lastValue(flags, "--root"), lastValue(flags, "--base"), lastValue(flags, "--target"), lastValue(flags, "--output"))
	if err != nil {
		// O CLI Python transforma falhas internas de spec-diff em erro público
		// de entrada (exit 2), preservando o código de domínio no stderr.
		return nil, fmt.Errorf("%s", err)
	}
	return result, nil
}

func createSpecDiff(rootValue, baseValue, targetValue, outputValue string) (map[string]any, error) {
	root, err := safeRoot(rootValue)
	if err != nil {
		return nil, err
	}
	baseCandidate, err := specConfined(root, baseValue, "spec base")
	if err != nil {
		return nil, err
	}
	targetCandidate, err := specConfined(root, targetValue, "spec target")
	if err != nil {
		return nil, err
	}
	baseInfo, baseErr := os.Lstat(baseCandidate)
	targetInfo, targetErr := os.Lstat(targetCandidate)
	if baseErr == nil && targetErr == nil && (baseInfo.IsDir() || targetInfo.IsDir()) {
		if !baseInfo.IsDir() || !targetInfo.IsDir() {
			return nil, fmt.Errorf("spec diff exige base e target do mesmo tipo")
		}
		output, pathErr := specConfined(root, outputValue, "spec diff output")
		if pathErr != nil {
			return nil, pathErr
		}
		for _, directory := range []string{baseCandidate, targetCandidate} {
			relative, relErr := filepath.Rel(directory, output)
			if relErr == nil && relative != ".." && !strings.HasPrefix(relative, ".."+string(filepath.Separator)) && !filepath.IsAbs(relative) {
				label := "base"
				if directory == targetCandidate {
					label = "target"
				}
				return nil, fmt.Errorf("spec diff output não pode ficar dentro da %s", label)
			}
		}
		manifest := filepath.Join(filepath.Dir(targetCandidate), "MANIFEST.json")
		metadata, rendered, deriveErr := deriveManagedSpecDiff(root, baseCandidate, targetCandidate, manifest)
		if deriveErr != nil {
			return nil, deriveErr
		}
		if err := atomicWrite(output, rendered); err != nil {
			return nil, domainError("SPEC_DIFF_ERROR", "falha ao gravar output")
		}
		outputRelative, _ := filepath.Rel(root, output)
		result := cloneMap(metadata)
		result["output"] = filepath.ToSlash(outputRelative)
		result["output_digest"] = sha256Bytes(rendered)
		return result, nil
	}
	base, err := confinedPath(root, baseValue, "spec base", true)
	if err != nil {
		return nil, err
	}
	target, err := confinedPath(root, targetValue, "spec target", true)
	if err != nil {
		return nil, err
	}
	output, err := confinedPath(root, outputValue, "spec diff output", false)
	if err != nil {
		return nil, err
	}
	if output == base || output == target {
		return nil, domainError("PATH_SAFETY", "spec diff output deve ser diferente da base e do target")
	}
	baseData, err := readTextFile(base, "spec base")
	if err != nil {
		return nil, err
	}
	targetData, err := readTextFile(target, "spec target")
	if err != nil {
		return nil, err
	}
	current, err := parseRequirements(base, baseData)
	if err != nil {
		return nil, err
	}
	future, err := parseRequirements(target, targetData)
	if err != nil {
		return nil, err
	}

	added := make([]string, 0)
	removed := make([]string, 0)
	modified := make([]string, 0)
	for identifier := range future {
		if previous, ok := current[identifier]; !ok {
			added = append(added, identifier)
		} else if previous != future[identifier] {
			modified = append(modified, identifier)
		}
	}
	for identifier := range current {
		if _, ok := future[identifier]; !ok {
			removed = append(removed, identifier)
		}
	}
	sort.Strings(added)
	sort.Strings(modified)
	sort.Strings(removed)
	baseRelative, _ := filepath.Rel(root, base)
	targetRelative, _ := filepath.Rel(root, target)
	outputRelative, _ := filepath.Rel(root, output)
	metadata := map[string]any{
		"added":          added,
		"base":           filepath.ToSlash(baseRelative),
		"base_digest":    sha256Bytes(baseData),
		"modified":       modified,
		"removed":        removed,
		"schema_version": 1,
		"target":         filepath.ToSlash(targetRelative),
		"target_digest":  sha256Bytes(targetData),
	}
	rendered, err := renderSpecDiff(metadata, added, modified, removed, current, future)
	if err != nil {
		return nil, err
	}
	if err := atomicWrite(output, rendered); err != nil {
		return nil, domainError("SPEC_DIFF_ERROR", "falha ao gravar output")
	}
	result := make(map[string]any, len(metadata)+2)
	for key, value := range metadata {
		result[key] = value
	}
	result["output"] = filepath.ToSlash(outputRelative)
	result["output_digest"] = sha256Bytes(rendered)
	return result, nil
}

func readTextFile(path, label string) ([]byte, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, domainError("SPEC_DIFF_ERROR", label+" ausente")
	}
	if len(data) == 0 {
		return nil, domainError("SPEC_DIFF_ERROR", label+" vazio")
	}
	if !utf8.Valid(data) || strings.IndexByte(string(data), 0) >= 0 {
		return nil, domainError("SPEC_DIFF_ERROR", label+" deve ser UTF-8 textual")
	}
	return data, nil
}

func parseRequirements(path string, data []byte) (map[string]string, error) {
	content := string(data)
	requirements := requirementHeading.FindAllStringSubmatchIndex(content, -1)
	if len(requirements) == 0 {
		return nil, domainError("SPEC_DIFF_ERROR", fmt.Sprintf("spec %s não contém requisitos com ID estável em heading, como ## AUTH-001: Título", path))
	}
	headings := markdownHeading.FindAllStringIndex(content, -1)
	headingPositions := make(map[int]int, len(headings))
	for index, heading := range headings {
		headingPositions[heading[0]] = index
	}
	parsed := make(map[string]string, len(requirements))
	for _, match := range requirements {
		identifier := content[match[4]:match[5]]
		if _, exists := parsed[identifier]; exists {
			return nil, domainError("SPEC_DIFF_ERROR", fmt.Sprintf("spec %s contém ID duplicado: %s", path, identifier))
		}
		level := match[3] - match[2]
		end := len(content)
		headingIndex, ok := headingPositions[match[0]]
		if !ok {
			return nil, domainError("SPEC_DIFF_ERROR", "heading inconsistente")
		}
		for _, following := range headings[headingIndex+1:] {
			line := content[following[0]:following[1]]
			followingLevel := strings.IndexByte(line, ' ')
			if followingLevel == -1 {
				followingLevel = strings.IndexByte(line, '\t')
			}
			if followingLevel <= level {
				end = following[0]
				break
			}
		}
		section := strings.TrimSpace(content[match[0]:end])
		parsed[identifier] = trailingWhitespace.ReplaceAllString(section, "")
	}
	return parsed, nil
}

func renderSpecDiff(metadata map[string]any, added, modified, removed []string, current, future map[string]string) ([]byte, error) {
	jsonData, err := json.MarshalIndent(metadata, "", "  ")
	if err != nil {
		return nil, domainError("SPEC_DIFF_ERROR", "falha ao renderizar metadata")
	}
	lines := []string{
		"# Spec Diff", "",
		"Esta é uma projeção derivada. A spec target completa permanece a fonte de verdade.",
		"", "```json", string(jsonData), "```",
	}
	sections := []struct {
		title       string
		identifiers []string
		source      map[string]string
	}{
		{"ADDED", added, future},
		{"MODIFIED", modified, future},
		{"REMOVED", removed, current},
	}
	for _, section := range sections {
		lines = append(lines, "", "## "+section.title, "")
		if len(section.identifiers) == 0 {
			lines = append(lines, "Nenhum.")
		}
		for _, identifier := range section.identifiers {
			lines = append(lines, "### "+identifier, "", section.source[identifier], "")
		}
	}
	return []byte(strings.TrimRight(strings.Join(lines, "\n"), " \t\r\n") + "\n"), nil
}

func sha256Bytes(data []byte) string {
	sum := sha256.Sum256(data)
	return hex.EncodeToString(sum[:])
}

func atomicWrite(path string, data []byte) error {
	mode := os.FileMode(0o644)
	existing := false
	if info, err := os.Lstat(path); err == nil {
		if !info.Mode().IsRegular() || info.Mode()&os.ModeSymlink != 0 {
			return fmt.Errorf("output inseguro")
		}
		mode = info.Mode().Perm()
		existing = true
	} else if !os.IsNotExist(err) {
		return err
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
	temporary, err := os.CreateTemp(filepath.Dir(path), ".bm-spec-diff-*")
	if err != nil {
		return err
	}
	temporaryPath := temporary.Name()
	defer os.Remove(temporaryPath)
	if existing {
		if err := temporary.Chmod(mode); err != nil {
			temporary.Close()
			return err
		}
	} else {
		if err := temporary.Close(); err != nil {
			return err
		}
		if err := os.Remove(temporaryPath); err != nil {
			return err
		}
		temporary, err = os.OpenFile(
			temporaryPath, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0o666,
		)
		if err != nil {
			return err
		}
	}
	if _, err := temporary.Write(data); err != nil {
		temporary.Close()
		return err
	}
	if err := temporary.Sync(); err != nil {
		temporary.Close()
		return err
	}
	if err := temporary.Close(); err != nil {
		return err
	}
	return durableRename(temporaryPath, path)
}
