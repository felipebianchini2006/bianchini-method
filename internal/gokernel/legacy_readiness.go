package gokernel

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"unicode"
	"unicode/utf8"

	"golang.org/x/text/unicode/norm"
)

var (
	legacyPlanningWords = regexp.MustCompile(`[\p{L}\p{N}_-]+`)
	legacyPlaceholder   = regexp.MustCompile(`(?i)\b(?:TBD|TODO|FIXME|a definir|tratar erros|preencher depois)\b|<(?:alvo|arquivo|comando|caminho|se[cç][aã]o|descri[cç][aã]o|id|nome)[^>]*>`)
	legacyRawReference  = regexp.MustCompile(`(?i)(?:docs/superpowers|(?:^|/)inputs/|PLANO\s+Task|writing-plans|Superpowers)`)
	legacyResearchMode  = regexp.MustCompile(`(?mi)^Research mode:\s*(\S+)\s*$`)
	legacyResearchWhy   = regexp.MustCompile(`(?mi)^Motivo:\s*\S`)
	legacyAccessedAt    = regexp.MustCompile(`(?i)Acessado em:\s*\d{4}-\d{2}-\d{2}`)
	legacySplitAt       = regexp.MustCompile(`^\d{4}-\d{2}-\d{2}T`)
	legacyReadinessID   = regexp.MustCompile(`^(?:D|A|P|U|S|DS|SD)-[0-9]{3}$`)
)

var legacyUnitFields = []string{
	"Execution", "Review", "Test seams", "Spec refs", "Files", "Contract", "Verification", "Done when",
}

var legacyReadinessCollections = map[string]*regexp.Regexp{
	"decisions":       regexp.MustCompile(`^D-[0-9]{3}$`),
	"assumptions":     regexp.MustCompile(`^A-[0-9]{3}$`),
	"pitfalls":        regexp.MustCompile(`^P-[0-9]{3}$`),
	"user_actions":    regexp.MustCompile(`^U-[0-9]{3}$`),
	"spikes":          regexp.MustCompile(`^S-[0-9]{3}$`),
	"design_surfaces": regexp.MustCompile(`^DS-[0-9]{3}$`),
	"spec_deltas":     regexp.MustCompile(`^SD-[0-9]{3}$`),
}

var legacyNonCommandPrefixes = map[string]bool{
	"aplicar": true, "confirmar": true, "executar": true, "revisar": true,
	"rodar": true, "testar": true, "validar": true, "verificar": true,
}

var legacyQualityV2Changes = map[string]bool{
	"api-contract": true, "authorization": true, "behavioral": true, "bug": true,
	"business-rule": true, "calculation": true, "config": true, "copy": true,
	"data-model": true, "data-transform": true, "dependency": true, "deployment": true,
	"documentation": true, "financial": true, "infrastructure": true, "integration": true,
	"inventory": true, "mechanical": true, "migration": true, "money": true,
	"observability": true, "offline": true, "parser": true, "payment": true,
	"performance": true, "permission": true, "platform": true, "refactor": true,
	"security": true, "state-machine": true, "stock": true, "style": true,
	"sync": true, "visual": true, "workflow": true,
}

func legacyWordCount(content string) int {
	return len(legacyPlanningWords.FindAllString(content, -1))
}

func legacyOrderedUnique(values []string) []string {
	seen := make(map[string]bool, len(values))
	result := make([]string, 0, len(values))
	for _, value := range values {
		if !seen[value] {
			seen[value] = true
			result = append(result, value)
		}
	}
	return result
}

func legacyPlanningText(root, value, label string) (string, string, error) {
	if strings.TrimSpace(value) == "" {
		return "", "", nil
	}
	path, err := confinedPath(root, value, label, true)
	if err != nil {
		return "", "", err
	}
	content, err := os.ReadFile(path)
	if err != nil {
		return path, "", err
	}
	if !utf8.Valid(content) || bytesContainNUL(content) {
		return path, "", fmt.Errorf("%s: arquivo deve ser UTF-8 textual", label)
	}
	return path, string(content), nil
}

func bytesContainNUL(content []byte) bool {
	for _, value := range content {
		if value == 0 {
			return true
		}
	}
	return false
}

func legacyUnitField(section, field string) string {
	prefix := "**" + strings.ToLower(field) + ":**"
	for _, line := range strings.Split(section, "\n") {
		trimmed := strings.TrimSpace(line)
		if strings.HasPrefix(strings.ToLower(trimmed), prefix) {
			return strings.TrimSpace(trimmed[len(prefix):])
		}
	}
	return ""
}

func legacyUnitSections(content string) []struct{ heading, content string } {
	matches := legacyPlanningUnit.FindAllStringIndex(content, -1)
	result := make([]struct{ heading, content string }, 0, len(matches))
	for index, match := range matches {
		end := len(content)
		if index+1 < len(matches) {
			end = matches[index+1][0]
		}
		result = append(result, struct{ heading, content string }{
			heading: strings.TrimSpace(content[match[0]:match[1]]), content: content[match[0]:end],
		})
	}
	return result
}

