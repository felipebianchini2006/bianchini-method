package gokernel

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
)

var planResultName = regexp.MustCompile(`^P[0-9]{2,}\.md$`)

func runPlan(args []string) (any, error) {
	if len(args) == 0 {
		return nil, argparseError("the following arguments are required: action")
	}
	if args[0] != "complete" {
		return nil, argparseError(fmt.Sprintf("argument action: invalid choice: '%s'", args[0]))
	}
	flags, err := parseFlags(args[1:], map[string]bool{
		"--repo": true, "--change": true, "--plan": true, "--task": true,
		"--context-pack": true, "--actual-delta": true, "--result": true,
		"--verification": true, "--completed-task": true,
	}, map[string]bool{})
	if err != nil {
		return nil, err
	}
	missing := []string{}
	for _, flag := range []string{"--change", "--plan", "--result"} {
		if lastValue(flags, flag) == "" {
			missing = append(missing, flag)
		}
	}
	if len(missing) > 0 {
		return nil, argparseError("the following arguments are required: " + strings.Join(missing, ", "))
	}
	repo := lastValue(flags, "--repo")
	if repo == "" {
		repo, err = os.Getwd()
		if err != nil {
			return nil, err
		}
	}
	task := lastValue(flags, "--task")
	pack := lastValue(flags, "--context-pack")
	delta := lastValue(flags, "--actual-delta")
	if task != "" {
		if pack == "" {
			return nil, userError("plan complete --task exige --context-pack")
		}
		if delta != "" || len(flags.values["--completed-task"]) > 0 {
			return nil, userError("plan complete --task não aceita --actual-delta ou --completed-task")
		}
		return taskComplete(repo, lastValue(flags, "--change"), lastValue(flags, "--plan"), task, pack, lastValue(flags, "--result"), flags.values["--verification"])
	}
	if delta == "" {
		return nil, userError("plan complete exige --actual-delta")
	}
	if pack != "" {
		return nil, userError("plan complete sem --task não aceita --context-pack")
	}
	return completePlan(repo, lastValue(flags, "--change"), lastValue(flags, "--plan"), delta, lastValue(flags, "--result"), flags.values["--verification"], flags.values["--completed-task"])
}

func approvedPlanPackage(repo, change string) (coherencePackage, map[string]any, error) {
	pack, err := loadCoherencePackage(repo, change)
	if err != nil {
		return coherencePackage{}, nil, err
	}
	coherence := pack.contract
	if !oneOf(stateString(coherence["status"]), "approved", "approved_with_stale") {
		return coherencePackage{}, nil, workflowError("COHERENCE_ERROR", "plano exige pacote global aprovado")
	}
	if err := coherenceAssertCurrent(pack, coherence); err != nil {
		return coherencePackage{}, nil, err
	}
	return pack, coherence, nil
}

func planByID(plans []planContract, identifier string) (planContract, error) {
	matches := []planContract{}
	for _, plan := range plans {
		if plan.id == identifier {
			matches = append(matches, plan)
		}
	}
	if len(matches) != 1 {
		return planContract{}, workflowError("MODEL_MISMATCH", identifier+" deve localizar exatamente um plano")
	}
	return matches[0], nil
}

