package gokernel

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
)

const (
	maxScopePDFBytes = 128 * 1024 * 1024
	maxScopeBytes    = 512 * 1024
)

var scopeRequiredSections = []string{
	"Objetivo", "Resultados esperados", "Atores e perfis", "Fluxos",
	"Requisitos funcionais", "Requisitos não funcionais", "Regras de negócio",
	"Dados e estados", "Integrações e efeitos externos", "Critérios gerais de aceite",
	"Comportamentos de erro", "Riscos e casos para o planejamento", "Dentro do escopo",
	"Fora do escopo", "Decisões consolidadas", "Questões abertas", "Decisões bloqueantes",
	"Contradições", "Proveniência e cobertura",
}

var scopeStructuredSections = map[string]string{
	"Atores e perfis": "ACT", "Fluxos": "FLW", "Requisitos funcionais": "REQ",
	"Requisitos não funcionais": "NFR", "Regras de negócio": "BR", "Dados e estados": "DAT",
	"Integrações e efeitos externos": "INT", "Comportamentos de erro": "ERR",
	"Riscos e casos para o planejamento": "RSK", "Decisões consolidadas": "DEC",
}

var (
	scopeItemPattern    = regexp.MustCompile(`(?m)^### ((?:ACT|FLW|REQ|NFR|BR|DAT|INT|ERR|RSK|DEC)-[0-9]{3})\b[^\n]*$`)
	scopeSectionPattern = regexp.MustCompile(`(?m)^## ([^\n]+?)\s*$`)
	scopeTitlePattern   = regexp.MustCompile(`^# Escopo(?:\s+[-—:].+)?\s*\n`)
	scopePagePattern    = regexp.MustCompile(`PDF p(?:\.|p\.)\s*([0-9]+)(?:\s*[-–]\s*([0-9]+))?`)
	scopeSourceSingle   = regexp.MustCompile(`^PDF p\. [0-9]+$`)
	scopeSourceRange    = regexp.MustCompile(`^PDF pp\. [0-9]+\s*[-–]\s*[0-9]+$`)
	scopeFrontmatter    = regexp.MustCompile(`(?s)^---\r?\n.*?\r?\n---\r?\n\r?\n(.*)$`)
)

var scopePlaceholderPatterns = []*regexp.Regexp{
	regexp.MustCompile(`(?i)\bTBD\b`), regexp.MustCompile(`(?i)\bTODO\b`),
	regexp.MustCompile(`\?\?+`), regexp.MustCompile(`(?i)\ba definir\b`),
	regexp.MustCompile(`(?i)\bquando necessári[oa]s?\b`), regexp.MustCompile(`(?i)\bconforme necessári[oa]s?\b`),
	regexp.MustCompile(`(?i)\be similares\b`), regexp.MustCompile(`(?i)\betc\.?\b`),
	regexp.MustCompile(`(?i)\bdeve funcionar\b`), regexp.MustCompile(`(?i)\btratar erros\b`),
}

type scopeItem struct {
	id    string
	block string
}

func runScope(args []string) (any, error) {
	if len(args) == 0 {
		return nil, argparseError("the following arguments are required: action")
	}
	action := args[0]
	if !oneOf(action, "seal", "verify") {
		return nil, argparseError(fmt.Sprintf("argument action: invalid choice: '%s'", action))
	}
	flags, err := parseFlags(args[1:], map[string]bool{
		"--repo": true, "--change": true, "--source": true, "--draft": true,
		"--pages": true, "--extraction": true,
	}, map[string]bool{})
	if err != nil {
		return nil, err
	}
	change := lastValue(flags, "--change")
	if change == "" {
		return nil, argparseError("the following arguments are required: --change")
	}
	repo := lastValue(flags, "--repo")
	if repo == "" {
		repo, err = os.Getwd()
		if err != nil {
			return nil, scopeError("SCOPE_CHANGE_INVALID", "mudança não encontrada: "+change)
		}
	}
	if action == "verify" {
		return verifyScope(repo, change, lastValue(flags, "--source"))
	}
	source, draft := lastValue(flags, "--source"), lastValue(flags, "--draft")
	pagesRaw, extraction := lastValue(flags, "--pages"), lastValue(flags, "--extraction")
	if source == "" || draft == "" || pagesRaw == "" || extraction == "" {
		return nil, &commandError{message: "scope seal exige --source, --draft, --pages e --extraction"}
	}
	pages, err := strconv.Atoi(pagesRaw)
	if err != nil {
		return nil, argparseError("argument --pages: invalid int value: '" + pagesRaw + "'")
	}
	if !oneOf(extraction, "native", "ocr", "mixed") {
		return nil, argparseError("argument --extraction: invalid choice: '" + extraction + "'")
	}
	return sealScope(repo, change, source, draft, pages, extraction)
}