func legacyPlanningAudit(statePath, root string, strict, requireChecker bool) (map[string]any, error) {
	state, err := validateStateFile(statePath, "")
	if err != nil {
		return nil, err
	}
	planning := stateObject(state["planning"])
	quality := stateInt(planning["quality_version"])
	qualityEnabled := quality == 1 || quality == 2
	qualityV2 := quality == 2
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
		contract := "legacy-compatible"
		if qualityV2 {
			contract = "planning-quality-v2"
		}
		return map[string]any{"valid": true, "quality_contract": contract, "profile": profile, "recommended_profile": "lean", "metrics": metrics, "limits": limits, "warnings": []string{}}, nil
	}

	errors := make([]string, 0)
	warnings := make([]string, 0)
	pack := stateObject(stateObject(state["approval"])["package"])
	packageFiles := stateStringSlice(pack["files"])
	packageSet := stringSet(packageFiles)
	plans := stateArray(state["plans"])
	researchValue := stateString(planning["research"])
	researchMode := stateString(planning["research_mode"])
	inferredMode := false
	contractValues := []string{researchValue, stateString(planning["spec"]), stateString(planning["review"])}
	for _, rawPlan := range plans {
		contractValues = append(contractValues, stateString(stateObject(rawPlan)["path"]))
	}
	if qualityV2 {
		contractValues = append(contractValues, stateString(planning["readiness"]), stateString(planning["user_actions"]))
		if design := stateString(planning["design_manifest"]); design != "" {
			contractValues = append(contractValues, design)
		}
	}
	if enforced {
		if !qualityEnabled {
			errors = append(errors, "planning.quality_version: esperado 1 ou 2 para novo planejamento")
		}
		if researchMode != "" && !oneOf(researchMode, "repo_only", "targeted_web", "full") {
			errors = append(errors, "planning.research_mode: esperado repo_only, targeted_web ou full")
		}
		for _, value := range contractValues {
			if value == "" {
				errors = append(errors, "pacote: pesquisa, spec, revisão e planos devem ter caminhos locais")
			} else if !packageSet[value] {
				errors = append(errors, "pacote: artefato contratual ausente do manifesto: "+value)
			}
		}
	}

	_, research, researchErr := legacyPlanningText(root, researchValue, "planning.research")
	if researchErr != nil && enforced {
		errors = append(errors, researchErr.Error())
	}
	if enforced {
		if research == "" {
			errors = append(errors, "pesquisa: STACK_RESEARCH.md local é obrigatório")
		} else {
			if researchMode == "" && stateString(stateObject(state["approval"])["status"]) == "approved" {
				if strings.Contains(research, "https://") && strings.Contains(research, "Fonte primária:") {
					researchMode = "targeted_web"
				} else {
					researchMode = "repo_only"
				}
				inferredMode = true
				warnings = append(warnings, "planning.research_mode ausente em pacote aprovado anterior; inferido como "+researchMode+" somente para compatibilidade")
			} else if researchMode == "" {
				errors = append(errors, "planning.research_mode: esperado repo_only, targeted_web ou full")
			}
			if !inferredMode {
				match := legacyResearchMode.FindStringSubmatch(research)
				if len(match) != 2 || match[1] != researchMode {
					errors = append(errors, "pesquisa: Research mode deve coincidir com planning.research_mode")
				}
				if !legacyResearchWhy.MatchString(research) {
					errors = append(errors, "pesquisa: registre Motivo para o menor modo suficiente")
				}
			}
			switch researchMode {
			case "repo_only":
				for _, heading := range []string{"## Stack detectada", "## Inventário local", "## Decisões aplicadas", "## Riscos e lacunas"} {
					if !strings.Contains(research, heading) {
						errors = append(errors, "pesquisa: seção obrigatória ausente: "+heading)
					}
				}
				for _, field := range []string{"Manifests:", "Lockfiles:", "CI:", "Testes:", "Padrões locais:"} {
					if !strings.Contains(research, field) {
						errors = append(errors, "pesquisa repo_only: inventário ausente: "+field)
					}
				}
			case "targeted_web", "full":
				for _, heading := range []string{"## Stack detectada", "## Fontes primárias", "## Decisões aplicadas", "## Alternativas rejeitadas", "## Riscos e lacunas"} {
					if !strings.Contains(research, heading) {
						errors = append(errors, "pesquisa: seção obrigatória ausente: "+heading)
					}
				}
				if !strings.Contains(research, "https://") {
					errors = append(errors, "pesquisa: ao menos uma URL HTTPS de fonte primária é obrigatória")
				}
				if !strings.Contains(research, "Fonte primária:") {
					errors = append(errors, "pesquisa: classifique explicitamente cada referência como Fonte primária")
				}
				if !legacyAccessedAt.MatchString(research) {
					errors = append(errors, "pesquisa: registre Acessado em: YYYY-MM-DD")
				}
				if researchMode == "full" {
					for _, heading := range []string{"## Escopo da pesquisa", "## Decisões críticas"} {
						if !strings.Contains(research, heading) {
							errors = append(errors, "pesquisa: seção obrigatória do modo full ausente: "+heading)
						}
					}
				}
			}
		}
	}

	sharedContext := ""
	for _, field := range []string{"research", "spec", "review"} {
		value := stateString(planning[field])
		_, content, textErr := legacyPlanningText(root, value, "planning."+field)
		if textErr != nil && enforced {
			errors = append(errors, textErr.Error())
		}
		if enforced && content == "" {
			errors = append(errors, "planning."+field+": arquivo ausente ou vazio")
		}
		if field == "spec" {
			sharedContext = content
		}
	}

	unitCount := 0
	planWords := make([]int, 0, len(plans))
	unitWords := make([]int, 0)
	planContents := make(map[string]string)
	for _, rawPlan := range plans {
		plan := stateObject(rawPlan)
		identifier := stateString(plan["id"])
		pathValue := stateString(plan["path"])
		_, content, textErr := legacyPlanningText(root, pathValue, "plan "+identifier)
		if textErr != nil && enforced {
			errors = append(errors, textErr.Error())
		}
		if content == "" {
			if enforced {
				errors = append(errors, "plano "+identifier+": arquivo ausente ou vazio")
			}
			continue
		}
		planContents[pathValue] = content
		planWords = append(planWords, legacyWordCount(content))
		sections := legacyUnitSections(content)
		unitCount += len(sections)
		if enforced && len(sections) == 0 {
			errors = append(errors, "plano "+identifier+": nenhuma unidade executável encontrada")
		}
		if enforced && legacyPlaceholder.MatchString(content) {
			errors = append(errors, "plano "+identifier+": placeholder ou instrução vaga")
		}
		if enforced && legacyRawReference.MatchString(content) {
			errors = append(errors, "plano "+identifier+": referência operacional a fonte bruta/legado")
		}
		for _, section := range sections {
			unitWords = append(unitWords, legacyWordCount(section.content))
			fields := append([]string(nil), legacyUnitFields...)
			if qualityV2 {
				fields = append(fields, "Change", "Readiness refs")
			}
			for _, field := range fields {
				if legacyUnitField(section.content, field) == "" {
					errors = append(errors, fmt.Sprintf("plano %s / %s: campo %s ausente", identifier, section.heading, field))
				}
			}
		}
		titles := make([]string, 0, len(sections))
		for _, section := range sections {
			titles = append(titles, section.heading)
		}
		titleText := strings.ToLower(strings.Join(titles, "\n"))
		if strings.Contains(titleText, "baseline") || strings.Contains(titleText, "lint") || strings.Contains(titleText, "setup") {
			warnings = append(warnings, "plano "+identifier+": confirme que baseline/lint/setup foi incorporado à primeira entrega real")
		}
		if strings.Contains(titleText, "homologação") || strings.Contains(titleText, "homologacao") || strings.Contains(titleText, "evidência de release") || strings.Contains(titleText, "evidencias de release") {
			warnings = append(warnings, "plano "+identifier+": possível duplicação do gate homologar-sistema")
		}
	}

	var readinessSummary any
	if qualityV2 {
		summary, readinessErrors, readinessWarnings := legacyValidateReadiness(state, root, packageSet)
		readinessSummary = summary
		errors = append(errors, readinessErrors...)
		warnings = append(warnings, readinessWarnings...)
		if readinessPath := stateString(planning["readiness"]); readinessPath != "" {
			path, _, pathErr := legacyPlanningText(root, readinessPath, "planning.readiness")
			if pathErr == nil && path != "" {
				readiness, readErr := legacyReadJSONDocument(path, "READINESS.md")
				if readErr == nil {
					for planPath, planContent := range planContents {
						errors = append(errors, legacyValidateQualityV2Plan(planPath, planContent, readiness)...)
					}
				}
			}
		}
		if requireChecker {
			checker, checkerOK := planning["checker"].(map[string]any)
			if !checkerOK {
				errors = append(errors, "planning.checker: contrato obrigatório ausente")
			} else {
				if stateString(checker["status"]) != "passed" {
					errors = append(errors, "planning.checker.status: esperado passed")
				}
				rounds := stateInt(checker["rounds"])
				if rounds != 1 && rounds != 2 {
					errors = append(errors, "planning.checker.rounds: esperado 1 ou 2")
				}
				inputFiles := make([]string, 0, len(packageFiles))
				for _, value := range packageFiles {
					if value != stateString(planning["review"]) {
						inputFiles = append(inputFiles, value)
					}
				}
				if len(inputFiles) == 0 {
					errors = append(errors, "checker: pacote sem entradas auditáveis")
				} else if manifest, manifestErr := legacyBuildManifest(root, inputFiles); manifestErr != nil {
					errors = append(errors, manifestErr.Error())
				} else if stateString(checker["package_digest"]) != sha256Bytes(manifest) {
					errors = append(errors, "planning.checker.package_digest: pacote mudou após a revisão")
				}
				reviewPath, reviewContent, reviewErr := legacyPlanningText(root, stateString(planning["review"]), "planning.review")
				if reviewErr != nil || reviewContent == "" {
					errors = append(errors, "planning.checker.report_digest: planning.review ausente")
				} else if digest, digestErr := legacyFileDigest(reviewPath); digestErr != nil || stateString(checker["report_digest"]) != digest {
					errors = append(errors, "planning.checker.report_digest: relatório mudou após a revisão")
				}
			}
		}
	}

	if enforced {
		verification := stateObject(state["verification"])
		for _, stage := range []string{"fast", "plan", "release"} {
			commands := stateStringSlice(stateObject(verification[stage])["commands"])
			if len(commands) == 0 {
				errors = append(errors, "verification."+stage+": informe ao menos um comando real")
			}
			for _, command := range commands {
				parts := strings.Fields(strings.TrimSpace(command))
				first := ""
				if len(parts) > 0 {
					first = strings.ToLower(parts[0])
				}
				if first == "" || legacyPlaceholder.MatchString(command) {
					errors = append(errors, "verification."+stage+": comando vazio, vago ou com placeholder")
				} else if legacyNonCommandPrefixes[first] {
					errors = append(errors, "verification."+stage+": procedimento em prosa não é comando reproduzível: "+command)
				}
			}
		}
	}

	packageWords := 0
	for _, value := range packageFiles {
		path, pathErr := confinedPath(root, value, "approval.package.files", true)
		if pathErr != nil {
			continue
		}
		content, readErr := os.ReadFile(path)
		if readErr == nil && utf8.Valid(content) && !bytesContainNUL(content) {
			packageWords += legacyWordCount(string(content))
		}
	}
	metrics := map[string]int{
		"plans": len(plans), "execution_units": unitCount,
		"platforms":            len(stateStringSlice(stateObject(state["release"])["platforms"])),
		"shared_context_words": legacyWordCount(sharedContext), "max_plan_words": legacyMaxInt(planWords),
		"max_execution_unit_words": legacyMaxInt(unitWords), "package_words": packageWords,
	}
	if profile == "lean" && metrics["plans"] > 4 {
		warnings = append(warnings, "perfil lean acima da faixa típica de 1–4 planos; 7 é teto, não meta")
	}
	exceeded := make([]string, 0)
	for key, limit := range limits {
		if metrics[key] > limit {
			exceeded = append(exceeded, key)
		}
	}
	sort.Strings(exceeded)
	recommended := legacyDeepRecommendedProfile(metrics, plans)
	if enforced {
		complexity, complexityOK := state["complexity_review"].(map[string]any)
		if !complexityOK {
			errors = append(errors, "complexity_review: revisão obrigatória ausente")
		} else {
			decision := stateString(complexity["decision"])
			justification := strings.TrimSpace(stateString(complexity["justification"]))
			deferred := stateStringSlice(complexity["deferred_scope"])
			splitApproved := stateBool(complexity["scope_split_approved"])
			splitBy := strings.TrimSpace(stateString(complexity["scope_split_approved_by"]))
			splitAt := stateString(complexity["scope_split_approved_at"])
			if len(deferred) > 0 {
				if decision != "split" {
					errors = append(errors, "complexity_review: deferred_scope exige decision split")
				}
				if !splitApproved || splitBy == "" || !legacySplitAt.MatchString(splitAt) {
					errors = append(errors, "complexity_review: escopo aprovado não pode ser adiado para caber no orçamento; split exige autorização explícita do responsável com autor e horário")
				}
			} else if decision == "split" {
				errors = append(errors, "complexity_review.deferred_scope: split exige escopo adiado autorizado")
			} else if splitApproved || splitBy != "" || splitAt != "" {
				errors = append(errors, "complexity_review: autorização de split não pode permanecer sem deferred_scope")
			}
			if legacyProfileRank(profile) < legacyProfileRank(recommended) {
				errors = append(errors, fmt.Sprintf("assurance_profile %s: insuficiente para risco/capacidade; preserve todo o escopo e escale para %s", profile, recommended))
			}
			if len(exceeded) > 0 {
				if profile == "full" && (!oneOf(decision, "indivisible", "split") || len([]rune(justification)) < 40) {
					errors = append(errors, "complexity_review: perfil full acima da faixa exige justificativa de indivisibilidade em 40+ caracteres; nunca reduza escopo automaticamente")
				}
			} else if !oneOf(decision, "within_budget", "split") {
				errors = append(errors, "complexity_review.decision: use within_budget ou split dentro do orçamento")
			}
		}
	}
	if len(errors) > 0 {
		return nil, fmt.Errorf("planejamento inválido:\n- %s", strings.Join(legacyOrderedUnique(errors), "\n- "))
	}
	contract := "legacy-compatible"
	if quality == 1 {
		contract = "planning-quality-v1"
	} else if qualityV2 {
		contract = "planning-quality-v2"
	}
	return map[string]any{
		"valid": true, "quality_contract": contract, "profile": profile,
		"recommended_profile": recommended, "research_mode": func() any {
			if researchMode == "" {
				return nil
			}
			return researchMode
		}(),
		"metrics": metrics, "limits": limits, "budget_exceeded": exceeded,
		"warnings": legacyUniqueSorted(warnings), "readiness": readinessSummary,
	}, nil
}

