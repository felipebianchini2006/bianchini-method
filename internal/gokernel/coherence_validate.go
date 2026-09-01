package gokernel

import (
	"encoding/json"
	"fmt"
	"sort"
	"strings"
)

func coherenceStructuralFindings(current, expected projectModel, plans []planContract, requirements []string, typed bool) []any {
	findings := []any{}
	order, counts, known := map[string]int{}, map[string]int{}, map[string]bool{}
	for index, plan := range plans {
		order[plan.id], counts[plan.id], known[plan.id] = index, counts[plan.id]+1, true
	}
	identifiers := make([]string, 0, len(counts))
	for identifier := range counts {
		identifiers = append(identifiers, identifier)
	}
	sort.Strings(identifiers)
	for _, identifier := range identifiers {
		if !wavePlanID.MatchString(identifier) {
			findings = append(findings, coherenceFinding("INVALID_PLAN_ID", "ERROR", "structural", []string{identifier}, nil, "ID de plano inválido: "+identifier, "Usar P seguido por ao menos dois dígitos."))
		}
		if counts[identifier] > 1 {
			findings = append(findings, coherenceFinding("DUPLICATE_PLAN_ID", "ERROR", "structural", []string{identifier}, nil, "ID repetido no roadmap: "+identifier, "Atribuir um ID único a cada plano."))
		}
	}

	for _, plan := range plans {
		if typed && plan.schema != 2 {
			findings = append(findings, coherenceFinding("LEGACY_PLAN_CONTRACT", "ERROR", "structural", []string{plan.id}, nil, plan.id+" usa contrato legado sem tarefas tipadas.", "Reescrever o plano com schema_version 2 e tarefas Txx."))
		}
		if len(normalizedPlanStrings(plan, "acceptance")) == 0 {
			findings = append(findings, coherenceFinding("MISSING_ACCEPTANCE", "ERROR", "structural", []string{plan.id}, nil, plan.id+" não declara critérios de aceite.", "Declarar ao menos um resultado observável."))
		}
		if len(normalizedPlanStrings(plan, "verifications")) == 0 {
			findings = append(findings, coherenceFinding("MISSING_VERIFICATION", "ERROR", "structural", []string{plan.id}, nil, plan.id+" não declara verificações.", "Declarar a verificação que prova o aceite."))
		}
		for _, dependency := range normalizedPlanStrings(plan, "depends_on") {
			switch {
			case dependency == plan.id:
				findings = append(findings, coherenceFinding("SELF_DEPENDENCY", "ERROR", "structural", []string{plan.id}, nil, plan.id+" depende de si mesmo.", "Remover a dependência circular."))
			case !known[dependency]:
				findings = append(findings, coherenceFinding("UNKNOWN_DEPENDENCY", "ERROR", "structural", []string{plan.id}, nil, plan.id+" depende do plano inexistente "+dependency+".", "Corrigir depends_on ou adicionar o plano ausente."))
			case order[dependency] > order[plan.id]:
				findings = append(findings, coherenceFinding("ORDER_VIOLATION", "ERROR", "structural", []string{plan.id, dependency}, nil, plan.id+" aparece antes de sua dependência "+dependency+".", "Reordenar o roadmap para executar o provider primeiro."))
			}
		}
		if plan.schema == 2 {
			findings = append(findings, coherenceTaskFindings(plan)...)
			for _, section := range []string{"modules", "interfaces", "data"} {
				available := map[string]bool{}
				for identifier := range current.sections[section] {
					available[identifier] = true
				}
				for identifier := range expected.sections[section] {
					available[identifier] = true
				}
				for _, reference := range normalizedPlanStrings(plan, section) {
					if !available[reference] {
						findings = append(findings, coherenceFinding("UNKNOWN_MODEL_REFERENCE", "ERROR", "structural", []string{plan.id}, []string{reference}, fmt.Sprintf("%s referencia %s.%s, ausente em S0 e Sn.", plan.id, section, reference), "Corrigir a referência ou declarar o item no SYSTEM_MODEL."))
					}
				}
			}
		}
	}

	if _, err := coherencePlanWaves(plans); err != nil && strings.Contains(err.Error(), "ciclo") {
		findings = append(findings, coherenceFinding("DEPENDENCY_CYCLE", "ERROR", "structural", identifiers, nil, "O grafo de planos contém um ciclo.", "Romper o ciclo e declarar uma ordem executável."))
	}
	providers, consumers := map[string][]string{}, map[string][]string{}
	for _, plan := range plans {
		for _, contract := range normalizedPlanStrings(plan, "provides") {
			providers[contract] = append(providers[contract], plan.id)
		}
		for _, contract := range normalizedPlanStrings(plan, "consumes") {
			consumers[contract] = append(consumers[contract], plan.id)
		}
	}
	available := coherenceComponentIDs(current)
	for _, plan := range plans {
		for _, contract := range normalizedPlanStrings(plan, "consumes") {
			if !available[contract] && len(providers[contract]) == 0 {
				findings = append(findings, coherenceFinding("MISSING_PROVIDER", "ERROR", "structural", []string{plan.id}, []string{contract}, plan.id+" consome "+contract+", mas nenhum estado ou plano o fornece.", "Adicionar provider ou remover o consumo inválido."))
			}
			for _, provider := range providers[contract] {
				if provider != plan.id && order[provider] > order[plan.id] {
					findings = append(findings, coherenceFinding("ORDER_VIOLATION", "ERROR", "structural", []string{plan.id, provider}, []string{contract}, plan.id+" consome "+contract+" antes de "+provider+" fornecê-lo.", "Executar o provider antes do consumer."))
				}
			}
		}
	}
	providerKeys := sortedStringKeys(providers)
	for _, contract := range providerKeys {
		values := uniqueSorted(providers[contract])
		if len(values) > 1 {
			findings = append(findings, coherenceFinding("PROVIDER_CONFLICT", "ERROR", "structural", values, []string{contract}, "Contrato "+contract+" possui múltiplos providers: "+strings.Join(values, ", ")+".", "Definir um único provider responsável."))
		}
	}
	owners := map[string][]string{}
	for _, plan := range plans {
		for _, resource := range coherencePlanOwns(plan) {
			owners[resource] = append(owners[resource], plan.id)
		}
	}
	for _, resource := range sortedStringKeys(owners) {
		values := uniqueSorted(owners[resource])
		if len(values) > 1 {
			findings = append(findings, coherenceFinding("OWNERSHIP_CONFLICT", "ERROR", "structural", values, []string{resource}, resource+" possui ownership em "+strings.Join(values, ", ")+".", "Definir um owner único e tornar os demais consumers."))
		}
	}
	for index, plan := range plans {
		for _, removed := range coherenceRemovedContracts(plan) {
			later := []string{}
			for _, candidate := range plans[index+1:] {
				if containsString(normalizedPlanStrings(candidate, "consumes"), removed) {
					later = append(later, candidate.id)
				}
			}
			if len(later) > 0 {
				findings = append(findings, coherenceFinding("CONTRACT_REMOVED_BEFORE_CONSUMERS", "ERROR", "structural", append([]string{plan.id}, later...), []string{removed}, plan.id+" remove "+removed+" antes dos consumers "+strings.Join(later, ", ")+".", "Migrar os consumers antes de remover o contrato."))
			}
		}
	}
	findings = append(findings, coherenceMigrationFindings(plans, order)...)
	required := stringSet(requirements)
	covered := map[string]bool{}
	for _, plan := range plans {
		for _, requirement := range normalizedPlanStrings(plan, "requirements") {
			covered[requirement] = true
		}
	}
	if len(required) > 0 {
		for _, identifier := range sortedSetDifference(covered, required) {
			findings = append(findings, coherenceFinding("PLAN_REQUIREMENT_UNKNOWN", "ERROR", "structural", nil, []string{identifier}, "Plano referencia item ausente do escopo: "+identifier+".", "Corrigir requirements ou incluir o item no SCOPE.md."))
		}
	}
	for _, identifier := range sortedSetDifference(required, covered) {
		findings = append(findings, coherenceFinding("REQUIREMENT_WITHOUT_PLAN", "ERROR", "structural", nil, []string{identifier}, "Requisito sem fase responsável: "+identifier+".", "Associar o requisito a um plano com aceite e verificação."))
	}
	findings = append(findings, coherenceJourneyFindings(current, "atual")...)
	findings = append(findings, coherenceJourneyFindings(expected, "final")...)
	for _, plan := range plans {
		for _, effect := range coherencePlanObjects(plan, "effects") {
			if effect["guard_required"] == false || coherenceEffectHasGuard(effect) {
				continue
			}
			identifier := stateString(effect["id"])
			if identifier == "" {
				identifier = "efeito externo"
			}
			findings = append(findings, coherenceFinding("MISSING_GUARD", "ERROR", "structural", []string{plan.id}, []string{identifier}, plan.id+" declara "+identifier+" sem guard de falha/recuperação.", "Declarar guards verificáveis antes da execução."))
		}
	}
	calculated := current
	for _, plan := range plans {
		var err error
		calculated, err = calculated.applyDelta(plan.modelDelta)
		if err != nil {
			findings = append(findings, coherenceFinding("MODEL_DELTA_INVALID", "ERROR", "structural", []string{plan.id}, nil, plan.id+" possui delta inválido: "+err.Error(), "Corrigir o delta para produzir um snapshot válido."))
			break
		}
	}
	if differences := calculated.differences(expected); len(differences) > 0 {
		encoded, _ := json.Marshal(differences)
		phases := make([]string, 0, len(plans))
		for _, plan := range plans {
			phases = append(phases, plan.id)
		}
		findings = append(findings, coherenceFinding("MODEL_MISMATCH", "ERROR", "structural", phases, nil, "O modelo simulado diverge do modelo final: "+string(encoded), "Alinhar deltas dos planos e SYSTEM_MODEL.md final."))
	}
	coherenceSortFindings(findings, order)
	return findings
}