func scopeError(code, message string) error { return workflowError(code, message) }

func scopeRejectForeignPath(path, label string) error {
	for _, part := range strings.Split(filepath.ToSlash(path), "/") {
		if strings.EqualFold(part, ".planning") {
			return scopeError("SCOPE_SOURCE_INVALID", label+" usa namespace estrangeiro")
		}
	}
	return nil
}

func scopePDFMetadata(path string) (map[string]any, error) {
	if err := scopeRejectForeignPath(path, "fonte PDF"); err != nil {
		return nil, err
	}
	info, err := os.Lstat(path)
	if err != nil || info.Mode()&os.ModeSymlink != 0 || !info.Mode().IsRegular() {
		return nil, scopeError("SCOPE_SOURCE_INVALID", "fonte PDF ausente ou symlink")
	}
	if strings.ToLower(filepath.Ext(path)) != ".pdf" {
		return nil, scopeError("SCOPE_SOURCE_INVALID", "fonte deve possuir extensão .pdf")
	}
	if info.Size() <= 8 || info.Size() > maxScopePDFBytes {
		return nil, scopeError("SCOPE_SOURCE_INVALID", "fonte PDF vazia ou acima de 128 MiB")
	}
	name := filepath.Base(path)
	validName := regexp.MustCompile(`^[^/\\\x00-\x1f]+\.[pP][dD][fF]$`)
	if !validName.MatchString(name) {
		return nil, scopeError("SCOPE_SOURCE_INVALID", "nome do PDF é inválido")
	}
	file, err := os.Open(path)
	if err != nil {
		return nil, scopeError("SCOPE_SOURCE_INVALID", "fonte PDF ausente ou symlink")
	}
	defer file.Close()
	header := make([]byte, 5)
	if _, err := io.ReadFull(file, header); err != nil || !strings.HasPrefix(string(header), "%PDF-") {
		return nil, scopeError("SCOPE_SOURCE_INVALID", "assinatura PDF inválida")
	}
	if _, err := file.Seek(0, io.SeekStart); err != nil {
		return nil, scopeError("SCOPE_SOURCE_INVALID", "fonte PDF ausente ou symlink")
	}
	digest := sha256.New()
	if _, err := io.Copy(digest, file); err != nil {
		return nil, scopeError("SCOPE_SOURCE_INVALID", "fonte PDF ausente ou symlink")
	}
	return map[string]any{"name": name, "sha256": hex.EncodeToString(digest.Sum(nil))}, nil
}

func scopeDirectory(workspace methodWorkspace, change string) (string, error) {
	if !regexp.MustCompile(`^C[0-9]{3}-[a-z0-9]+(?:-[a-z0-9]+)*$`).MatchString(change) {
		return "", scopeError("SCOPE_CHANGE_INVALID", "mudança inválida: "+change)
	}
	directory := filepath.Join(workspace.changes, change)
	if err := workspace.validateWorkspacePath(directory); err != nil {
		return "", scopeError("SCOPE_CHANGE_INVALID", "mudança não encontrada: "+change)
	}
	info, err := os.Lstat(directory)
	if err != nil || info.Mode()&os.ModeSymlink != 0 || !info.IsDir() {
		return "", scopeError("SCOPE_CHANGE_INVALID", "mudança não encontrada: "+change)
	}
	return directory, nil
}