func legacyMaxInt(values []int) int {
	result := 0
	for _, value := range values {
		if value > result {
			result = value
		}
	}
	return result
}

func legacyDeepRecommendedProfile(metrics map[string]int, plans []any) string {
	capacity := "full"
	for _, profile := range []string{"lean", "standard", "full"} {
		fits := true
		for key, limit := range legacyPlanningLimits[profile] {
			if metrics[key] > limit {
				fits = false
			}
		}
		if fits {
			capacity = profile
			break
		}
	}
	dependencies := make(map[string][]string)
	critical := make(map[string]bool)
	riskProfile := "lean"
	for _, raw := range plans {
		plan := stateObject(raw)
		identifier := stateString(plan["id"])
		dependencies[identifier] = stateStringSlice(plan["depends_on"])
		risk := stateString(plan["risk"])
		if risk == "critical" {
			critical[identifier] = true
		}
		if oneOf(risk, "medium", "high", "critical") {
			riskProfile = "standard"
		}
	}
	if len(critical) > 1 {
		var dependsCritical func(string, map[string]bool) bool
		dependsCritical = func(identifier string, seen map[string]bool) bool {
			if seen[identifier] {
				return false
			}
			seen[identifier] = true
			for _, dependency := range dependencies[identifier] {
				if critical[dependency] || dependsCritical(dependency, seen) {
					return true
				}
			}
			return false
		}
		for identifier := range critical {
			if dependsCritical(identifier, map[string]bool{}) {
				riskProfile = "full"
				break
			}
		}
	}
	if legacyProfileRank(riskProfile) > legacyProfileRank(capacity) {
		return riskProfile
	}
	return capacity
}