func coherenceTaskFindings(plan planContract) []any {
	findings, tasks := []any{}, planTasks(plan)
	if len(tasks) == 0 {
		return []any{coherenceFinding("MISSING_TASKS", "ERROR", "structural", []string{plan.id}, nil, plan.id+" não declara tarefas tipadas.", "Declarar ao menos uma tarefa Txx verificável.")}
	}
	counts, position, known := map[string]int{}, map[string]int{}, map[string]bool{}
	for index, task := range tasks {
		id := stateString(task["id"])
		counts[id]++
		position[id], known[id] = index, true
	}
	planRequirements := stringSet(normalizedPlanStrings(plan, "requirements"))
	covered := map[string]bool{}
	for _, task := range tasks {
		id, phase := stateString(task["id"]), plan.id+"/"+stateString(task["id"])
		if !waveTaskID.MatchString(id) {
			findings = append(findings, coherenceFinding("INVALID_TASK_ID", "ERROR", "structural", []string{plan.id}, nil, "ID de tarefa inválido: "+phase+".", "Usar T seguido por ao menos dois dígitos."))
		}
		if counts[id] > 1 {
			findings = append(findings, coherenceFinding("DUPLICATE_TASK_ID", "ERROR", "structural", []string{plan.id}, nil, "ID de tarefa repetido em "+plan.id+": "+id+".", "Atribuir ID único dentro do plano."))
		}
		for _, requirement := range normalizedTaskStrings(task, "covers") {
			covered[requirement] = true
			if !planRequirements[requirement] {
				findings = append(findings, coherenceFinding("TASK_COVERS_UNKNOWN_REQUIREMENT", "ERROR", "structural", []string{plan.id}, []string{requirement}, phase+" cobre item não declarado no plano: "+requirement+".", "Adicionar o item ao plano ou corrigir covers."))
			}
		}
		for _, dependency := range normalizedTaskStrings(task, "depends_on") {
			switch {
			case dependency == id:
				findings = append(findings, coherenceFinding("TASK_SELF_DEPENDENCY", "ERROR", "structural", []string{plan.id}, nil, phase+" depende de si mesma.", "Remover a dependência circular."))
			case !known[dependency]:
				findings = append(findings, coherenceFinding("UNKNOWN_TASK_DEPENDENCY", "ERROR", "structural", []string{plan.id}, nil, phase+" depende da tarefa inexistente "+dependency+".", "Corrigir depends_on ou adicionar a tarefa."))
			case position[dependency] > position[id]:
				findings = append(findings, coherenceFinding("TASK_ORDER_VIOLATION", "ERROR", "structural", []string{plan.id}, nil, phase+" aparece antes de sua dependência "+dependency+".", "Reordenar as tarefas para refletir a execução."))
			}
		}
	}
	for _, requirement := range sortedSetDifference(planRequirements, covered) {
		findings = append(findings, coherenceFinding("TASK_REQUIREMENT_UNCOVERED", "ERROR", "structural", []string{plan.id}, []string{requirement}, plan.id+" não liga "+requirement+" a nenhuma tarefa.", "Associar o item a uma tarefa com verificação e done."))
	}
	if _, err := coherenceTaskWaves(tasks); err != nil && strings.Contains(err.Error(), "ciclo") {
		findings = append(findings, coherenceFinding("TASK_DEPENDENCY_CYCLE", "ERROR", "structural", []string{plan.id}, nil, plan.id+" possui ciclo entre tarefas.", "Romper o ciclo e declarar uma ordem executável."))
	}
	return findings
}

