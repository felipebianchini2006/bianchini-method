package gokernel

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"unicode"

	"golang.org/x/text/unicode/norm"
)

var (
	managedSpecID       = regexp.MustCompile(`^[a-z][a-z0-9_-]{0,63}$`)
	managedRequirement  = regexp.MustCompile(`^[A-Z][A-Z0-9_-]*-[0-9]{3,}$`)
	managedScopeHeading = regexp.MustCompile(`(?m)^### ([A-Z]+-[0-9]{3})\b`)
)

var traceableScopePrefixes = map[string]bool{
	"FLW": true, "REQ": true, "NFR": true, "BR": true, "DAT": true,
	"INT": true, "ERR": true, "RSK": true,
}

var mandatorySpecPrefixes = map[string]bool{
	"FLW": true, "REQ": true, "NFR": true, "BR": true,
	"DAT": true, "INT": true, "ERR": true,
}

type managedSpecTree struct {
	files        map[string][]byte
	requirements map[string]map[string]string
	digest       string
}

type managedRequirementEntry struct {
	id    string
	scope []string
}

type managedSpecEntry struct {
	id           string
	path         string
	requirements []managedRequirementEntry
}

type managedRiskEntry struct {
	scope  string
	kind   string
	target string
}

type managedManifest struct {
	specs         []managedSpecEntry
	riskCoverage  []managedRiskEntry
	digest        any
	schemaVersion int
	specContract  int
}

func specError(code, message string) error {
	return workflowError(code, message)
}

func validateManagedSpecPath(value, label string) (string, error) {
	if value == "" {
		return "", specError("SPEC_PATH_INVALID", label+" vazio")
	}
	if strings.Contains(value, "\\") {
		return "", specError("SPEC_PATH_INVALID", label+" contém barra invertida: "+value)
	}
	if filepath.IsAbs(value) {
		return "", specError("SPEC_PATH_INVALID", label+" absoluto: "+value)
	}
	if value != filepath.ToSlash(filepath.Clean(value)) || value == "." || value == ".." {
		return "", specError("SPEC_PATH_INVALID", label+" não está normalizado: "+value)
	}
	for _, part := range strings.Split(value, "/") {
		if part == "" || part == "." || part == ".." {
			return "", specError("SPEC_PATH_INVALID", label+" contém traversal: "+value)
		}
		if strings.EqualFold(part, ".planning") {
			return "", specError("SPEC_PATH_INVALID", label+" usa namespace estrangeiro: "+value)
		}
	}
	if filepath.Ext(value) != ".md" {
		return "", specError("SPEC_PATH_INVALID", label+" deve terminar em .md: "+value)
	}
	if norm.NFC.String(value) != value {
		return "", specError("SPEC_PATH_INVALID", label+" não está em NFC: "+value)
	}
	return value, nil
}

func specConfined(root, candidate, label string) (string, error) {
	if strings.Contains(candidate, "\\") {
		return "", specError("SPEC_PATH_INVALID", label+" contém traversal")
	}
	for _, part := range strings.Split(filepath.ToSlash(candidate), "/") {
		if strings.EqualFold(part, ".planning") {
			return "", specError("SPEC_PATH_INVALID", label+" usa namespace estrangeiro")
		}
	}
	trusted, err := filepath.Abs(root)
	if err != nil {
		return "", specError("SPEC_PATH_INVALID", label+" fora da raiz confiável")
	}
	rootInfo, err := os.Lstat(trusted)
	if err != nil || rootInfo.Mode()&os.ModeSymlink != 0 || !rootInfo.IsDir() {
		return "", specError("SPEC_SYMLINK", "raiz confiável não pode ser symlink: "+trusted)
	}
	path := candidate
	if !filepath.IsAbs(path) {
		path = filepath.Join(trusted, path)
	}
	path, err = filepath.Abs(path)
	if err != nil {
		return "", specError("SPEC_PATH_INVALID", label+" fora da raiz confiável")
	}
	relative, err := filepath.Rel(trusted, path)
	if err != nil || relative == ".." || strings.HasPrefix(relative, ".."+string(filepath.Separator)) || filepath.IsAbs(relative) {
		return "", specError("SPEC_PATH_INVALID", label+" fora da raiz confiável")
	}
	cursor := trusted
	for _, part := range strings.Split(relative, string(filepath.Separator)) {
		if part == "." || part == "" {
			continue
		}
		cursor = filepath.Join(cursor, part)
		info, statErr := os.Lstat(cursor)
		if statErr == nil && info.Mode()&os.ModeSymlink != 0 {
			return "", specError("SPEC_SYMLINK", "symlink ancestral não permitido: "+cursor)
		}
		if statErr != nil && !os.IsNotExist(statErr) {
			return "", specError("SPEC_PATH_INVALID", label+" inválido")
		}
	}
	return filepath.Clean(path), nil
}

