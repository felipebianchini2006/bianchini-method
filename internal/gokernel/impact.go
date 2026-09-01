package gokernel

import (
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

func runImpact(args []string) (any, error) {
	if len(args) == 0 {
		return nil, argparseError("the following arguments are required: action")
	}
	if args[0] != "analyze" {
		return nil, argparseError(fmt.Sprintf("argument action: invalid choice: '%s'", args[0]))
	}
	flags, err := parseFlags(args[1:], map[string]bool{
		"--repo": true, "--change": true, "--plan": true,
		"--changed-contract": true, "--changed-ownership": true,
		"--changed-interface": true, "--changed-data": true,
		"--changed-migration": true, "--changed-journey": true,
		"--changed-effect": true, "--changed-invariant": true,
	}, map[string]bool{"--global-change": true})
	if err != nil {
		return nil, err
	}
	change, plan := lastValue(flags, "--change"), lastValue(flags, "--plan")
	if change == "" || plan == "" {
		missing := "--change"
		if change != "" {
			missing = "--plan"
		}
		return nil, argparseError("the following arguments are required: " + missing)
	}
	repo := lastValue(flags, "--repo")
	if repo == "" {
		repo, err = os.Getwd()
		if err != nil {
			return nil, err
		}
	}
	return impactAnalyze(repo, change, plan, flags)
}

func impactAnalyze(repo, change, changedPlan string, flags parsedFlags) (map[string]any, error) {
	pack, err := loadCoherencePackage(repo, change)
	if err != nil {
		return nil, err
	}
	result, err := projectImpact(pack.plans, pack.expected, changedPlan, flags)
	if err != nil {
		return nil, workflowError("IMPACT_STALE", err.Error())
	}
	payload := pack.contract
	status := stateString(payload["status"])
	if oneOf(status, "approved", "approved_with_stale") {
		if err := coherenceAssertCurrent(pack, payload); err != nil {
			return nil, err
		}
	} else if pack.specContract != 0 {
		if _, err := loadModelSpecPackage(pack.workspace, pack.directory, payload); err != nil {
			return nil, err
		}
	}
	preview := status != "approved"
	result["preview"] = preview
	payload["impact"] = result
	stale := stateStringSlice(result["stale_plans"])
	if preview {
		payload["stale_plans"] = []any{}
	} else {
		payload["stale_plans"] = stringSliceAny(stale)
		if len(stale) > 0 {
			payload["status"] = "approved_with_stale"
		}
	}
	payload["updated_at"] = utcNow()
	if preview {
		copy := cloneMap(payload)
		delete(copy, "digest")
		payload["digest"] = waveStableDigest(copy)
	}
	mode := "invalidation"
	if preview {
		mode = "preview"
	}
	body := "# Coerência\n\nStatus: " + stateString(payload["status"]) + ".\n\n## Impact Radius\n\n" +
		"- Modo: " + mode + "\n" +
		"- Classificação: " + stateString(result["radius"]) + "\n" +
		"- Plano alterado: " + stateString(result["changed_plan"]) + "\n" +
		"- Diretos: " + impactJoined(stateStringSlice(result["direct_plans"]), "nenhum") + "\n" +
		"- Transitivos: " + impactJoined(stateStringSlice(result["transitive_plans"]), "nenhum") + "\n" +
		"- Stale: " + impactJoined(stale, "nenhum") + "\n" +
		"- Journeys: " + impactJoined(stateStringSlice(result["affected_journeys"]), "nenhuma") + "\n" +
		"- Verificações: " + impactJoined(stateStringSlice(result["verifications"]), "nenhuma")
	document, _ := frontmatterDocument(payload, body, false)
	if err := pack.workspace.atomicWrite(filepath.Join(pack.directory, "COHERENCE.md"), document); err != nil {
		return nil, err
	}
	state, err := pack.workspace.readState()
	if err != nil {
		return nil, err
	}
	state["current_unit"] = changedPlan
	if !preview && len(stale) > 0 {
		state["status"], state["blockers"] = "approved_with_stale", []any{"IMPACT_STALE"}
		state["next_action"] = "Replanejar e revalidar planos stale: " + strings.Join(stale, ", ")
	} else if preview {
		state["next_action"] = "Revisar o raio potencial antes da aprovação global."
	} else {
		state["next_action"] = "Continuar " + changedPlan + "; nenhuma fase posterior foi invalidada."
	}
	state["digest"], state["updated_at"] = payload["digest"], utcNow()
	if err := pack.workspace.writeState(state, "# Estado atual"); err != nil {
		return nil, err
	}
	return result, nil
}

func projectImpact(plans []planContract, model projectModel, changedPlan string, flags parsedFlags) (map[string]any, error) {
	position, byID := map[string]int{}, map[string]planContract{}
	for index, plan := range plans {
		position[plan.id] = index
		if _, exists := byID[plan.id]; !exists {
			byID[plan.id] = plan
		}
	}
	if _, exists := byID[changedPlan]; !exists {
		return nil, fmt.Errorf("plano desconhecido: %s", changedPlan)
	}
	dependencies, _ := coherencePlanDependencies(plans)
	directDependents := func(identifier string) map[string]bool {
		result := map[string]bool{}
		for candidate, values := range dependencies {
			if containsString(values, identifier) {
				result[candidate] = true
			}
		}
		return result
	}
	transitive := func(roots map[string]bool) map[string]bool {
		visited, frontier := map[string]bool{}, cloneBoolSet(roots)
		for len(frontier) > 0 {
			next := map[string]bool{}
			for identifier := range frontier {
				for dependent := range directDependents(identifier) {
					if !roots[dependent] && !visited[dependent] {
						next[dependent], visited[dependent] = true, true
					}
				}
			}
			frontier = next
		}
		return visited
	}
	contracts := stringSet(flags.values["--changed-contract"])
	resources := map[string]bool{}
	for _, flag := range []string{"--changed-ownership", "--changed-interface", "--changed-data", "--changed-migration", "--changed-effect"} {
		for _, value := range flags.values[flag] {
			resources[value] = true
		}
	}
	journeys, invariants := stringSet(flags.values["--changed-journey"]), stringSet(flags.values["--changed-invariant"])
	direct := map[string]bool{}
	for _, plan := range plans {
		if plan.id == changedPlan || position[plan.id] <= position[changedPlan] {
			continue
		}
		for _, contract := range normalizedPlanStrings(plan, "consumes") {
			if contracts[contract] {
				direct[plan.id] = true
			}
		}
		if setsIntersect(resources, coherencePlanResources(plan)) {
			direct[plan.id] = true
		}
	}
	if len(contracts) == 0 && len(resources) == 0 && len(journeys) == 0 {
		for identifier := range directDependents(changedPlan) {
			direct[identifier] = true
		}
	}
	downstream := transitive(direct)
	delete(downstream, changedPlan)
	for identifier := range direct {
		delete(downstream, identifier)
	}
	radius := "local"
	if flags.booleans["--global-change"] || len(invariants) > 0 {
		direct = directDependents(changedPlan)
		all := transitive(map[string]bool{changedPlan: true})
		downstream = all
		for identifier := range direct {
			delete(downstream, identifier)
		}
		radius = "global"
	} else if len(downstream) > 0 {
		radius = "transitive"
	} else if len(direct) > 0 {
		radius = "direct"
	}
	stale := cloneBoolSet(direct)
	for identifier := range downstream {
		stale[identifier] = true
	}
	affected := cloneBoolSet(journeys)
	changed := cloneBoolSet(contracts)
	for value := range resources {
		changed[value] = true
	}
	for value := range invariants {
		changed[value] = true
	}
	for identifier, journey := range model.sections["journeys"] {
		for _, raw := range stateArray(journey["path"]) {
			if changed[stateString(raw)] {
				affected[identifier] = true
			}
		}
	}
	verifications := map[string]bool{}
	for identifier := range stale {
		for _, verification := range normalizedPlanStrings(byID[identifier], "verifications") {
			verifications[verification] = true
		}
	}
	for _, verification := range normalizedPlanStrings(byID[changedPlan], "verifications") {
		verifications[verification] = true
	}
	return map[string]any{
		"radius": radius, "changed_plan": changedPlan,
		"direct_plans":      stringSliceAny(impactOrdered(direct, position)),
		"transitive_plans":  stringSliceAny(impactOrdered(downstream, position)),
		"stale_plans":       stringSliceAny(impactOrdered(stale, position)),
		"affected_journeys": stringSliceAny(sortedBoolSet(affected)),
		"verifications":     stringSliceAny(sortedBoolSet(verifications)),
	}, nil
}

func coherenceAssertCurrent(pack coherencePackage, payload map[string]any) error {
	if pack.planningContract < 2 {
		return nil
	}
	findings, findingsOK := payload["findings"].([]any)
	semantic, semanticOK := payload["semantic"].(map[string]any)
	if !findingsOK || !semanticOK {
		return workflowError("COHERENCE_ERROR", "pacote aprovado está incompleto")
	}
	manifest, err := coherenceArtifactManifest(pack.workspace, pack.directory)
	if err != nil {
		return err
	}
	spec, err := loadModelSpecPackage(pack.workspace, pack.directory, payload)
	if err != nil {
		return err
	}
	if !coherenceManifestEqual(payload["artifact_manifest"], manifest) || stateString(payload["review_input_digest"]) != coherenceReviewDigest(pack.planningContract, manifest, spec) || stateString(payload["digest"]) != coherencePackageDigest(pack.current, pack.expected, pack.plans, findings, semantic, pack.planningContract, manifest, spec) {
		return workflowError("STALE_EVIDENCE", "pacote aprovado mudou depois do checkpoint")
	}
	for key, value := range spec {
		if key == "spec_contract" {
			if stateInt(payload[key]) != stateInt(value) {
				return workflowError("STALE_EVIDENCE", "pacote aprovado mudou depois do checkpoint")
			}
		} else if stateString(payload[key]) != stateString(value) {
			return workflowError("STALE_EVIDENCE", "pacote aprovado mudou depois do checkpoint")
		}
	}
	return nil
}

func coherencePlanResources(plan planContract) map[string]bool {
	result := map[string]bool{}
	for _, field := range []string{"provides", "consumes", "touches", "modules", "interfaces", "data"} {
		for _, value := range normalizedPlanStrings(plan, field) {
			result[value] = true
		}
	}
	for _, value := range coherencePlanOwns(plan) {
		result[value] = true
	}
	for _, field := range []string{"migrations", "effects"} {
		for _, item := range coherencePlanObjects(plan, field) {
			if identifier := stateString(item["id"]); identifier != "" {
				result[identifier] = true
			}
		}
	}
	for _, rawOperations := range plan.modelDelta {
		operations, ok := rawOperations.(map[string]any)
		if !ok {
			for _, raw := range stateArray(rawOperations) {
				if identifier := impactDeltaID(raw); identifier != "" {
					result[identifier] = true
				}
			}
			continue
		}
		for _, operation := range []string{"add", "update", "upsert", "remove"} {
			for _, raw := range stateArray(operations[operation]) {
				if identifier := impactDeltaID(raw); identifier != "" {
					result[identifier] = true
				}
			}
		}
	}
	return result
}

func impactDeltaID(raw any) string {
	if item, ok := raw.(map[string]any); ok {
		return stateString(item["id"])
	}
	return stateString(raw)
}

func impactOrdered(values map[string]bool, position map[string]int) []string {
	result := sortedBoolSet(values)
	sort.Slice(result, func(left, right int) bool {
		if position[result[left]] == position[result[right]] {
			return result[left] < result[right]
		}
		return position[result[left]] < position[result[right]]
	})
	return result
}

func sortedBoolSet(values map[string]bool) []string {
	result := make([]string, 0, len(values))
	for value := range values {
		result = append(result, value)
	}
	sort.Strings(result)
	return result
}

func cloneBoolSet(values map[string]bool) map[string]bool {
	result := map[string]bool{}
	for value := range values {
		result[value] = true
	}
	return result
}

func setsIntersect(left, right map[string]bool) bool {
	for value := range left {
		if right[value] {
			return true
		}
	}
	return false
}

func impactJoined(values []string, empty string) string {
	if len(values) == 0 {
		return empty
	}
	return strings.Join(values, ", ")
}