func legacyDirectoryPath(root, value, label string, mustExist bool) (string, error) {
	if err := rejectForeignNamespace(value, label); err != nil {
		return "", err
	}
	if strings.Contains(filepath.ToSlash(value), "/../") || strings.HasSuffix(value, "/..") {
		return "", domainError("PATH_SAFETY", label+" contém traversal")
	}
	joined := value
	if !filepath.IsAbs(value) {
		joined = filepath.Join(root, value)
	}
	absolute, err := filepath.Abs(joined)
	if err != nil {
		return "", domainError("PATH_SAFETY", label+" inválido")
	}
	absolute = filepath.Clean(absolute)
	relative, err := filepath.Rel(root, absolute)
	if err != nil || relative == ".." || strings.HasPrefix(relative, ".."+string(filepath.Separator)) || filepath.IsAbs(relative) {
		return "", domainError("PATH_SAFETY", label+" fora da raiz")
	}
	probe := absolute
	for {
		info, statErr := os.Lstat(probe)
		if statErr == nil && info.Mode()&os.ModeSymlink != 0 {
			return "", domainError("PATH_SAFETY", label+" não aceita symlink")
		}
		if statErr != nil && !os.IsNotExist(statErr) {
			return "", domainError("PATH_SAFETY", label+" inválido")
		}
		if probe == root {
			break
		}
		parent := filepath.Dir(probe)
		if parent == probe {
			return "", domainError("PATH_SAFETY", label+" fora da raiz")
		}
		probe = parent
	}
	if mustExist {
		info, statErr := os.Lstat(absolute)
		if statErr != nil || !info.IsDir() || info.Mode()&os.ModeSymlink != 0 {
			return absolute, fmt.Errorf("%s: diretório ausente", label)
		}
	}
	return absolute, nil
}

func legacyDestinationPath(value string) string {
	return strings.TrimSpace(strings.SplitN(value, "#", 2)[0])
}