func inspectManagedSpecTree(root, directory string, required, allowRootManifest bool) (managedSpecTree, error) {
	directory, err := specConfined(root, directory, "árvore de specs")
	if err != nil {
		return managedSpecTree{}, err
	}
	info, err := os.Lstat(directory)
	if os.IsNotExist(err) {
		if required {
			return managedSpecTree{}, specError("SPEC_TARGET_MISSING", "target de specs ausente: "+directory)
		}
		emptyDigest, _ := canonicalJSON(map[string]any{})
		return managedSpecTree{files: map[string][]byte{}, requirements: map[string]map[string]string{}, digest: sha256Bytes(emptyDigest)}, nil
	}
	if err != nil || info.Mode()&os.ModeSymlink != 0 {
		return managedSpecTree{}, specError("SPEC_SYMLINK", "symlink não permitido: "+directory)
	}
	if !info.IsDir() {
		return managedSpecTree{}, specError("SPEC_TARGET_INVALID", "árvore de specs não é diretório: "+directory)
	}
	tree := managedSpecTree{files: map[string][]byte{}, requirements: map[string]map[string]string{}}
	err = filepath.WalkDir(directory, func(path string, entry fs.DirEntry, walkErr error) error {
		if walkErr != nil {
			return specError("SPEC_PATH_INVALID", "entrada de spec inválida: "+path)
		}
		if path == directory {
			return nil
		}
		relative, relErr := filepath.Rel(directory, path)
		if relErr != nil {
			return specError("SPEC_PATH_INVALID", "entrada de spec inválida: "+path)
		}
		relative = filepath.ToSlash(relative)
		if entry.Type()&os.ModeSymlink != 0 {
			return specError("SPEC_SYMLINK", "symlink não permitido: "+path)
		}
		if entry.IsDir() {
			for _, part := range strings.Split(relative, "/") {
				if strings.EqualFold(part, ".planning") {
					return specError("SPEC_PATH_INVALID", "path usa namespace estrangeiro: "+relative)
				}
			}
			return nil
		}
		if entry.Type()&fs.ModeType != 0 {
			return specError("SPEC_PATH_INVALID", "entrada de spec inválida: "+relative)
		}
		content, readErr := os.ReadFile(path)
		if readErr != nil {
			return specError("SPEC_PATH_INVALID", "entrada de spec inválida: "+relative)
		}
		if allowRootManifest && relative == "MANIFEST.json" {
			tree.files[relative] = content
			return nil
		}
		if _, pathErr := validateManagedSpecPath(relative, "spec path"); pathErr != nil {
			return pathErr
		}
		if !validUTF8Text(content) {
			return specError("SPEC_BINARY", "spec binário ou UTF-8 inválido: "+relative)
		}
		text := string(content)
		if strings.TrimSpace(text) == "" {
			return specError("SPEC_EMPTY", "spec vazio: "+relative)
		}
		for _, character := range text {
			if unicode.IsControl(character) && character != '\n' && character != '\r' && character != '\t' {
				return specError("SPEC_BINARY", "spec binário contém controle inválido: "+relative)
			}
		}
		requirements, parseErr := parseManagedRequirements(text, relative)
		if parseErr != nil {
			return parseErr
		}
		tree.files[relative] = content
		tree.requirements[relative] = requirements
		return nil
	})
	if err != nil {
		return managedSpecTree{}, err
	}
	paths := make([]string, 0, len(tree.requirements))
	for path := range tree.requirements {
		paths = append(paths, path)
	}
	if err := validateManagedPathCollisions(paths); err != nil {
		return managedSpecTree{}, err
	}
	if required && len(paths) == 0 {
		return managedSpecTree{}, specError("SPEC_TARGET_EMPTY", "target de specs não possui Markdown")
	}
	digestPayload := map[string]any{}
	for path, content := range tree.files {
		digestPayload[path] = sha256Bytes(content)
	}
	encoded, _ := canonicalJSON(digestPayload)
	tree.digest = sha256Bytes(encoded)
	return tree, nil
}