func taskComplete(repo, change, planID, taskID, packPath, result string, verifications []string) (map[string]any, error) {
	pack, coherence, err := approvedPlanPackage(repo, change)
	if err != nil {
		return nil, err
	}
	if containsString(stateStringSlice(coherence["stale_plans"]), planID) {
		return nil, workflowError("IMPACT_STALE", planID+" está stale")
	}
	plan, err := planByID(pack.plans, planID)
	if err != nil {
		return nil, err
	}
	if plan.schema != 2 {
		return nil, workflowError("MODEL_MISMATCH", "resultado por tarefa exige plano schema 2")
	}
	var task map[string]any
	for _, candidate := range planTasks(plan) {
		if stateString(candidate["id"]) == taskID {
			if task != nil {
				return nil, workflowError("MODEL_MISMATCH", "tarefa desconhecida: "+planID+"/"+taskID)
			}
			task = candidate
		}
	}
	if task == nil {
		return nil, workflowError("MODEL_MISMATCH", "tarefa desconhecida: "+planID+"/"+taskID)
	}
	packageDigest := stateString(coherence["digest"])
	if !waveDigest.MatchString(packageDigest) {
		return nil, workflowError("STALE_EVIDENCE", "pacote aprovado possui digest inválido")
	}
	results, err := planResultPayloads(pack.workspace, pack.directory)
	if err != nil {
		return nil, err
	}
	missingPlans := []string{}
	for _, dependency := range normalizedPlanStrings(plan, "depends_on") {
		if results[dependency] == nil {
			missingPlans = append(missingPlans, dependency)
		}
	}
	if len(missingPlans) > 0 {
		return nil, workflowError("MISSING_PROVIDER", "dependências ainda não concluídas: "+strings.Join(missingPlans, ", "))
	}
	taskResults, err := planTaskResultPayloads(pack.workspace, pack.directory, plan, packageDigest)
	if err != nil {
		return nil, err
	}
	if taskResults[taskID] != nil {
		return nil, workflowError("COHERENCE_ERROR", planID+"/"+taskID+" já foi concluída")
	}
	missingTasks := []string{}
	for _, dependency := range normalizedTaskStrings(task, "depends_on") {
		if taskResults[dependency] == nil {
			missingTasks = append(missingTasks, dependency)
		}
	}
	if len(missingTasks) > 0 {
		return nil, workflowError("MISSING_PROVIDER", "tarefas ainda não concluídas: "+strings.Join(missingTasks, ", "))
	}
	verified, err := verifyContextPack(pack.workspace.root, packPath)
	if err != nil {
		return nil, err
	}
	identity := strings.SplitN(filepath.Base(pack.directory), "-", 2)[0] + "/" + plan.id + "/" + taskID
	if stateString(verified["unit"]) != identity {
		return nil, workflowError("STALE_EVIDENCE", fmt.Sprintf("context pack pertence a %s, não a %s", stateString(verified["unit"]), identity))
	}
	summary := strings.TrimSpace(result)
	evidence := nonemptyUnique(verifications)
	if summary == "" {
		return nil, workflowError("DOCVIVA_INCOMPLETE", "conclusão da tarefa exige resultado")
	}
	if len(evidence) == 0 {
		return nil, workflowError("STALE_EVIDENCE", "conclusão da tarefa exige verificação")
	}
	payload := map[string]any{
		"schema_version": 1, "change": filepath.Base(pack.directory), "plan": plan.id,
		"task": taskID, "status": "completed", "expected_result": strings.TrimSpace(stateString(task["result"])),
		"result": summary, "covers": normalizedTaskStrings(task, "covers"), "verification": evidence,
		"pack_identity": identity, "pack_digest": verified["digest"], "package_digest": packageDigest,
		"completed_at": utcNow(),
	}
	document, _ := frontmatterDocument(payload, "# Resultado "+plan.id+"/"+taskID+"\n\n"+summary, false)
	if err := pack.workspace.atomicWrite(filepath.Join(pack.directory, "results", "tasks", plan.id, taskID+".md"), document); err != nil {
		return nil, err
	}
	state, err := pack.workspace.readState()
	if err != nil {
		return nil, err
	}
	state["current_unit"], state["status"], state["blockers"] = nil, "approved", []any{}
	state["next_action"], state["digest"], state["updated_at"] = "Consultar a próxima onda de "+filepath.Base(pack.directory)+".", packageDigest, utcNow()
	if active, ok := state["active_work"].(map[string]any); ok {
		active["status"] = "approved"
	}
	if err := pack.workspace.writeState(state, "# Estado atual"); err != nil {
		return nil, err
	}
	return map[string]any{
		"change": filepath.Base(pack.directory), "plan": plan.id, "task": taskID, "status": "completed",
		"pack_identity": identity, "pack_digest": verified["digest"], "package_digest": packageDigest,
	}, nil
}