func legacyValidateReadiness(state map[string]any, root string, packageSet map[string]bool) (map[string]any, []string, []string) {
	errors := make([]string, 0)
	warnings := make([]string, 0)
	planning := stateObject(state["planning"])
	changeRootValue := stateString(planning["change_root"])
	changeRoot := ""
	if changeRootValue == "" {
		errors = append(errors, "planning.change_root: diretório canônico obrigatório")
	} else if value, err := legacyDirectoryPath(root, changeRootValue, "planning.change_root", true); err != nil {
		errors = append(errors, err.Error())
	} else {
		changeRoot = value
	}
	readinessValue := stateString(planning["readiness"])
	readinessPath, _, readinessErr := legacyPlanningText(root, readinessValue, "planning.readiness")
	if readinessErr != nil || readinessPath == "" {
		return map[string]any{}, []string{"planning.readiness: READINESS.md local é obrigatório"}, []string{}
	}
	readiness, err := legacyReadJSONDocument(readinessPath, "READINESS.md")
	if err != nil {
		return map[string]any{}, []string{err.Error()}, []string{}
	}
	if stateInt(readiness["schema_version"]) != 1 {
		errors = append(errors, "readiness.schema_version: esperado 1")
	}
	if stateString(readiness["status"]) != "ready" {
		errors = append(errors, "readiness.status: esperado ready antes dos planos")
	}
	scopeValue := stateString(stateObject(state["scope"])["source"])
	scopePath, scopeContent, scopeErr := legacyPlanningText(root, scopeValue, "scope.source")
	if scopeErr != nil || scopeContent == "" {
		errors = append(errors, "readiness.scope_digest: escopo local ausente")
	} else if digest, digestErr := legacyFileDigest(scopePath); digestErr != nil || stateString(readiness["scope_digest"]) != digest {
		errors = append(errors, "readiness.scope_digest: divergiu do escopo aprovado")
	}
	requireChangePath := func(path, label string) {
		if path == "" || changeRoot == "" {
			return
		}
		relative, relErr := filepath.Rel(changeRoot, path)
		if relErr != nil || relative == ".." || strings.HasPrefix(relative, ".."+string(filepath.Separator)) || filepath.IsAbs(relative) {
			errors = append(errors, label+": deve ficar dentro de planning.change_root")
		}
	}
	requireChangePath(scopePath, "scope.source")
	requireChangePath(readinessPath, "planning.readiness")
	declaredRevision := strings.TrimSpace(stateString(readiness["repository_revision"]))
	if declaredRevision == "" {
		errors = append(errors, "readiness.repository_revision: valor factual obrigatório")
	} else if stateString(stateObject(state["approval"])["status"]) != "approved" {
		currentRevision, revisionErr := legacyRepositoryRevision(root)
		if revisionErr != nil {
			errors = append(errors, revisionErr.Error())
		} else if declaredRevision != currentRevision {
			errors = append(errors, "readiness.repository_revision: repositório mudou após o gate de prontidão")
		}
	}
	designRequired, designRequiredOK := readiness["design_required"].(bool)
	if !designRequiredOK {
		errors = append(errors, "readiness.design_required: esperado boolean")
	}
	impact, impactOK := readiness["impact_map"].(map[string]any)
	if !impactOK {
		errors = append(errors, "readiness.impact_map: objeto obrigatório")
	} else {
		for _, key := range []string{"applications", "modules", "contracts", "data", "platforms"} {
			values, valuesOK := impact[key].([]any)
			if !valuesOK {
				// Programmatic callers can provide []string before serialization.
				if _, stringOK := impact[key].([]string); !stringOK {
					errors = append(errors, "readiness.impact_map."+key+": esperado lista de strings")
				}
				continue
			}
			for _, raw := range values {
				value, stringOK := raw.(string)
				if !stringOK || strings.TrimSpace(value) == "" {
					errors = append(errors, "readiness.impact_map."+key+": esperado lista de strings")
					break
				}
			}
		}
	}

	identifiers := make(map[string]bool)
	planIDs := make(map[string]bool)
	for _, raw := range stateArray(state["plans"]) {
		planIDs[stateString(stateObject(raw)["id"])] = true
	}
	packageContent := make(map[string]string)
	contentFor := func(pathValue string) string {
		if content, exists := packageContent[pathValue]; exists {
			return content
		}
		_, content, textErr := legacyPlanningText(root, pathValue, "readiness destination "+pathValue)
		if textErr != nil || content == "" {
			errors = append(errors, "readiness destination ausente ou vazio: "+pathValue)
			packageContent[pathValue] = ""
			return ""
		}
		packageContent[pathValue] = content
		return content
	}
	checkDestinations := func(item map[string]any, identifier string) {
		destinations := stateStringSlice(item["destinations"])
		if len(destinations) == 0 {
			errors = append(errors, "readiness "+identifier+": destinations não vazio é obrigatório")
			return
		}
		for _, raw := range destinations {
			pathValue := legacyDestinationPath(raw)
			if !packageSet[pathValue] {
				errors = append(errors, "readiness "+identifier+": destino fora do pacote aprovado: "+pathValue)
				continue
			}
			if !strings.Contains(contentFor(pathValue), identifier) {
				errors = append(errors, "readiness "+identifier+": ID ausente no destino "+pathValue)
			}
		}
	}
	collections := make(map[string][]map[string]any, len(legacyReadinessCollections))
	collectionNames := []string{"decisions", "assumptions", "pitfalls", "user_actions", "spikes", "design_surfaces", "spec_deltas"}
	for _, name := range collectionNames {
		values, ok := readiness[name].([]any)
		if !ok {
			errors = append(errors, "readiness."+name+": esperado lista")
			collections[name] = []map[string]any{}
			continue
		}
		collections[name] = make([]map[string]any, 0, len(values))
		for index, raw := range values {
			item, itemOK := raw.(map[string]any)
			if !itemOK {
				errors = append(errors, fmt.Sprintf("readiness.%s[%d]: esperado objeto", name, index))
				continue
			}
			identifier := stateString(item["id"])
			if !legacyReadinessCollections[name].MatchString(identifier) {
				errors = append(errors, fmt.Sprintf("readiness.%s[%d].id: formato inválido", name, index))
				continue
			}
			if identifiers[identifier] {
				errors = append(errors, "readiness: ID duplicado "+identifier)
			}
			identifiers[identifier] = true
			collections[name] = append(collections[name], item)
			checkDestinations(item, identifier)
		}
	}
	for _, item := range collections["decisions"] {
		identifier := stateString(item["id"])
		if strings.TrimSpace(stateString(item["statement"])) == "" {
			errors = append(errors, "readiness "+identifier+": statement obrigatório")
		}
		if strings.TrimSpace(stateString(item["evidence"])) == "" {
			errors = append(errors, "readiness "+identifier+": evidence obrigatório")
		}
	}
	for _, item := range collections["assumptions"] {
		identifier := stateString(item["id"])
		impactValue := stateString(item["impact"])
		status := stateString(item["status"])
		if !oneOf(impactValue, "low", "medium", "high", "critical") {
			errors = append(errors, "readiness "+identifier+": impact inválido")
		}
		if !oneOf(status, "confirmed", "bounded", "not_applicable") {
			errors = append(errors, "readiness "+identifier+": suposição ainda não resolvida")
		}
		if oneOf(impactValue, "high", "critical") && strings.TrimSpace(stateString(item["evidence"])) == "" {
			errors = append(errors, "readiness "+identifier+": evidência obrigatória para alto impacto")
		}
		if status == "bounded" && strings.TrimSpace(stateString(item["fallback"])) == "" {
			errors = append(errors, "readiness "+identifier+": fallback obrigatório quando bounded")
		}
	}
	for _, item := range collections["pitfalls"] {
		identifier := stateString(item["id"])
		impactValue := stateString(item["impact"])
		if !oneOf(impactValue, "low", "medium", "high", "critical") {
			errors = append(errors, "readiness "+identifier+": impact inválido")
		}
		if oneOf(impactValue, "high", "critical") {
			for _, field := range []string{"prevention", "recovery", "verification"} {
				if strings.TrimSpace(stateString(item[field])) == "" {
					errors = append(errors, "readiness "+identifier+": "+field+" obrigatório")
				}
			}
		}
	}
	userActionsValue := stateString(planning["user_actions"])
	userActionsPath, userActionsContent, userActionsErr := legacyPlanningText(root, userActionsValue, "planning.user_actions")
	if userActionsErr != nil || userActionsContent == "" {
		errors = append(errors, "planning.user_actions: USER_ACTIONS.md local é obrigatório")
	}
	requireChangePath(userActionsPath, "planning.user_actions")
	for _, field := range []string{"research", "spec", "review"} {
		path, _, _ := legacyPlanningText(root, stateString(planning[field]), "planning."+field)
		requireChangePath(path, "planning."+field)
	}
	for _, raw := range stateArray(state["plans"]) {
		plan := stateObject(raw)
		path, _, _ := legacyPlanningText(root, stateString(plan["path"]), "plan "+stateString(plan["id"]))
		requireChangePath(path, "plan "+stateString(plan["id"]))
	}
	for _, item := range collections["user_actions"] {
		identifier := stateString(item["id"])
		if !planIDs[stateString(item["needed_by"])] {
			errors = append(errors, "readiness "+identifier+": needed_by deve apontar plano existente")
		}
		if _, ok := item["can_continue_without"].(bool); !ok {
			errors = append(errors, "readiness "+identifier+": can_continue_without deve ser boolean")
		}
		if stateBool(item["can_continue_without"]) && strings.TrimSpace(stateString(item["fallback"])) == "" {
			errors = append(errors, "readiness "+identifier+": fallback obrigatório")
		}
		if strings.TrimSpace(stateString(item["evidence_required"])) == "" {
			errors = append(errors, "readiness "+identifier+": evidence_required obrigatório")
		}
		if !strings.Contains(userActionsContent, identifier) {
			errors = append(errors, "planning.user_actions: ação "+identifier+" ausente")
		}
	}
	for _, item := range collections["spikes"] {
		identifier := stateString(item["id"])
		status := stateString(item["status"])
		if !oneOf(status, "passed", "failed", "not_needed") {
			errors = append(errors, "readiness "+identifier+": spike deve estar encerrado")
		}
		if status == "passed" {
			if strings.TrimSpace(stateString(item["evidence"])) == "" {
				errors = append(errors, "readiness "+identifier+": evidence obrigatório")
			}
			if strings.TrimSpace(stateString(item["decision"])) == "" {
				errors = append(errors, "readiness "+identifier+": decision obrigatória")
			}
		}
		if status == "failed" {
			errors = append(errors, "readiness "+identifier+": spike falhou e bloqueia o plano")
		}
	}

	designManifest := stateString(planning["design_manifest"])
	var designSummary any
	if designRequired {
		if designManifest == "" {
			errors = append(errors, "planning.design_manifest: design obrigatório sem manifesto aprovado")
		}
		if len(collections["design_surfaces"]) == 0 {
			errors = append(errors, "readiness.design_surfaces: UI obrigatória sem superfície DS")
		}
	}
	if designManifest != "" {
		if !packageSet[designManifest] {
			errors = append(errors, "planning.design_manifest: manifesto ausente do pacote")
		} else if scopePath != "" {
			summary, designErr := legacyDesignAudit(root, scopePath, designManifest, false)
			if designErr != nil {
				errors = append(errors, designErr.Error())
			} else {
				designSummary = summary
				for _, file := range stateStringSlice(summary["files"]) {
					if !packageSet[file] {
						errors = append(errors, "planning.design_manifest: arquivo de design fora do pacote: "+file)
					}
				}
			}
		}
	}
	for _, item := range collections["design_surfaces"] {
		identifier := stateString(item["id"])
		if item["required"] != true {
			warnings = append(warnings, "readiness "+identifier+": superfície opcional não deve ampliar escopo")
		}
		if stateString(item["manifest_ref"]) != designManifest {
			errors = append(errors, "readiness "+identifier+": manifest_ref diverge do estado")
		}
	}
	currentSpecsValue := stateString(planning["current_specs"])
	currentSpecsRoot := ""
	if currentSpecsValue == "" {
		errors = append(errors, "planning.current_specs: diretório canônico obrigatório")
	} else if value, pathErr := legacyDirectoryPath(root, currentSpecsValue, "planning.current_specs", false); pathErr != nil {
		errors = append(errors, pathErr.Error())
	} else {
		currentSpecsRoot = value
	}
	if len(collections["spec_deltas"]) == 0 {
		warnings = append(warnings, "readiness.spec_deltas vazio: ciclo não altera comportamento persistido nas specs atuais")
	}
	specDeltas := make([]map[string]string, 0)
	specSources := make(map[string]bool)
	specTargets := make(map[string]bool)
	for _, item := range collections["spec_deltas"] {
		identifier := stateString(item["id"])
		source := stateString(item["source"])
		target := stateString(item["target"])
		if source == "" || !packageSet[source] {
			errors = append(errors, "readiness "+identifier+": source deve constar no pacote")
			continue
		}
		if target == "" {
			errors = append(errors, "readiness "+identifier+": target obrigatório")
			continue
		}
		if specSources[source] {
			errors = append(errors, "readiness "+identifier+": source duplicado em spec_deltas")
		}
		if specTargets[target] {
			errors = append(errors, "readiness "+identifier+": target duplicado em spec_deltas")
		}
		specSources[source] = true
		specTargets[target] = true
		sourcePath, sourceContent, sourceErr := legacyPlanningText(root, source, "readiness "+identifier+".source")
		requireChangePath(sourcePath, "readiness "+identifier+".source")
		if sourceErr != nil || sourceContent == "" {
			errors = append(errors, "readiness "+identifier+": source ausente ou vazio")
		} else if !strings.Contains(sourceContent, identifier) {
			errors = append(errors, "readiness "+identifier+": ID ausente no source")
		}
		targetPath, targetErr := confinedPath(root, target, "readiness "+identifier+".target", false)
		if targetErr != nil {
			errors = append(errors, targetErr.Error())
		} else if currentSpecsRoot != "" {
			relative, relErr := filepath.Rel(currentSpecsRoot, targetPath)
			if relErr != nil || relative == ".." || strings.HasPrefix(relative, ".."+string(filepath.Separator)) || filepath.IsAbs(relative) {
				errors = append(errors, "readiness "+identifier+": target fora de current_specs")
			}
			if info, statErr := os.Lstat(targetPath); statErr == nil && info.Mode().IsRegular() && !packageSet[target] {
				errors = append(errors, "readiness "+identifier+": spec atual existente deve constar no pacote")
			}
		}
		specDeltas = append(specDeltas, map[string]string{"id": identifier, "source": source, "target": target})
	}
	counts := make(map[string]int, len(collections))
	for _, name := range collectionNames {
		counts[name] = len(collections[name])
	}
	coverage := legacyUniqueSorted(errors)
	return map[string]any{
		"status": readiness["status"], "scope_digest": readiness["scope_digest"],
		"design_required": designRequired, "design": designSummary, "counts": counts,
		"coverage_gaps": coverage, "spec_deltas": specDeltas,
	}, errors, warnings
}