func coherenceMigrationFindings(plans []planContract, order map[string]int) []any {
	findings := []any{}
	for _, plan := range plans {
		for _, migration := range coherencePlanObjects(plan, "migrations") {
			identifier := stateString(migration["id"])
			if identifier == "" {
				identifier = "migration"
			}
			after, err := coherenceFlexibleStrings(migration["after"], "after")
			if err != nil {
				findings = append(findings, coherenceFinding("MIGRATION_ORDER_INVALID", "ERROR", "structural", []string{plan.id}, nil, plan.id+"/"+identifier+" possui after inválido.", "Declarar lista de planos anteriores."))
				continue
			}
			for _, dependency := range after {
				position, exists := order[dependency]
				if !exists || position >= order[plan.id] {
					findings = append(findings, coherenceFinding("MIGRATION_ORDER_INVALID", "ERROR", "structural", []string{plan.id, dependency}, nil, plan.id+"/"+identifier+" exige "+dependency+" antes da migração.", "Reposicionar a migração após sua dependência."))
				}
			}
			if stateBool(migration["destructive"]) && !stateBool(migration["compatibility"]) && stateString(migration["compatibility"]) == "" {
				findings = append(findings, coherenceFinding("MIGRATION_COMPATIBILITY_MISSING", "ERROR", "structural", []string{plan.id}, nil, plan.id+"/"+identifier+" é destrutiva sem compatibilidade declarada.", "Declarar compatibilidade e rollback."))
			}
		}
	}
	return findings
}