func completePlan(repo, change, planID, actualDeltaPath, result string, verifications, completedTasks []string) (map[string]any, error) {
	pack, coherence, err := approvedPlanPackage(repo, change)
	if err != nil {
		return nil, err
	}
	if containsString(stateStringSlice(coherence["stale_plans"]), planID) {
		return nil, workflowError("IMPACT_STALE", planID+" está stale")
	}
	plan, err := planByID(pack.plans, planID)
	if err != nil {
		return nil, err
	}
	completed := nonemptyUnique(completedTasks)
	managedTasks := plan.schema == 2 && stateInt(coherence["schema_version"]) == 2 && stateInt(coherence["spec_contract"]) == 1
	if plan.schema == 2 {
		expectedTasks := planTaskIDs(plan)
		if managedTasks {
			taskResults, loadErr := planTaskResultPayloads(pack.workspace, pack.directory, plan, stateString(coherence["digest"]))
			if loadErr != nil {
				return nil, loadErr
			}
			missing := []string{}
			for _, identifier := range expectedTasks {
				if taskResults[identifier] == nil {
					missing = append(missing, identifier)
				}
			}
			if len(missing) > 0 {
				return nil, workflowError("DOCVIVA_INCOMPLETE", "conclusão exige resultados próprios para todas as tarefas (ausentes: "+strings.Join(missing, ", ")+")")
			}
		}
		if (managedTasks && len(completed) > 0 || !managedTasks) && !sameStrings(completed, expectedTasks) {
			return nil, workflowError("DOCVIVA_INCOMPLETE", taskCompletionMismatch(expectedTasks, completed))
		}
		completed = expectedTasks
	}
	results, err := planResultPayloads(pack.workspace, pack.directory)
	if err != nil {
		return nil, err
	}
	if results[planID] != nil {
		return nil, workflowError("COHERENCE_ERROR", planID+" já possui resultado")
	}
	missingDependencies := []string{}
	for _, dependency := range normalizedPlanStrings(plan, "depends_on") {
		if results[dependency] == nil {
			missingDependencies = append(missingDependencies, dependency)
		}
	}
	sort.Strings(missingDependencies)
	if len(missingDependencies) > 0 {
		return nil, workflowError("MISSING_PROVIDER", "dependências ainda não concluídas: "+strings.Join(missingDependencies, ", "))
	}
	evidence := nonemptyUnique(verifications)
	if len(evidence) == 0 {
		return nil, workflowError("STALE_EVIDENCE", "conclusão do plano exige verificação")
	}
	summary := strings.TrimSpace(result)
	if summary == "" {
		return nil, workflowError("DOCVIVA_INCOMPLETE", "conclusão do plano exige resultado")
	}
	delta, err := readActualDelta(actualDeltaPath)
	if err != nil {
		return nil, err
	}
	if !mapsEqual(delta, plan.modelDelta) {
		return nil, workflowError("IMPACT_STALE", "delta entregue diverge do plano; execute impact analyze e revalide o pacote")
	}
	effectiveBefore, err := effectiveProjectModel(pack.current, pack.plans, results)
	if err != nil {
		return nil, err
	}
	missingContracts := []string{}
	for _, contract := range normalizedPlanStrings(plan, "consumes") {
		if effectiveBefore.sections["contracts"][contract] == nil {
			missingContracts = append(missingContracts, contract)
		}
	}
	sort.Strings(missingContracts)
	if len(missingContracts) > 0 {
		return nil, workflowError("MISSING_PROVIDER", "contratos consumidos ainda ausentes: "+strings.Join(missingContracts, ", "))
	}
	effectiveAfter, applyErr := effectiveBefore.applyDelta(delta)
	if applyErr != nil {
		return nil, workflowError("MODEL_MISMATCH", applyErr.Error())
	}
	completedAt := utcNow()
	payload := map[string]any{
		"schema_version": 1, "change": filepath.Base(pack.directory), "plan": plan.id, "status": "completed",
		"result": summary, "promised_delta_digest": waveStableDigest(plan.modelDelta), "actual_delta": delta,
		"actual_delta_digest": waveStableDigest(delta), "model_before_digest": effectiveBefore.digest(),
		"model_after_digest": effectiveAfter.digest(), "verification": evidence, "completed_tasks": completed,
		"impact":       map[string]any{"radius": "local", "stale_plans": []any{}, "reason": "entrega equivalente ao delta aprovado"},
		"completed_at": completedAt,
	}
	if plan.schema == 2 && !managedTasks {
		for _, task := range planTasks(plan) {
			taskID := stateString(task["id"])
			taskPayload := map[string]any{
				"schema_version": 1, "change": filepath.Base(pack.directory), "plan": plan.id, "task": taskID,
				"status": "completed", "expected_result": strings.TrimSpace(stateString(task["result"])), "result": summary,
				"covers": normalizedTaskStrings(task, "covers"), "verification": evidence, "completed_at": completedAt,
			}
			document, _ := frontmatterDocument(taskPayload, "# Resultado "+plan.id+"/"+taskID+"\n\n"+summary, false)
			if err := pack.workspace.atomicWrite(filepath.Join(pack.directory, "results", "tasks", plan.id, taskID+".md"), document); err != nil {
				return nil, err
			}
		}
	}
	document, _ := frontmatterDocument(payload, "# Resultado "+plan.id+"\n\n"+summary, false)
	if err := pack.workspace.atomicWrite(filepath.Join(pack.directory, "results", plan.id+".md"), document); err != nil {
		return nil, err
	}
	resultSet := map[string]bool{plan.id: true}
	for identifier := range results {
		resultSet[identifier] = true
	}
	pending := []string{}
	for _, item := range pack.plans {
		if !resultSet[item.id] {
			pending = append(pending, item.id)
		}
	}
	state, err := pack.workspace.readState()
	if err != nil {
		return nil, err
	}
	state["current_unit"], state["blockers"], state["digest"], state["updated_at"] = nil, []any{}, coherence["digest"], utcNow()
	state["status"] = "pending_close"
	state["next_action"] = "Executar o fechamento global de " + filepath.Base(pack.directory) + "."
	if len(pending) > 0 {
		state["current_unit"], state["status"], state["next_action"] = pending[0], "approved", "Executar "+pending[0]+" de "+filepath.Base(pack.directory)+"."
	}
	if active, ok := state["active_work"].(map[string]any); ok {
		active["status"] = state["status"]
	}
	if err := pack.workspace.writeState(state, "# Estado atual"); err != nil {
		return nil, err
	}
	var next any
	if len(pending) > 0 {
		next = pending[0]
	}
	return map[string]any{
		"change": filepath.Base(pack.directory), "plan": plan.id, "status": "completed",
		"model_digest": effectiveAfter.digest(), "completed_tasks": completed, "next_plan": next,
	}, nil
}