func sealScope(repo, change, source, draft string, pages int, extraction string) (map[string]any, error) {
	if pages < 1 || pages > 10000 {
		return nil, scopeError("SCOPE_SOURCE_INVALID", "quantidade de páginas inválida")
	}
	if !oneOf(extraction, "native", "ocr", "mixed") {
		return nil, scopeError("SCOPE_SOURCE_INVALID", "modo de extração inválido")
	}
	if err := scopeRejectForeignPath(draft, "draft"); err != nil {
		return nil, scopeError("SCOPE_FORMAT_INVALID", "draft usa namespace estrangeiro")
	}
	draftInfo, err := os.Lstat(draft)
	if err != nil || draftInfo.Mode()&os.ModeSymlink != 0 || !draftInfo.Mode().IsRegular() {
		return nil, scopeError("SCOPE_FORMAT_INVALID", "draft ausente ou symlink")
	}
	if draftInfo.Size() > maxScopeBytes {
		return nil, scopeError("SCOPE_FORMAT_INVALID", "SCOPE.md excede 512 KiB")
	}
	sourceMetadata, err := scopePDFMetadata(source)
	if err != nil {
		return nil, err
	}
	draftBytes, err := os.ReadFile(draft)
	if err != nil || !validUTF8Text(draftBytes) {
		return nil, scopeError("SCOPE_FORMAT_INVALID", "draft não é UTF-8")
	}
	body, coverage, err := validateScopeBody(string(draftBytes), pages)
	if err != nil {
		return nil, err
	}
	root, err := repositoryRoot(repo)
	if err != nil {
		return nil, scopeError("SCOPE_CHANGE_INVALID", "mudança não encontrada: "+change)
	}
	workspace := newMethodWorkspace(root)
	state, err := workspace.readState()
	if err != nil {
		return nil, err
	}
	active, ok := state["active_work"].(map[string]any)
	if !ok || stateString(active["kind"]) != "change" {
		return nil, scopeError("SCOPE_CHANGE_INVALID", "não existe mudança ativa")
	}
	if stateString(active["id"]) != change {
		return nil, scopeError("SCOPE_CHANGE_INVALID", "mudança informada não é a ativa")
	}
	if !oneOf(stateString(state["status"]), "planning", "scope_ready") || !oneOf(stateString(active["status"]), "planning", "scope_ready") {
		return nil, scopeError("SCOPE_CHANGE_INVALID", "mudança já avançou além do intake")
	}
	directory, err := scopeDirectory(workspace, change)
	if err != nil {
		return nil, err
	}
	scopePath := filepath.Join(directory, "SCOPE.md")
	metadata := map[string]any{
		"schema_version": 1, "document": "bianchini-scope", "status": "ready_for_sdd", "change": change,
		"source": map[string]any{
			"kind": "pdf", "name": sourceMetadata["name"], "sha256": sourceMetadata["sha256"],
			"pages": pages, "extraction": extraction,
		},
		"coverage": coverage, "sealed_at": utcNow(),
	}
	metadata["scope_digest"] = scopeDigest(metadata, body)
	document, err := scopeDocument(metadata, body)
	if err != nil {
		return nil, scopeError("SCOPE_FORMAT_INVALID", err.Error())
	}
	var previous []byte
	hadPrevious := false
	if info, statErr := os.Lstat(scopePath); statErr == nil && info.Mode().IsRegular() && info.Mode()&os.ModeSymlink == 0 {
		previous, err = os.ReadFile(scopePath)
		if err != nil {
			return nil, scopeError("SCOPE_FORMAT_INVALID", "SCOPE.md atual não pôde ser preservado")
		}
		hadPrevious = true
	}
	if err := workspace.atomicWrite(scopePath, document); err != nil {
		return nil, err
	}
	active["status"] = "scope_ready"
	state["active_work"] = active
	state["current_unit"] = "scope"
	state["status"] = "scope_ready"
	state["blockers"] = []any{}
	state["next_action"] = "Executar /sdd-planning para " + change + "."
	state["digest"] = metadata["scope_digest"]
	state["updated_at"] = utcNow()
	pointers := stateObject(state["pointers"])
	pointers["scope"] = ".bianchini/changes/" + change + "/SCOPE.md"
	state["pointers"] = pointers
	if err := workspace.writeState(state, "# Estado atual"); err != nil {
		if hadPrevious {
			_ = workspace.atomicWrite(scopePath, previous)
		} else {
			_ = os.Remove(scopePath)
		}
		return nil, err
	}
	return map[string]any{
		"change": change, "status": "ready_for_sdd", "scope": scopePath,
		"scope_digest": metadata["scope_digest"], "source_sha256": sourceMetadata["sha256"],
		"coverage": coverage, "next_action": "/sdd-planning",
	}, nil
}