func parseManagedRequirements(content, path string) (map[string]string, error) {
	matches := requirementHeading.FindAllStringSubmatchIndex(content, -1)
	if len(matches) == 0 {
		return nil, specError("SPEC_REQUIREMENTS_MISSING", "spec "+path+" não contém requisito com ID estável em heading")
	}
	headings := markdownHeading.FindAllStringIndex(content, -1)
	positions := map[int]int{}
	for index, heading := range headings {
		positions[heading[0]] = index
	}
	result := map[string]string{}
	for _, match := range matches {
		identifier := content[match[4]:match[5]]
		if _, exists := result[identifier]; exists {
			return nil, specError("SPEC_REQUIREMENT_DUPLICATE", "ID duplicado em "+path+": "+identifier)
		}
		level := match[3] - match[2]
		end := len(content)
		for _, heading := range headings[positions[match[0]]+1:] {
			line := content[heading[0]:heading[1]]
			followingLevel := strings.IndexAny(line, " \t")
			if followingLevel <= level {
				end = heading[0]
				break
			}
		}
		result[identifier] = trailingWhitespace.ReplaceAllString(strings.TrimSpace(content[match[0]:end]), "")
	}
	return result, nil
}

func validateManagedPathCollisions(paths []string) error {
	seen := map[string]string{}
	for _, path := range paths {
		key := strings.ToLower(norm.NFC.String(path))
		if previous, exists := seen[key]; exists {
			return specError("SPEC_PATH_COLLISION", "colisão de path por normalização/case: "+previous+" e "+path)
		}
		seen[key] = path
	}
	return nil
}