func legacyRepositoryRevision(root string) (string, error) {
	top, err := legacyGitOutput(root, "rev-parse", "--show-toplevel")
	if err != nil {
		return "new-project", nil
	}
	resolvedRoot, rootErr := filepath.EvalSymlinks(root)
	resolvedTop, topErr := filepath.EvalSymlinks(top)
	if rootErr != nil || topErr != nil || filepath.Clean(resolvedRoot) != filepath.Clean(resolvedTop) {
		return "", fmt.Errorf("readiness: --root deve apontar para a raiz Git")
	}
	head, err := legacyGitOutput(root, "rev-parse", "HEAD")
	if err != nil {
		return "unborn", nil
	}
	return head, nil
}

func legacyReadinessIndex(readiness map[string]any) map[string]map[string]any {
	result := make(map[string]map[string]any)
	for _, collection := range []string{"decisions", "assumptions", "pitfalls", "user_actions", "spikes", "design_surfaces", "spec_deltas"} {
		for _, raw := range stateArray(readiness[collection]) {
			item := stateObject(raw)
			identifier := stateString(item["id"])
			if identifier != "" {
				copy := make(map[string]any, len(item)+1)
				for key, value := range item {
					copy[key] = value
				}
				copy["collection"] = collection
				result[identifier] = copy
			}
		}
	}
	return result
}