func verifyScope(repo, change, source string) (map[string]any, error) {
	root, err := repositoryRoot(repo)
	if err != nil {
		return nil, scopeError("SCOPE_CHANGE_INVALID", "mudança não encontrada: "+change)
	}
	workspace := newMethodWorkspace(root)
	state, err := workspace.readState()
	if err != nil {
		return nil, err
	}
	directory, err := scopeDirectory(workspace, change)
	if err != nil {
		return nil, err
	}
	scopePath := filepath.Join(directory, "SCOPE.md")
	metadata, err := readStructuredFrontmatter(scopePath)
	if err != nil {
		return nil, scopeError("SCOPE_FORMAT_INVALID", err.Error())
	}
	expectedKeys := []string{"schema_version", "document", "status", "change", "source", "coverage", "sealed_at", "scope_digest"}
	if !hasExactKeys(metadata, expectedKeys) {
		return nil, scopeError("SCOPE_FORMAT_INVALID", "frontmatter do SCOPE.md é inválido")
	}
	if stateInt(metadata["schema_version"]) != 1 || stateString(metadata["document"]) != "bianchini-scope" || stateString(metadata["status"]) != "ready_for_sdd" || stateString(metadata["change"]) != change {
		return nil, scopeError("SCOPE_FORMAT_INVALID", "identidade do SCOPE.md é inválida")
	}
	sourceInfo, ok := metadata["source"].(map[string]any)
	if !ok || !hasExactKeys(sourceInfo, []string{"kind", "name", "sha256", "pages", "extraction"}) {
		return nil, scopeError("SCOPE_FORMAT_INVALID", "metadados da fonte são inválidos")
	}
	pages := stateInt(sourceInfo["pages"])
	name, sourceHash := stateString(sourceInfo["name"]), stateString(sourceInfo["sha256"])
	if stateString(sourceInfo["kind"]) != "pdf" || pages < 1 || pages > 10000 || !oneOf(stateString(sourceInfo["extraction"]), "native", "ocr", "mixed") || name == "" || !strings.HasSuffix(strings.ToLower(name), ".pdf") || filepath.Base(name) != name || !regexp.MustCompile(`^[0-9a-f]{64}$`).MatchString(sourceHash) {
		return nil, scopeError("SCOPE_FORMAT_INVALID", "fonte selada é inválida")
	}
	content, err := os.ReadFile(scopePath)
	if err != nil || !validUTF8Text(content) {
		return nil, scopeError("SCOPE_FORMAT_INVALID", "corpo do SCOPE.md ausente")
	}
	match := scopeFrontmatter.FindSubmatch(content)
	if match == nil {
		return nil, scopeError("SCOPE_FORMAT_INVALID", "corpo do SCOPE.md ausente")
	}
	originalBody := string(match[1])
	body, coverage, err := validateScopeBody(originalBody, pages)
	if err != nil {
		return nil, err
	}
	if body != strings.ReplaceAll(originalBody, "\r\n", "\n") {
		return nil, scopeError("SCOPE_FORMAT_INVALID", "corpo do SCOPE.md não está normalizado")
	}
	if !mapsEqual(stateObject(metadata["coverage"]), coverage) {
		return nil, scopeError("SCOPE_FORMAT_INVALID", "cobertura selada diverge do documento")
	}
	digest := stateString(metadata["scope_digest"])
	unsigned := cloneMap(metadata)
	delete(unsigned, "scope_digest")
	if digest != scopeDigest(unsigned, body) {
		return nil, scopeError("SCOPE_STALE", "digest do SCOPE.md diverge do conteúdo")
	}
	if source != "" {
		current, sourceErr := scopePDFMetadata(source)
		if sourceErr != nil {
			return nil, sourceErr
		}
		if current["sha256"] != sourceHash {
			return nil, scopeError("SCOPE_STALE", "fonte PDF diverge do selo")
		}
	}
	active, activeOK := state["active_work"].(map[string]any)
	if activeOK && stateString(active["id"]) == change && (stateString(state["status"]) == "scope_ready" || stateString(active["status"]) == "scope_ready") {
		expectedPointer := ".bianchini/changes/" + change + "/SCOPE.md"
		pointers := stateObject(state["pointers"])
		if stateString(state["status"]) != "scope_ready" || stateString(active["status"]) != "scope_ready" || stateString(state["digest"]) != digest || stateString(pointers["scope"]) != expectedPointer {
			return nil, scopeError("SCOPE_STALE", "STATE.md diverge do escopo selado")
		}
	}
	return map[string]any{
		"change": change, "status": "ready_for_sdd", "scope": scopePath,
		"scope_digest": digest, "source_sha256": sourceHash, "coverage": coverage, "verified": true,
	}, nil
}