func loadManagedManifest(root, path string) (managedManifest, error) {
	path, err := specConfined(root, path, "MANIFEST.json")
	if err != nil {
		return managedManifest{}, err
	}
	info, err := os.Lstat(path)
	if err != nil || info.Mode()&os.ModeSymlink != 0 || !info.Mode().IsRegular() {
		return managedManifest{}, specError("SPEC_MANIFEST_MISSING", "MANIFEST.json ausente: "+path)
	}
	content, err := os.ReadFile(path)
	if err != nil || !validUTF8Text(content) {
		return managedManifest{}, specError("SPEC_MANIFEST_INVALID", "MANIFEST.json inválido")
	}
	value, err := decodeJSONObject(content)
	if err != nil {
		return managedManifest{}, specError("SPEC_MANIFEST_INVALID", "MANIFEST.json inválido: "+err.Error())
	}
	allowed := stringSet([]string{"schema_version", "spec_contract", "specs", "risk_coverage"})
	if unknown := unknownMapKeys(value, allowed); len(unknown) > 0 {
		return managedManifest{}, specError("SPEC_MANIFEST_INVALID", "campos desconhecidos: "+strings.Join(unknown, ", "))
	}
	if missing := missingMapKeys(value, []string{"schema_version", "spec_contract", "specs", "risk_coverage"}); len(missing) > 0 {
		return managedManifest{}, specError("SPEC_MANIFEST_INVALID", "campos ausentes: "+strings.Join(missing, ", "))
	}
	if stateInt(value["schema_version"]) != 1 {
		return managedManifest{}, specError("SPEC_MANIFEST_INVALID", "schema_version deve ser 1")
	}
	if stateInt(value["spec_contract"]) != 1 {
		return managedManifest{}, specError("SPEC_CONTRACT_UNSUPPORTED", "spec_contract deve ser 1")
	}
	rawSpecs, ok := value["specs"].([]any)
	if !ok {
		return managedManifest{}, specError("SPEC_MANIFEST_INVALID", "specs deve ser lista")
	}
	rawRisks, ok := value["risk_coverage"].([]any)
	if !ok {
		return managedManifest{}, specError("SPEC_MANIFEST_INVALID", "risk_coverage deve ser lista")
	}
	manifest := managedManifest{schemaVersion: 1, specContract: 1, digest: sha256Bytes(content)}
	specIDs, requirementIDs := map[string]bool{}, map[string]bool{}
	paths := []string{}
	for index, raw := range rawSpecs {
		item, ok := raw.(map[string]any)
		if !ok || len(item) != 3 || !hasExactKeys(item, []string{"id", "path", "requirements"}) {
			return managedManifest{}, specError("SPEC_MANIFEST_INVALID", fmt.Sprintf("shape inválido em specs[%d]", index))
		}
		identifier := stateString(item["id"])
		if !managedSpecID.MatchString(identifier) {
			return managedManifest{}, specError("SPEC_MANIFEST_INVALID", "spec id inválido: "+identifier)
		}
		if specIDs[identifier] {
			return managedManifest{}, specError("SPEC_ID_DUPLICATE", "spec id duplicado: "+identifier)
		}
		specIDs[identifier] = true
		pathValue, pathErr := validateManagedSpecPath(stateString(item["path"]), fmt.Sprintf("specs[%d].path", index))
		if pathErr != nil {
			return managedManifest{}, pathErr
		}
		paths = append(paths, pathValue)
		rawRequirements, ok := item["requirements"].([]any)
		if !ok {
			return managedManifest{}, specError("SPEC_MANIFEST_INVALID", fmt.Sprintf("specs[%d].requirements deve ser lista", index))
		}
		spec := managedSpecEntry{id: identifier, path: pathValue}
		for requirementIndex, rawRequirement := range rawRequirements {
			requirement, ok := rawRequirement.(map[string]any)
			if !ok || len(requirement) != 2 || !hasExactKeys(requirement, []string{"id", "scope"}) {
				return managedManifest{}, specError("SPEC_MANIFEST_INVALID", "shape inválido em requirement")
			}
			requirementID := stateString(requirement["id"])
			if !managedRequirement.MatchString(requirementID) {
				return managedManifest{}, specError("SPEC_MANIFEST_INVALID", "requirement id inválido: "+requirementID)
			}
			if requirementIDs[requirementID] {
				return managedManifest{}, specError("SPEC_REQUIREMENT_DUPLICATE", "requirement duplicado no manifesto: "+requirementID)
			}
			requirementIDs[requirementID] = true
			scope, scopeErr := exactStringList(requirement["scope"], fmt.Sprintf("scope de %s", requirementID))
			if scopeErr != nil {
				return managedManifest{}, scopeErr
			}
			if len(scope) == 0 {
				return managedManifest{}, specError("SPEC_COVERAGE_EMPTY", "scope vazio em "+requirementID)
			}
			if hasDuplicates(scope) {
				return managedManifest{}, specError("SPEC_MANIFEST_INVALID", "scope duplicado em "+requirementID)
			}
			_ = requirementIndex
			spec.requirements = append(spec.requirements, managedRequirementEntry{id: requirementID, scope: scope})
		}
		manifest.specs = append(manifest.specs, spec)
	}
	if err := validateManagedPathCollisions(paths); err != nil {
		return managedManifest{}, err
	}
	if !sort.StringsAreSorted(paths) {
		return managedManifest{}, specError("SPEC_MANIFEST_INVALID", "paths de specs devem estar em ordem POSIX")
	}
	seenRisks := map[string]bool{}
	for index, raw := range rawRisks {
		risk, ok := raw.(map[string]any)
		if !ok || len(risk) != 3 || !hasExactKeys(risk, []string{"scope", "kind", "target"}) {
			return managedManifest{}, specError("SPEC_MANIFEST_INVALID", fmt.Sprintf("shape inválido em risk_coverage[%d]", index))
		}
		entry := managedRiskEntry{scope: stateString(risk["scope"]), kind: stateString(risk["kind"]), target: stateString(risk["target"])}
		if entry.scope == "" || entry.kind == "" || entry.target == "" {
			return managedManifest{}, specError("SPEC_MANIFEST_INVALID", fmt.Sprintf("risk_coverage[%d] inválido", index))
		}
		if !oneOf(entry.kind, "spec", "guard", "plan_gate") {
			return managedManifest{}, specError("SPEC_MANIFEST_INVALID", "kind de risco inválido: "+entry.kind)
		}
		identity := entry.scope + "\x00" + entry.kind + "\x00" + entry.target
		if seenRisks[identity] {
			return managedManifest{}, specError("SPEC_MANIFEST_INVALID", "risk_coverage duplicada: "+entry.scope)
		}
		seenRisks[identity] = true
		manifest.riskCoverage = append(manifest.riskCoverage, entry)
	}
	return manifest, nil
}