func legacyParseCommaValues(value string) []string {
	result := make([]string, 0)
	seen := make(map[string]bool)
	for _, raw := range strings.Split(value, ",") {
		item := strings.TrimSpace(raw)
		if item != "" && !seen[item] {
			seen[item] = true
			result = append(result, item)
		}
	}
	return result
}

func legacyRawCommaValues(value string) []string {
	result := make([]string, 0)
	for _, raw := range strings.Split(value, ",") {
		if item := strings.TrimSpace(raw); item != "" {
			result = append(result, item)
		}
	}
	return result
}

func legacyValidateQualityV2Plan(planPath, content string, readiness map[string]any) []string {
	errors := make([]string, 0)
	index := legacyReadinessIndex(readiness)
	referenced := make(map[string]bool)
	for _, section := range legacyUnitSections(content) {
		change := legacyUnitField(section.content, "Change")
		if change == "" {
			errors = append(errors, fmt.Sprintf("plano %s / %s: campo Change ausente", planPath, section.heading))
		} else if !legacyQualityV2Changes[change] {
			errors = append(errors, fmt.Sprintf("plano %s / %s: Change inválido %q; use categoria factual suportada por bm.py policy", planPath, section.heading, change))
		}
		rawRefs := legacyUnitField(section.content, "Readiness refs")
		if rawRefs == "" {
			errors = append(errors, fmt.Sprintf("plano %s / %s: campo Readiness refs ausente", planPath, section.heading))
			continue
		}
		refs := legacyRawCommaValues(rawRefs)
		if len(refs) == 0 {
			errors = append(errors, fmt.Sprintf("plano %s / %s: Readiness refs vazio", planPath, section.heading))
			continue
		}
		if len(legacyStableStrings(refs)) != len(refs) {
			errors = append(errors, fmt.Sprintf("plano %s / %s: Readiness refs contém duplicatas", planPath, section.heading))
		}
		for _, identifier := range refs {
			if !legacyReadinessID.MatchString(identifier) {
				errors = append(errors, fmt.Sprintf("plano %s / %s: readiness ref inválida %q", planPath, section.heading, identifier))
				continue
			}
			item := index[identifier]
			if item == nil {
				errors = append(errors, fmt.Sprintf("plano %s / %s: readiness ref inexistente %s", planPath, section.heading, identifier))
				continue
			}
			allowed := false
			for _, destination := range stateStringSlice(item["destinations"]) {
				if legacyDestinationPath(destination) == planPath {
					allowed = true
				}
			}
			if !allowed {
				errors = append(errors, fmt.Sprintf("plano %s / %s: readiness ref %s não declara este plano em destinations", planPath, section.heading, identifier))
				continue
			}
			referenced[identifier] = true
		}
	}
	expected := make([]string, 0)
	for identifier, item := range index {
		for _, destination := range stateStringSlice(item["destinations"]) {
			if legacyDestinationPath(destination) == planPath && !referenced[identifier] {
				expected = append(expected, identifier)
				break
			}
		}
	}
	sort.Strings(expected)
	if len(expected) > 0 {
		errors = append(errors, "plano "+planPath+": readiness refs destinadas ao plano não foram ligadas a nenhuma unidade: "+strings.Join(expected, ", "))
	}
	return errors
}