func planResultPayloads(workspace methodWorkspace, directory string) (map[string]map[string]any, error) {
	result := map[string]map[string]any{}
	resultsDirectory := filepath.Join(directory, "results")
	if err := workspace.validateWorkspacePath(resultsDirectory); err != nil {
		return nil, err
	}
	entries, err := os.ReadDir(resultsDirectory)
	if os.IsNotExist(err) {
		return result, nil
	}
	if err != nil {
		return nil, workflowError("DOCVIVA_INCOMPLETE", err.Error())
	}
	for _, entry := range entries {
		if entry.IsDir() || !planResultName.MatchString(entry.Name()) {
			continue
		}
		path := filepath.Join(resultsDirectory, entry.Name())
		info, statErr := os.Lstat(path)
		if statErr != nil || info.Mode()&os.ModeSymlink != 0 || !info.Mode().IsRegular() {
			return nil, workflowError("DOCVIVA_INCOMPLETE", "resultado inválido: "+entry.Name())
		}
		payload, readErr := readStructuredFrontmatter(path)
		if readErr != nil {
			return nil, workflowError("DOCVIVA_INCOMPLETE", readErr.Error())
		}
		identifier := stateString(payload["plan"])
		if identifier == "" || result[identifier] != nil {
			return nil, workflowError("DOCVIVA_INCOMPLETE", "resultado inválido: "+entry.Name())
		}
		result[identifier] = payload
	}
	return result, nil
}

func planTaskResultPayloads(workspace methodWorkspace, directory string, plan planContract, packageDigest string) (map[string]map[string]any, error) {
	result := map[string]map[string]any{}
	taskDirectory := filepath.Join(directory, "results", "tasks", plan.id)
	if err := workspace.validateWorkspacePath(taskDirectory); err != nil {
		return nil, err
	}
	entries, err := os.ReadDir(taskDirectory)
	if os.IsNotExist(err) {
		return result, nil
	}
	if err != nil {
		return nil, workflowError("MODEL_MISMATCH", "resultados de "+plan.id+" são inseguros")
	}
	known := map[string]map[string]any{}
	for _, task := range planTasks(plan) {
		known[stateString(task["id"])] = task
	}
	changeName := filepath.Base(directory)
	prefix := strings.SplitN(changeName, "-", 2)[0]
	for _, entry := range entries {
		path := filepath.Join(taskDirectory, entry.Name())
		info, statErr := os.Lstat(path)
		if statErr != nil || info.Mode()&os.ModeSymlink != 0 || !info.Mode().IsRegular() || !regexp.MustCompile(`^T[0-9]{2,}\.md$`).MatchString(entry.Name()) {
			return nil, workflowError("MODEL_MISMATCH", "resultado de tarefa inválido: "+entry.Name())
		}
		taskID := strings.TrimSuffix(entry.Name(), ".md")
		task := known[taskID]
		if task == nil || result[taskID] != nil {
			return nil, workflowError("MODEL_MISMATCH", "resultado pertence a tarefa desconhecida: "+taskID)
		}
		payload, readErr := readStructuredFrontmatter(path)
		if readErr != nil {
			return nil, workflowError("DOCVIVA_INCOMPLETE", readErr.Error())
		}
		if err := validatePlanTaskResult(payload, changeName, prefix+"/"+plan.id+"/"+taskID, plan.id, taskID, task, packageDigest); err != nil {
			return nil, err
		}
		result[taskID] = payload
	}
	return result, nil
}