func validateScopeBody(raw string, pages int) (string, map[string]any, error) {
	if strings.HasPrefix(raw, "---") {
		return "", nil, scopeError("SCOPE_FORMAT_INVALID", "draft não pode fornecer frontmatter; o CLI gera o selo")
	}
	if len([]byte(raw)) > maxScopeBytes {
		return "", nil, scopeError("SCOPE_FORMAT_INVALID", "SCOPE.md excede 512 KiB")
	}
	normalized := strings.TrimSpace(strings.ReplaceAll(raw, "\r\n", "\n")) + "\n"
	for _, pattern := range scopePlaceholderPatterns {
		if pattern.MatchString(normalized) {
			return "", nil, scopeError("SCOPE_AMBIGUOUS", "placeholder ou linguagem vaga encontrada: "+pattern.String())
		}
	}
	sections, err := parseScopeSections(normalized)
	if err != nil {
		return "", nil, err
	}
	for _, name := range []string{"Objetivo", "Resultados esperados", "Dentro do escopo", "Fora do escopo"} {
		if len(sections[name]) < 20 {
			return "", nil, scopeError("SCOPE_FORMAT_INVALID", "seção insuficiente: "+name)
		}
	}
	closed := map[string]string{"Questões abertas": "questão aberta", "Decisões bloqueantes": "decisão bloqueante", "Contradições": "contradição aberta"}
	for _, name := range []string{"Questões abertas", "Decisões bloqueantes", "Contradições"} {
		if sections[name] != "Nenhuma." {
			return "", nil, scopeError("SCOPE_AMBIGUOUS", closed[name]+" impede o selo")
		}
	}
	structuredNames := make([]string, 0, len(scopeStructuredSections))
	for name := range scopeStructuredSections {
		structuredNames = append(structuredNames, name)
	}
	sort.Strings(structuredNames)
	for _, name := range structuredNames {
		prefix := scopeStructuredSections[name]
		matches := scopeItemPattern.FindAllStringSubmatch(sections[name], -1)
		if len(matches) > 0 {
			for _, match := range matches {
				if !strings.HasPrefix(match[1], prefix+"-") {
					return "", nil, scopeError("SCOPE_FORMAT_INVALID", match[1]+" está na seção incorreta: "+name)
				}
			}
			continue
		}
		value := sections[name]
		allowed := value == "Nenhuma." || value == "Não especificado no PDF." || (strings.HasPrefix(value, "Não aplicável:") && strings.TrimSpace(strings.TrimPrefix(value, "Não aplicável:")) != "")
		if !allowed {
			return "", nil, scopeError("SCOPE_FORMAT_INVALID", name+" exige item "+prefix+" ou ausência explícita")
		}
	}
	items, err := parseScopeItems(normalized)
	if err != nil {
		return "", nil, err
	}
	hasRequirement := false
	for _, item := range items {
		if strings.HasPrefix(item.id, "REQ-") {
			hasRequirement = true
		}
	}
	if !hasRequirement {
		return "", nil, scopeError("SCOPE_FORMAT_INVALID", "ao menos um REQ é obrigatório")
	}
	referencedPages := []int{}
	for _, item := range items {
		sourcePattern := regexp.MustCompile(`(?m)^- Fonte:\s*(.+?)\s*$`)
		match := sourcePattern.FindStringSubmatch(item.block)
		if match == nil {
			return "", nil, scopeError("SCOPE_SOURCE_INVALID", "item sem fonte: "+item.id)
		}
		itemPages, sourceErr := scopeSourcePages(match[1], pages)
		if sourceErr != nil {
			return "", nil, sourceErr
		}
		referencedPages = append(referencedPages, itemPages...)
		if strings.HasPrefix(item.id, "REQ-") || strings.HasPrefix(item.id, "NFR-") {
			if !regexp.MustCompile(`(?m)^- Aceite:\s*$`).MatchString(item.block) {
				return "", nil, scopeError("SCOPE_FORMAT_INVALID", item.id+" exige bloco de aceite")
			}
			if !strings.Contains(item.block, "GIVEN") || !strings.Contains(item.block, "WHEN") || !strings.Contains(item.block, "THEN") {
				return "", nil, scopeError("SCOPE_AMBIGUOUS", item.id+" exige aceite GIVEN/WHEN/THEN")
			}
		}
		if strings.HasPrefix(item.id, "FLW-") {
			for _, field := range []string{"Ator", "Gatilho", "Pré-condições", "Caminho principal", "Resultado", "Falhas"} {
				if !regexp.MustCompile(`(?m)^- ` + regexp.QuoteMeta(field) + `:\s*\S`).MatchString(item.block) {
					return "", nil, scopeError("SCOPE_FORMAT_INVALID", item.id+" exige campo "+field)
				}
			}
		}
	}
	if len(referencedPages) == 0 {
		return "", nil, scopeError("SCOPE_SOURCE_INVALID", "nenhuma página do PDF foi referenciada")
	}
	coverage := map[string]any{
		"identified_items": len(items), "sourced_items": len(items), "unsourced_items": 0,
		"open_questions": 0, "blocking_decisions": 0, "open_contradictions": 0,
	}
	provenance := fmt.Sprintf("- Páginas processadas: 1-%d de %d.\n- Itens estruturados: %d\n- Itens sem fonte: 0\n- Questões abertas: 0\n- Decisões bloqueantes: 0\n- Contradições abertas: 0", pages, pages, len(items))
	body, err := replaceScopeProvenance(normalized, provenance)
	return body, coverage, err
}