func deriveManagedSpecDiff(root, base, target, manifestPath string) (map[string]any, []byte, error) {
	baseTree, err := inspectManagedSpecTree(root, base, false, true)
	if err != nil {
		return nil, nil, err
	}
	targetTree, err := inspectManagedSpecTree(root, target, true, false)
	if err != nil {
		return nil, nil, err
	}
	targetManifest, err := loadManagedManifest(root, manifestPath)
	if err != nil {
		return nil, nil, err
	}
	if !sameStrings(manifestPaths(targetManifest), sortedRequirementPaths(targetTree)) {
		return nil, nil, specError("SPEC_MANIFEST_MISMATCH", "paths do manifesto não correspondem exatamente ao target")
	}
	if err := validateManagedTargetRequirements(targetManifest, targetTree); err != nil {
		return nil, nil, err
	}
	baseManifestPath := filepath.Join(base, "MANIFEST.json")
	baseManifest := managedManifest{schemaVersion: 1, specContract: 1, digest: nil}
	if len(baseTree.requirements) > 0 {
		if info, statErr := os.Lstat(baseManifestPath); statErr != nil || info.Mode()&os.ModeSymlink != 0 || !info.Mode().IsRegular() {
			return nil, nil, specError("SPEC_BASE_MANIFEST_MISSING", "base gerenciada possui specs sem MANIFEST.json")
		}
	}
	if info, statErr := os.Lstat(baseManifestPath); statErr == nil && info.Mode().IsRegular() && info.Mode()&os.ModeSymlink == 0 {
		baseManifest, err = loadManagedManifest(root, baseManifestPath)
		if err != nil {
			return nil, nil, err
		}
		if !sameStrings(manifestPaths(baseManifest), sortedRequirementPaths(baseTree)) {
			return nil, nil, specError("SPEC_BASE_MANIFEST_MISMATCH", "paths do manifesto da base não correspondem às specs aceitas")
		}
		if len(baseManifest.specs) > 0 {
			if err := validateManagedTargetRequirements(baseManifest, baseTree); err != nil {
				return nil, nil, err
			}
		}
	}
	current, future := manifestByID(baseManifest), manifestByID(targetManifest)
	added, modified, removed, renamed := []any{}, []any{}, []any{}, []any{}
	for _, identifier := range sortedDifferenceKeys(future, current) {
		added = append(added, map[string]any{"id": identifier, "path": future[identifier].path})
	}
	for _, identifier := range sortedDifferenceKeys(current, future) {
		removed = append(removed, map[string]any{"id": identifier, "path": current[identifier].path})
	}
	for _, identifier := range sortedIntersectionKeys(current, future) {
		previous, next := current[identifier], future[identifier]
		if previous.path != next.path {
			renamed = append(renamed, map[string]any{"id": identifier, "from": previous.path, "to": next.path})
		}
		if !bytes.Equal(baseTree.files[previous.path], targetTree.files[next.path]) {
			modified = append(modified, map[string]any{"id": identifier, "path": next.path})
		}
	}
	metadata := map[string]any{
		"schema_version": 1, "spec_contract": 1, "mode": "directory",
		"base_digest": baseTree.digest, "target_digest": targetTree.digest,
		"base_manifest_digest": baseManifest.digest, "target_manifest_digest": targetManifest.digest,
		"added": added, "modified": modified, "removed": removed, "renamed": renamed,
	}
	rendered, err := renderManagedSpecDiff(metadata, added, modified, removed, renamed)
	return metadata, rendered, err
}

func renderManagedSpecDiff(metadata map[string]any, sections ...[]any) ([]byte, error) {
	encoded, err := json.MarshalIndent(metadata, "", "  ")
	if err != nil {
		return nil, specError("SPEC_MANIFEST_INVALID", err.Error())
	}
	lines := []string{"# Spec Diff", "", "Esta é uma projeção derivada. O target completo e o MANIFEST são a fonte de verdade.", "", "```json", string(encoded), "```"}
	titles := []string{"ADDED", "MODIFIED", "REMOVED", "RENAMED"}
	for index, items := range sections {
		lines = append(lines, "", "## "+titles[index], "")
		if len(items) == 0 {
			lines = append(lines, "Nenhum.")
			continue
		}
		for _, raw := range items {
			item := raw.(map[string]any)
			if titles[index] == "RENAMED" {
				lines = append(lines, fmt.Sprintf("- `%s`: `%s` -> `%s`", item["id"], item["from"], item["to"]))
			} else {
				lines = append(lines, fmt.Sprintf("- `%s`: `%s`", item["id"], item["path"]))
			}
		}
	}
	return []byte(strings.TrimRight(strings.Join(lines, "\n"), "\r\n") + "\n"), nil
}