func coherenceJourneyFindings(model projectModel, label string) []any {
	findings, components := []any{}, coherenceComponentIDs(model)
	for _, identifier := range sortedModelSectionKeys(model.sections["journeys"]) {
		journey := model.sections["journeys"][identifier]
		path, ok := journey["path"].([]any)
		if !ok || len(path) == 0 {
			findings = append(findings, coherenceFinding("JOURNEY_EMPTY", "ERROR", "structural", nil, []string{identifier}, "Journey "+identifier+" no modelo "+label+" não possui path.", "Declarar o caminho ponta a ponta."))
			continue
		}
		for _, raw := range path {
			component, ok := raw.(string)
			if !ok || !components[component] {
				findings = append(findings, coherenceFinding("JOURNEY_COMPONENT_MISSING", "ERROR", "structural", nil, []string{identifier, fmt.Sprint(raw)}, "Journey "+identifier+" referencia componente ausente: "+fmt.Sprint(raw)+".", "Adicionar o componente ao modelo ou corrigir a jornada."))
			}
		}
	}
	return findings
}

func coherenceComponentIDs(model projectModel) map[string]bool {
	result := map[string]bool{}
	for _, section := range modelCollections {
		for identifier := range model.sections[section] {
			result[identifier] = true
		}
	}
	return result
}