func legacyHydrateTaskContext(rootValue, stateValue, planPath string, labels, sections []string, ledgerTail int) (string, string, error) {
	root, err := safeRoot(rootValue)
	if err != nil {
		return "", "", err
	}
	statePath, err := confinedPath(root, stateValue, "state", true)
	if err != nil {
		return "", "", err
	}
	state, err := validateStateFile(statePath, "")
	if err != nil {
		return "", "", err
	}
	planning := stateObject(state["planning"])
	if stateInt(state["method_version"]) != 2 {
		return "", "", fmt.Errorf("contexto hidratado exige PROJECT_STATE v2")
	}
	if stateInt(planning["quality_version"]) != 2 {
		return "", "", fmt.Errorf("contexto hidratado exige planning.quality_version 2")
	}
	confinedPlan, err := confinedPath(root, planPath, "plan", true)
	if err != nil {
		return "", "", err
	}
	planRelative, err := legacyRelative(root, confinedPlan)
	if err != nil {
		return "", "", err
	}
	var plan map[string]any
	for _, raw := range stateArray(state["plans"]) {
		item := stateObject(raw)
		if stateString(item["path"]) == planRelative {
			plan = item
			break
		}
	}
	if plan == nil {
		return "", "", fmt.Errorf("plan não pertence ao PROJECT_STATE informado")
	}
	readinessPath, err := confinedPath(root, stateString(planning["readiness"]), "planning.readiness", true)
	if err != nil {
		return "", "", err
	}
	readiness, err := legacyReadJSONDocument(readinessPath, "READINESS.md")
	if err != nil {
		return "", "", err
	}
	planBytes, err := os.ReadFile(confinedPlan)
	if err != nil || !validUTF8Text(planBytes) {
		return "", "", fmt.Errorf("plan deve ser UTF-8 textual")
	}
	if validationErrors := legacyValidateQualityV2Plan(planRelative, string(planBytes), readiness); len(validationErrors) > 0 {
		return "", "", fmt.Errorf("contexto não pode ser hidratado:\n- %s", strings.Join(validationErrors, "\n- "))
	}
	selectedRefs := make([]string, 0)
	specRefs := make([]string, 0)
	changes := make([]string, 0)
	for _, section := range sections {
		selectedRefs = append(selectedRefs, legacyParseCommaValues(legacyUnitField(section, "Readiness refs"))...)
		specRefs = append(specRefs, legacyParseCommaValues(legacyUnitField(section, "Spec refs"))...)
		if change := legacyUnitField(section, "Change"); change != "" {
			changes = append(changes, change)
		}
	}
	selectedRefs = legacyStableStrings(selectedRefs)
	specRefs = legacyStableStrings(specRefs)
	index := legacyReadinessIndex(readiness)
	selectedItems := make([]map[string]any, 0, len(selectedRefs))
	for _, identifier := range selectedRefs {
		item := index[identifier]
		if item == nil {
			return "", "", fmt.Errorf("readiness ref inexistente: %s", identifier)
		}
		selectedItems = append(selectedItems, item)
	}
	changeRoot, err := legacyDirectoryPath(root, stateString(planning["change_root"]), "planning.change_root", true)
	if err != nil {
		return "", "", err
	}
	type resolvedSpec struct{ label, content string }
	resolved := make([]resolvedSpec, 0, len(specRefs))
	for _, raw := range specRefs {
		label, content, resolveErr := legacyResolveSpecRef(root, changeRoot, raw)
		if resolveErr != nil {
			return "", "", resolveErr
		}
		resolved = append(resolved, resolvedSpec{label: label, content: content})
	}
	ledgerLines := make([]string, 0)
	if ledger := stateString(plan["ledger"]); ledger != "" {
		ledgerPath, pathErr := confinedPath(root, ledger, "plan.ledger", true)
		if pathErr == nil {
			data, readErr := os.ReadFile(ledgerPath)
			if readErr == nil {
				all := strings.Split(strings.TrimRight(string(data), "\r\n"), "\n")
				if ledgerTail == 0 {
					all = nil
				} else if len(all) > ledgerTail {
					all = all[len(all)-ledgerTail:]
				}
				ledgerLines = all
			}
		}
	}
	var active any
	if activeValue, ok := state["active_execution"].(map[string]any); ok && stateString(activeValue["plan_id"]) == stateString(plan["id"]) {
		active = activeValue
	}
	profile := stateString(state["assurance_profile"])
	maxFix := map[string]int{"lean": 2, "standard": 3, "full": 5}[profile]
	resolvedLabels := make([]string, 0, len(resolved))
	for _, item := range resolved {
		resolvedLabels = append(resolvedLabels, item.label)
	}
	metadata := map[string]any{
		"schema_version": 1, "planning_version": state["planning_version"],
		"package_digest": stateObject(stateObject(state["approval"])["package"])["manifest_digest"],
		"plan_id":        plan["id"], "plan_path": planRelative, "profile": profile,
		"risk": plan["risk"], "execution": plan["execution"], "review": plan["review"],
		"test_seams": plan["test_seams"], "max_fix_rounds": maxFix, "units": labels,
		"changes": changes, "readiness_refs": selectedRefs, "spec_refs": resolvedLabels,
		"verification_fast": stateObject(stateObject(state["verification"])["fast"])["commands"],
		"active_execution":  active, "ledger_tail_lines": len(ledgerLines),
	}
	metadataJSON, _ := legacySortedIndentedJSON(metadata)
	readinessJSON, _ := legacySortedIndentedJSON(selectedItems)
	var chunks strings.Builder
	chunks.WriteString("## Contexto hidratado\n\n```json\n")
	chunks.WriteString(metadataJSON)
	chunks.WriteString("\n```\n\n### Readiness aplicável\n\n```json\n")
	chunks.WriteString(readinessJSON)
	chunks.WriteString("\n```\n\n### Specs aplicáveis")
	for _, item := range resolved {
		chunks.WriteString("\n\n#### `" + item.label + "`\n\n" + item.content)
	}
	chunks.WriteString("\n\n### Verification.fast\n\n")
	commands := stateStringSlice(metadata["verification_fast"])
	if len(commands) == 0 {
		chunks.WriteString("- Nenhum comando configurado.")
	} else {
		for index, command := range commands {
			if index > 0 {
				chunks.WriteByte('\n')
			}
			chunks.WriteString("- `" + command + "`")
		}
	}
	chunks.WriteString("\n\n### Último estado operacional\n\n")
	if len(ledgerLines) == 0 {
		chunks.WriteString("Nenhum ledger registrado para o plano.")
	} else {
		chunks.WriteString("```text\n" + strings.Join(ledgerLines, "\n") + "\n```")
	}
	rendered := strings.TrimRight(chunks.String(), "\n") + "\n"
	return rendered, sha256Bytes([]byte(rendered)), nil
}

func legacyStableStrings(values []string) []string {
	seen := make(map[string]bool)
	result := make([]string, 0, len(values))
	for _, value := range values {
		if value != "" && !seen[value] {
			seen[value] = true
			result = append(result, value)
		}
	}
	return result
}

func legacyResolveSpecRef(root, changeRoot, raw string) (string, string, error) {
	parts := strings.SplitN(strings.TrimSpace(raw), "#", 2)
	if len(parts) != 2 || strings.TrimSpace(parts[0]) == "" || strings.TrimSpace(parts[1]) == "" {
		return "", "", fmt.Errorf("spec ref hidratada exige seção #anchor: %s", raw)
	}
	pathValue := strings.TrimSpace(parts[0])
	anchor := strings.TrimSpace(parts[1])
	candidate := pathValue
	if first := strings.Split(filepath.ToSlash(pathValue), "/")[0]; first != "docs" {
		candidate = filepath.Join(changeRoot, filepath.FromSlash(pathValue))
	}
	path, err := confinedPath(root, candidate, "spec ref", true)
	if err != nil {
		return "", "", fmt.Errorf("spec ref ausente: %s", raw)
	}
	data, err := os.ReadFile(path)
	if err != nil || !validUTF8Text(data) {
		return "", "", fmt.Errorf("spec ref ausente: %s", raw)
	}
	relative, _ := legacyRelative(root, path)
	section, err := legacyMarkdownSection(string(data), anchor, relative)
	if err != nil {
		return "", "", err
	}
	return relative + "#" + anchor, section, nil
}

func legacySlugHeading(value string) string {
	decomposed := norm.NFKD.String(value)
	var result strings.Builder
	separator := false
	for _, character := range strings.ToLower(strings.TrimSpace(decomposed)) {
		if unicode.Is(unicode.Mn, character) {
			continue
		}
		if unicode.IsLetter(character) || unicode.IsDigit(character) {
			if separator && result.Len() > 0 {
				result.WriteByte('-')
			}
			separator = false
			result.WriteRune(character)
		} else {
			separator = true
		}
	}
	return strings.Trim(result.String(), "-")
}

func legacyMarkdownSection(content, anchor, label string) (string, error) {
	headings := regexp.MustCompile(`(?m)^(#{1,6})\s+([^\n]+)$`).FindAllStringSubmatchIndex(content, -1)
	for index, match := range headings {
		title := content[match[4]:match[5]]
		if legacySlugHeading(title) != anchor {
			continue
		}
		level := match[3] - match[2]
		end := len(content)
		for _, following := range headings[index+1:] {
			followingLevel := following[3] - following[2]
			if followingLevel <= level {
				end = following[0]
				break
			}
		}
		return strings.TrimSpace(content[match[0]:end]), nil
	}
	return "", fmt.Errorf("spec ref não encontrada: %s#%s", label, anchor)
}

func legacySortedIndentedJSON(value any) (string, error) {
	var buffer strings.Builder
	encoder := json.NewEncoder(&buffer)
	encoder.SetEscapeHTML(false)
	encoder.SetIndent("", "  ")
	if err := encoder.Encode(value); err != nil {
		return "", err
	}
	return strings.TrimSuffix(buffer.String(), "\n"), nil
}
