package gokernel

import (
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

func runRoadmap(args []string) (any, error) {
	if len(args) == 0 {
		return nil, argparseError("the following arguments are required: action")
	}
	action := args[0]
	if !oneOf(action, "sync", "next-wave") {
		return nil, argparseError(fmt.Sprintf("argument action: invalid choice: '%s'", action))
	}
	flags, err := parseFlags(args[1:], map[string]bool{"--repo": true, "--change": true, "--format": true}, map[string]bool{})
	if err != nil {
		return nil, err
	}
	change := lastValue(flags, "--change")
	if change == "" {
		return nil, argparseError("the following arguments are required: --change")
	}
	format := lastValue(flags, "--format")
	if format != "" && format != "json" {
		return nil, argparseError(argparseInvalidChoice("--format", format, []string{"json"}))
	}
	repo := lastValue(flags, "--repo")
	if repo == "" {
		repo, err = os.Getwd()
		if err != nil {
			return nil, workflowError("WAVE_INCOMPLETE", "repo 0.4 exige .bianchini")
		}
	}
	if action == "next-wave" {
		return projectNextWave(repo, change)
	}
	return syncRoadmap(repo, change)
}

func syncRoadmap(repo, change string) (map[string]any, error) {
	workspace, directory, plans, err := loadRoadmapPackage(repo, change)
	if err != nil {
		return nil, err
	}
	coherence, err := readStructuredFrontmatter(filepath.Join(directory, "COHERENCE.md"))
	if err != nil {
		return nil, workflowError("COHERENCE_ERROR", err.Error())
	}
	planningContract := stateInt(coherence["planning_contract"])
	if planningContract == 0 {
		planningContract = 1
	}
	if planningContract < 2 {
		return nil, workflowError("COHERENCE_ERROR", "roadmap sync exige planning_contract 2")
	}
	for _, plan := range plans {
		if plan.schema != 2 {
			return nil, workflowError("COHERENCE_ERROR", "roadmap v2 exige todos os planos em schema_version 2")
		}
	}
	content, err := roadmapDocument(plans)
	if err != nil {
		return nil, workflowError("MODEL_MISMATCH", err.Error())
	}
	if err := syncPlanningSpecs(workspace, directory, coherence); err != nil {
		return nil, err
	}
	roadmap := filepath.Join(directory, "ROADMAP.md")
	if err := workspace.atomicWrite(roadmap, content); err != nil {
		return nil, err
	}
	phases := make([]string, len(plans))
	for index, plan := range plans {
		phases[index] = plan.id
	}
	return map[string]any{
		"change": filepath.Base(directory), "planning_contract": planningContract,
		"phases": phases, "roadmap": roadmap, "digest": sha256Bytes(content),
	}, nil
}

func loadRoadmapPackage(repo, change string) (methodWorkspace, string, []planContract, error) {
	root, err := safeRoot(repo)
	if err != nil {
		return methodWorkspace{}, "", nil, err
	}
	workspace := newMethodWorkspace(root)
	state, err := workspace.readState()
	if err != nil {
		if _, statErr := os.Lstat(workspace.state); os.IsNotExist(statErr) {
			return methodWorkspace{}, "", nil, fmt.Errorf("erro de entrada/IO: STATE.md ausente: %s", workspace.state)
		}
		return methodWorkspace{}, "", nil, err
	}
	directory, err := locateChangeDirectory(workspace, change)
	if err != nil {
		return methodWorkspace{}, "", nil, err
	}
	active, activeOK := state["active_work"].(map[string]any)
	if activeOK && stateString(active["id"]) == filepath.Base(directory) && (stateString(state["status"]) == "scope_ready" || stateString(active["status"]) == "scope_ready") {
		if _, verifyErr := verifyScope(root, filepath.Base(directory), ""); verifyErr != nil {
			return methodWorkspace{}, "", nil, workflowError("STALE_EVIDENCE", verifyErr.Error())
		}
	}
	if _, err := loadProjectModel(workspace.currentMod); err != nil {
		return methodWorkspace{}, "", nil, workflowError("MODEL_MISMATCH", err.Error())
	}
	if _, err := loadProjectModel(filepath.Join(directory, "SYSTEM_MODEL.md")); err != nil {
		return methodWorkspace{}, "", nil, workflowError("MODEL_MISMATCH", err.Error())
	}
	paths, err := filepath.Glob(filepath.Join(directory, "plans", "P*.md"))
	if err != nil || len(paths) == 0 {
		return methodWorkspace{}, "", nil, workflowError("COHERENCE_ERROR", "a mudança exige ao menos um plano")
	}
	sort.Strings(paths)
	plans := make([]planContract, 0, len(paths))
	seen := map[string]bool{}
	for _, path := range paths {
		identifier, valid := planFileID(path)
		if !valid {
			return methodWorkspace{}, "", nil, workflowError("COHERENCE_ERROR", "arquivo de plano com identidade inválida: "+filepath.Base(path))
		}
		if seen[identifier] {
			return methodWorkspace{}, "", nil, workflowError("COHERENCE_ERROR", "arquivos de plano duplicam identidade: "+identifier)
		}
		plan, loadErr := loadPlanContract(path)
		if loadErr != nil {
			return methodWorkspace{}, "", nil, workflowError("MODEL_MISMATCH", loadErr.Error())
		}
		if plan.id != identifier {
			return methodWorkspace{}, "", nil, workflowError("MODEL_MISMATCH", "arquivo "+filepath.Base(path)+" diverge do id "+plan.id)
		}
		seen[identifier] = true
		plans = append(plans, plan)
	}
	return workspace, directory, plans, nil
}

func roadmapDocument(plans []planContract) ([]byte, error) {
	phases := make([]any, 0, len(plans))
	body := []string{"# Roadmap", "", "Gerado deterministicamente a partir dos planos."}
	for _, plan := range plans {
		value := plan.value
		dependsOn, _ := stringValues(value["depends_on"], "depends_on")
		requirements, _ := stringValues(value["requirements"], "requirements")
		rawTasks := stateArray(value["tasks"])
		tasks := make([]string, 0, len(rawTasks))
		for _, raw := range rawTasks {
			tasks = append(tasks, stateString(stateObject(raw)["id"]))
		}
		result := stateString(value["result"])
		execution := stateString(value["execution"])
		phases = append(phases, map[string]any{
			"id": plan.id, "result": nilIfEmpty(result), "depends_on": dependsOn,
			"requirements": requirements, "execution": nilIfEmpty(execution), "tasks": tasks,
		})
		title := result
		if title == "" {
			title = "Entrega planejada"
		}
		dependsLabel, requirementLabel, taskLabel := strings.Join(dependsOn, ", "), strings.Join(requirements, ", "), strings.Join(tasks, ", ")
		if dependsLabel == "" {
			dependsLabel = "nenhum"
		}
		if requirementLabel == "" {
			requirementLabel = "legado"
		}
		if taskLabel == "" {
			taskLabel = "legado"
		}
		body = append(body, "", "## "+plan.id+" — "+title, "", "- Depende de: "+dependsLabel, "- Escopo: "+requirementLabel, "- Tarefas: "+taskLabel)
	}
	return frontmatterDocument(map[string]any{"schema_version": 1, "planning_contract": 2, "phases": phases}, strings.Join(body, "\n"), false)
}

func nilIfEmpty(value string) any {
	if value == "" {
		return nil
	}
	return value
}