func coherencePlanOwns(plan planContract) []string {
	if plan.schema == 2 {
		return normalizedPlanStrings(plan, "ownership")
	}
	return normalizedPlanStrings(plan, "owns")
}

func coherencePlanObjects(plan planContract, field string) []map[string]any {
	raw := plan.value[field]
	if field == "effects" && plan.schema == 1 {
		raw = plan.value["external_effects"]
		if raw == nil {
			raw = plan.value["effects"]
		}
	}
	result := []map[string]any{}
	for _, value := range stateArray(raw) {
		if item, ok := value.(map[string]any); ok {
			result = append(result, item)
		}
	}
	return result
}

func coherenceRemovedContracts(plan planContract) []string {
	operations := stateObject(plan.modelDelta["contracts"])
	result := []string{}
	for _, raw := range stateArray(operations["remove"]) {
		identifier := stateString(raw)
		if item, ok := raw.(map[string]any); ok {
			identifier = stateString(item["id"])
		}
		if identifier != "" {
			result = append(result, identifier)
		}
	}
	sort.Strings(result)
	return result
}

func coherenceEffectHasGuard(effect map[string]any) bool {
	if guards, err := coherenceFlexibleStrings(effect["guards"], "guards"); err == nil && len(guards) > 0 {
		return true
	}
	for _, key := range []string{"idempotency", "authenticity", "deduplication", "recovery", "rollback", "reconciliation"} {
		if stateBool(effect[key]) || stateString(effect[key]) != "" {
			return true
		}
	}
	return false
}

func coherenceSortFindings(findings []any, order map[string]int) {
	severity := map[string]int{"ERROR": 0, "WARNING": 1, "INFO": 2}
	sort.SliceStable(findings, func(left, right int) bool {
		a, b := stateObject(findings[left]), stateObject(findings[right])
		position := func(item map[string]any) int {
			minimum := len(order)
			for _, phase := range stateStringSlice(item["phases"]) {
				if value, ok := order[phase]; ok && value < minimum {
					minimum = value
				}
			}
			return minimum
		}
		if position(a) != position(b) {
			return position(a) < position(b)
		}
		if severity[stateString(a["severity"])] != severity[stateString(b["severity"])] {
			return severity[stateString(a["severity"])] < severity[stateString(b["severity"])]
		}
		if stateString(a["code"]) != stateString(b["code"]) {
			return stateString(a["code"]) < stateString(b["code"])
		}
		return stateString(a["evidence"]) < stateString(b["evidence"])
	})
}

func sortedStringKeys(values map[string][]string) []string {
	result := make([]string, 0, len(values))
	for value := range values {
		result = append(result, value)
	}
	sort.Strings(result)
	return result
}

func sortedModelSectionKeys(values map[string]map[string]any) []string {
	result := make([]string, 0, len(values))
	for value := range values {
		result = append(result, value)
	}
	sort.Strings(result)
	return result
}

func sortedSetDifference(left, right map[string]bool) []string {
	result := []string{}
	for value := range left {
		if !right[value] {
			result = append(result, value)
		}
	}
	sort.Strings(result)
	return result
}