func parseScopeSections(body string) (map[string]string, error) {
	if !scopeTitlePattern.MatchString(body) {
		return nil, scopeError("SCOPE_FORMAT_INVALID", "documento deve iniciar com # Escopo")
	}
	matches := scopeSectionPattern.FindAllStringSubmatchIndex(body, -1)
	names, counts := []string{}, map[string]int{}
	for _, match := range matches {
		name := strings.TrimSpace(body[match[2]:match[3]])
		names = append(names, name)
		counts[name]++
	}
	duplicates := []string{}
	for name, count := range counts {
		if count > 1 {
			duplicates = append(duplicates, name)
		}
	}
	sort.Strings(duplicates)
	if len(duplicates) > 0 {
		return nil, scopeError("SCOPE_FORMAT_INVALID", "seção duplicada: "+duplicates[0])
	}
	allowed := stringSet(scopeRequiredSections)
	for _, name := range names {
		if !allowed[name] {
			return nil, scopeError("SCOPE_FORMAT_INVALID", "seção desconhecida: "+name)
		}
	}
	for _, required := range scopeRequiredSections {
		if counts[required] == 0 {
			return nil, scopeError("SCOPE_FORMAT_INVALID", "seção obrigatória ausente: "+required)
		}
	}
	if !sameStrings(names, scopeRequiredSections) {
		return nil, scopeError("SCOPE_FORMAT_INVALID", "seções fora da ordem canônica")
	}
	result := map[string]string{}
	for index, match := range matches {
		end := len(body)
		if index+1 < len(matches) {
			end = matches[index+1][0]
		}
		name := strings.TrimSpace(body[match[2]:match[3]])
		result[name] = strings.TrimSpace(body[match[1]:end])
		if result[name] == "" {
			return nil, scopeError("SCOPE_FORMAT_INVALID", "seção vazia: "+name)
		}
	}
	return result, nil
}