func validatePlanTaskResult(value map[string]any, change, identity, planID, taskID string, task map[string]any, packageDigest string) error {
	if !hasExactKeys(value, waveTaskResultFields) || stateInt(value["schema_version"]) != 1 || stateString(value["change"]) != change || stateString(value["plan"]) != planID || stateString(value["task"]) != taskID || stateString(value["status"]) != "completed" || stateString(value["expected_result"]) != strings.TrimSpace(stateString(task["result"])) || stateString(value["pack_identity"]) != identity || stateString(value["package_digest"]) != packageDigest || !waveDigest.MatchString(stateString(value["pack_digest"])) || !waveNonemptyText(value["result"]) || !waveNonemptyText(value["completed_at"]) || !waveEvidence(value["verification"]) {
		return workflowError("DOCVIVA_INCOMPLETE", "resultado inválido de "+identity)
	}
	covers, ok := waveExactStringList(value["covers"])
	if !ok || !sameStrings(covers, normalizedTaskStrings(task, "covers")) {
		return workflowError("DOCVIVA_INCOMPLETE", "resultado inválido de "+identity)
	}
	return nil
}

func readActualDelta(path string) (map[string]any, error) {
	if err := rejectForeignNamespace(path, "--actual-delta"); err != nil {
		return nil, workflowError("MODEL_MISMATCH", "--actual-delta exige arquivo JSON regular")
	}
	info, err := os.Lstat(path)
	if err != nil || info.Mode()&os.ModeSymlink != 0 || !info.Mode().IsRegular() {
		return nil, workflowError("MODEL_MISMATCH", "--actual-delta exige arquivo JSON regular")
	}
	content, err := os.ReadFile(path)
	if err != nil || !validUTF8Text(content) {
		return nil, workflowError("MODEL_MISMATCH", "actual_delta inválido: conteúdo ilegível")
	}
	decoder := json.NewDecoder(bytes.NewReader(content))
	decoder.UseNumber()
	var raw any
	if err := decoder.Decode(&raw); err != nil {
		return nil, workflowError("MODEL_MISMATCH", "actual_delta inválido: "+err.Error())
	}
	var trailing any
	if err := decoder.Decode(&trailing); err == nil {
		return nil, workflowError("MODEL_MISMATCH", "actual_delta inválido: valores adicionais")
	}
	delta, ok := raw.(map[string]any)
	if !ok {
		return nil, workflowError("MODEL_MISMATCH", "actual_delta exige objeto JSON")
	}
	return delta, nil
}

func effectiveProjectModel(current projectModel, plans []planContract, results map[string]map[string]any) (projectModel, error) {
	model := current
	for _, plan := range plans {
		result := results[plan.id]
		if result == nil {
			continue
		}
		if stateString(result["status"]) != "completed" {
			return projectModel{}, workflowError("DOCVIVA_INCOMPLETE", "resultado de "+plan.id+" não está completo")
		}
		delta, ok := result["actual_delta"].(map[string]any)
		if !ok {
			return projectModel{}, workflowError("DOCVIVA_INCOMPLETE", "resultado de "+plan.id+" não declara actual_delta")
		}
		var err error
		model, err = model.applyDelta(delta)
		if err != nil {
			return projectModel{}, workflowError("MODEL_MISMATCH", plan.id+": "+err.Error())
		}
	}
	return model, nil
}

func taskCompletionMismatch(expected, completed []string) string {
	missing := []string{}
	unknown := []string{}
	for _, identifier := range expected {
		if !containsString(completed, identifier) {
			missing = append(missing, identifier)
		}
	}
	for _, identifier := range completed {
		if !containsString(expected, identifier) {
			unknown = append(unknown, identifier)
		}
	}
	details := []string{}
	if len(missing) > 0 {
		details = append(details, "ausentes: "+strings.Join(missing, ", "))
	}
	if len(unknown) > 0 {
		details = append(details, "desconhecidas: "+strings.Join(unknown, ", "))
	}
	if len(details) == 0 {
		details = append(details, "ordem divergente do plano")
	}
	return "conclusão exige todas as tarefas na ordem aprovada (" + strings.Join(details, "; ") + ")"
}

func nonemptyUnique(values []string) []string {
	result := []string{}
	seen := map[string]bool{}
	for _, value := range values {
		value = strings.TrimSpace(value)
		if value != "" && !seen[value] {
			seen[value] = true
			result = append(result, value)
		}
	}
	return result
}