func loadModelSpecPackage(workspace methodWorkspace, directory string, coherence map[string]any) (map[string]any, error) {
	if stateInt(coherence["schema_version"]) != 2 {
		return map[string]any{}, nil
	}
	metadata, rendered, err := deriveManagedSpecDiff(workspace.root, workspace.currentSpec, filepath.Join(directory, "specs", "expected"), filepath.Join(directory, "specs", "MANIFEST.json"))
	if err != nil {
		return nil, err
	}
	manifest, err := loadManagedManifest(workspace.root, filepath.Join(directory, "specs", "MANIFEST.json"))
	if err != nil {
		return nil, err
	}
	if err := validateManagedScopeCoverage(workspace.root, filepath.Join(directory, "SCOPE.md"), manifest); err != nil {
		return nil, err
	}
	diffPath, err := specConfined(workspace.root, filepath.Join(directory, "specs", "diff.md"), "diff.md")
	if err != nil {
		return nil, err
	}
	info, err := os.Lstat(diffPath)
	if err != nil || info.Mode()&os.ModeSymlink != 0 || !info.Mode().IsRegular() {
		return nil, specError("SPEC_DIFF_STALE", "diff.md ausente; regenere com bm spec-diff antes do check")
	}
	actual, err := os.ReadFile(diffPath)
	if err != nil || !bytes.Equal(actual, rendered) {
		return nil, specError("SPEC_DIFF_STALE", "diff.md divergiu da projeção; regenere com bm spec-diff")
	}
	return map[string]any{
		"spec_contract": 1, "spec_base_digest": metadata["base_digest"],
		"spec_target_digest": metadata["target_digest"], "spec_manifest_digest": manifest.digest,
		"spec_diff_digest": sha256Bytes(actual),
	}, nil
}

func validateManagedTargetRequirements(manifest managedManifest, tree managedSpecTree) error {
	global := map[string]bool{}
	for _, item := range manifest.specs {
		parsed := tree.requirements[item.path]
		for identifier := range parsed {
			if global[identifier] {
				return specError("SPEC_REQUIREMENT_DUPLICATE", "requirement duplicado no target: "+identifier)
			}
			global[identifier] = true
		}
		declared := map[string]bool{}
		for _, requirement := range item.requirements {
			declared[requirement.id] = true
		}
		missing, unknown := differenceStringSet(parsed, declared), differenceBoolSet(declared, parsed)
		if len(missing)+len(unknown) > 0 {
			details := []string{}
			if len(missing) > 0 {
				details = append(details, "sem manifesto: "+strings.Join(missing, ", "))
			}
			if len(unknown) > 0 {
				details = append(details, "inexistente na spec: "+strings.Join(unknown, ", "))
			}
			return specError("SPEC_REQUIREMENT_MISMATCH", "requirements de "+item.path+" divergem ("+strings.Join(details, "; ")+")")
		}
	}
	return nil
}