func parseScopeItems(body string) ([]scopeItem, error) {
	matches := scopeItemPattern.FindAllStringSubmatchIndex(body, -1)
	seen := map[string]bool{}
	items := make([]scopeItem, 0, len(matches))
	for index, match := range matches {
		identifier := body[match[2]:match[3]]
		if seen[identifier] {
			return nil, scopeError("SCOPE_FORMAT_INVALID", "ID duplicado: "+identifier)
		}
		seen[identifier] = true
		end := len(body)
		if index+1 < len(matches) {
			end = matches[index+1][0]
		}
		if sectionOffset := strings.Index(body[match[1]:end], "\n## "); sectionOffset >= 0 {
			end = match[1] + sectionOffset
		}
		items = append(items, scopeItem{id: identifier, block: strings.TrimSpace(body[match[0]:end])})
	}
	return items, nil
}

func scopeSourcePages(value string, pages int) ([]int, error) {
	if strings.ToLower(value) == "decisão do usuário" {
		return []int{}, nil
	}
	if !scopeSourceSingle.MatchString(value) && !scopeSourceRange.MatchString(value) {
		return nil, scopeError("SCOPE_SOURCE_INVALID", "fonte deve ser PDF p. N, PDF pp. N-M ou decisão do usuário")
	}
	match := scopePagePattern.FindStringSubmatch(value)
	first, _ := strconv.Atoi(match[1])
	last := first
	if match[2] != "" {
		last, _ = strconv.Atoi(match[2])
	}
	if first < 1 || last < first {
		return nil, scopeError("SCOPE_SOURCE_INVALID", "intervalo de páginas inválido")
	}
	result := []int{}
	for page := first; page <= last; page++ {
		if page > pages {
			return nil, scopeError("SCOPE_SOURCE_INVALID", fmt.Sprintf("página %d fora do PDF de %d páginas", page, pages))
		}
		result = append(result, page)
	}
	return result, nil
}

func replaceScopeProvenance(body, value string) (string, error) {
	if _, err := parseScopeSections(body); err != nil {
		return "", err
	}
	marker := "## Proveniência e cobertura"
	index := strings.Index(body, marker)
	return strings.TrimRight(body[:index], " \t\r\n") + "\n\n" + marker + "\n\n" + strings.TrimSpace(value) + "\n", nil
}

func scopeDigest(metadata map[string]any, body string) string {
	encoded, _ := canonicalJSON(metadata)
	return sha256Bytes(append(append(encoded, '\n'), []byte(body)...))
}

func scopeDocument(metadata map[string]any, body string) ([]byte, error) {
	encoded, err := json.MarshalIndent(metadata, "", "  ")
	if err != nil {
		return nil, err
	}
	return []byte("---\n" + string(encoded) + "\n---\n\n" + strings.TrimRight(body, "\r\n") + "\n"), nil
}