func validateManagedScopeCoverage(root, scopePath string, manifest managedManifest) error {
	scopePath, err := specConfined(root, scopePath, "SCOPE.md")
	if err != nil {
		return err
	}
	info, err := os.Lstat(scopePath)
	if err != nil || info.Mode()&os.ModeSymlink != 0 || !info.Mode().IsRegular() {
		return specError("SPEC_SCOPE_MISSING", "SCOPE.md ausente ou symlink: "+scopePath)
	}
	content, err := os.ReadFile(scopePath)
	if err != nil || !validUTF8Text(content) {
		return specError("SPEC_SCOPE_INVALID", "SCOPE.md não é UTF-8")
	}
	identifiers, seen := []string{}, map[string]bool{}
	for _, match := range managedScopeHeading.FindAllStringSubmatch(string(content), -1) {
		identifier := match[1]
		prefix := strings.SplitN(identifier, "-", 2)[0]
		if !traceableScopePrefixes[prefix] {
			continue
		}
		if seen[identifier] {
			return specError("SPEC_SCOPE_INVALID", "ID duplicado no SCOPE.md: "+identifier)
		}
		seen[identifier] = true
		identifiers = append(identifiers, identifier)
	}
	if len(identifiers) == 0 {
		return specError("SPEC_SCOPE_INVALID", "SCOPE.md sem IDs rastreáveis")
	}
	coverage, targets := map[string][]string{}, map[string]bool{}
	for _, identifier := range identifiers {
		coverage[identifier] = []string{}
	}
	for _, spec := range manifest.specs {
		targets[spec.id] = true
		for _, requirement := range spec.requirements {
			targets[requirement.id] = true
			for _, scopeID := range requirement.scope {
				if !seen[scopeID] {
					return specError("SPEC_SCOPE_UNKNOWN", "ID de cobertura inexistente no SCOPE.md: "+scopeID)
				}
				coverage[scopeID] = append(coverage[scopeID], "spec:"+requirement.id)
			}
		}
	}
	for _, risk := range manifest.riskCoverage {
		if !seen[risk.scope] {
			return specError("SPEC_SCOPE_UNKNOWN", "ID de risco inexistente no SCOPE.md: "+risk.scope)
		}
		if !strings.HasPrefix(risk.scope, "RSK-") {
			return specError("SPEC_RISK_INVALID", "risk_coverage só aceita IDs RSK: "+risk.scope)
		}
		if risk.kind == "spec" && !targets[risk.target] {
			return specError("SPEC_RISK_TARGET_UNKNOWN", "target de spec inexistente: "+risk.target)
		}
		coverage[risk.scope] = append(coverage[risk.scope], risk.kind+":"+risk.target)
	}
	missing := []string{}
	for _, identifier := range identifiers {
		prefix := strings.SplitN(identifier, "-", 2)[0]
		if (mandatorySpecPrefixes[prefix] || prefix == "RSK") && len(coverage[identifier]) == 0 {
			missing = append(missing, identifier)
		}
	}
	if len(missing) > 0 {
		return specError("SPEC_COVERAGE_INCOMPLETE", "cobertura SCOPE -> spec incompleta: "+strings.Join(missing, ", "))
	}
	return nil
}

func unknownMapKeys(value map[string]any, allowed map[string]bool) []string {
	result := []string{}
	for key := range value {
		if !allowed[key] {
			result = append(result, key)
		}
	}
	sort.Strings(result)
	return result
}

func hasExactKeys(value map[string]any, keys []string) bool {
	if len(value) != len(keys) {
		return false
	}
	for _, key := range keys {
		if _, exists := value[key]; !exists {
			return false
		}
	}
	return true
}

func exactStringList(raw any, label string) ([]string, error) {
	values, ok := raw.([]any)
	if !ok {
		return nil, specError("SPEC_MANIFEST_INVALID", label+" deve ser lista")
	}
	result := make([]string, 0, len(values))
	for _, rawValue := range values {
		value, ok := rawValue.(string)
		if !ok || value == "" {
			return nil, specError("SPEC_MANIFEST_INVALID", label+" inválido")
		}
		result = append(result, value)
	}
	return result, nil
}

func manifestPaths(manifest managedManifest) []string {
	result := make([]string, 0, len(manifest.specs))
	for _, spec := range manifest.specs {
		result = append(result, spec.path)
	}
	return result
}

func sortedRequirementPaths(tree managedSpecTree) []string {
	result := make([]string, 0, len(tree.requirements))
	for path := range tree.requirements {
		result = append(result, path)
	}
	sort.Strings(result)
	return result
}

func sameStrings(left, right []string) bool {
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

func manifestByID(manifest managedManifest) map[string]managedSpecEntry {
	result := map[string]managedSpecEntry{}
	for _, entry := range manifest.specs {
		result[entry.id] = entry
	}
	return result
}

func sortedDifferenceKeys(left, right map[string]managedSpecEntry) []string {
	result := []string{}
	for key := range left {
		if _, exists := right[key]; !exists {
			result = append(result, key)
		}
	}
	sort.Strings(result)
	return result
}

func sortedIntersectionKeys(left, right map[string]managedSpecEntry) []string {
	result := []string{}
	for key := range left {
		if _, exists := right[key]; exists {
			result = append(result, key)
		}
	}
	sort.Strings(result)
	return result
}

func differenceStringSet(left map[string]string, right map[string]bool) []string {
	result := []string{}
	for key := range left {
		if !right[key] {
			result = append(result, key)
		}
	}
	sort.Strings(result)
	return result
}

func differenceBoolSet(left map[string]bool, right map[string]string) []string {
	result := []string{}
	for key := range left {
		if _, exists := right[key]; !exists {
			result = append(result, key)
		}
	}
	sort.Strings(result)
	return result
}
