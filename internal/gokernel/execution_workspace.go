package gokernel

import (
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
)

var (
	executionChangePrefix = regexp.MustCompile(`^C[0-9]{3}$`)
	executionPlanID       = regexp.MustCompile(`^P[0-9]{2,}$`)
	executionBranch       = regexp.MustCompile(`^bm/c[0-9]{3}-p[0-9]{2,}$`)
)

type executionWorkspaceDependencies struct {
	git     func(string, ...string) (string, error)
	persist func(methodWorkspace, string, map[string]any, string) error
}

func defaultExecutionWorkspaceDependencies() executionWorkspaceDependencies {
	return executionWorkspaceDependencies{
		git:     executionWorkspaceGitCommand,
		persist: persistExecutionWorkspace,
	}
}

func runExecutionWorkspace(args []string) (any, error) {
	return runExecutionWorkspaceWithDependencies(args, defaultExecutionWorkspaceDependencies())
}

func runExecutionWorkspaceWithDependencies(args []string, dependencies executionWorkspaceDependencies) (any, error) {
	if len(args) == 0 {
		return nil, argparseError("the following arguments are required: action")
	}
	action := args[0]
	if !oneOf(action, "create", "check", "locate", "resume", "finish") {
		return nil, argparseError(fmt.Sprintf("argument action: invalid choice: '%s'", action))
	}
	flags, err := parseFlags(args[1:], map[string]bool{
		"--repo": true, "--change": true, "--plan": true, "--target": true,
	}, map[string]bool{})
	if err != nil {
		return nil, err
	}
	repo := lastValue(flags, "--repo")
	if repo == "" {
		repo, err = os.Getwd()
		if err != nil {
			return nil, workflowError("DIRTY_WORKSPACE", "o diretório não é uma raiz Git")
		}
	}
	root, err := executionWorkspaceRepositoryRoot(repo, dependencies.git)
	if err != nil {
		return nil, err
	}
	change, plan := lastValue(flags, "--change"), lastValue(flags, "--plan")
	if action != "check" && action != "finish" && (change == "" || plan == "") {
		if action == "create" {
			return nil, fmt.Errorf("--change e --plan são obrigatórios para criar workspace 0.4")
		}
		return nil, fmt.Errorf("--change e --plan são obrigatórios para %s no método 0.4", action)
	}
	if action == "finish" && change == "" {
		return nil, fmt.Errorf("--change é obrigatório para finalizar workspaces")
	}
	switch action {
	case "create":
		return executionWorkspaceCreate(root, change, plan, lastValue(flags, "--target"), dependencies)
	case "check":
		return executionWorkspaceCheck(root, dependencies.git)
	case "finish":
		return executionWorkspaceFinish(root, change, plan, dependencies.git)
	default:
		return executionWorkspaceLocate(root, change, plan, action == "resume", dependencies.git)
	}
}

func executionWorkspaceFinish(root, change, plan string, git func(string, ...string) (string, error)) (map[string]any, error) {
	prefix := strings.SplitN(change, "-", 2)[0]
	if !executionChangePrefix.MatchString(prefix) {
		return nil, workflowError("MODEL_MISMATCH", "change exige C seguido de três dígitos")
	}
	wantedPrefix := "bm/" + strings.ToLower(prefix) + "-"
	wantedBranch := ""
	if plan != "" {
		_, branch, err := executionWorkspaceIdentity(change, plan)
		if err != nil {
			return nil, err
		}
		wantedBranch = branch
	}
	output, err := git(root, "worktree", "list", "--porcelain")
	if err != nil {
		return nil, executionWorkspaceGitError(err)
	}
	type candidate struct{ path, branch string }
	candidates := []candidate{}
	for _, record := range parseExecutionWorktrees(output) {
		branch := strings.TrimPrefix(record["branch"], "refs/heads/")
		if branch == "" || branch == record["branch"] || !strings.HasPrefix(branch, wantedPrefix) || wantedBranch != "" && branch != wantedBranch {
			continue
		}
		path := filepath.Clean(record["worktree"])
		if path == root {
			continue
		}
		metadataPaths, _ := filepath.Glob(filepath.Join(path, ".bianchini", ".runtime", "workspace-*.json"))
		if len(metadataPaths) != 1 {
			return nil, workflowError("DIRTY_WORKSPACE", "workspace "+path+" não possui identidade confiável")
		}
		metadata, metadataErr := readExecutionWorkspaceMetadata(metadataPaths[0])
		if metadataErr != nil || stateString(metadata["source_repo"]) != root || strings.SplitN(stateString(metadata["change"]), "-", 2)[0] != prefix || stateString(metadata["branch"]) != branch {
			return nil, workflowError("DIRTY_WORKSPACE", "workspace "+path+" possui identidade divergente")
		}
		status, statusErr := git(path, "status", "--porcelain")
		if statusErr != nil || status != "" {
			return nil, workflowError("DIRTY_WORKSPACE", "workspace possui alterações não integradas: "+path)
		}
		if _, ancestorErr := git(root, "merge-base", "--is-ancestor", branch, "HEAD"); ancestorErr != nil {
			return nil, workflowError("UNMERGED_WORKSPACE", "branch ainda não está integrada no HEAD: "+branch)
		}
		candidates = append(candidates, candidate{path: path, branch: branch})
	}
	sort.Slice(candidates, func(i, j int) bool { return candidates[i].branch < candidates[j].branch })
	removedWorktrees, removedBranches := []string{}, []string{}
	for _, item := range candidates {
		if _, err := git(root, "worktree", "remove", item.path); err != nil {
			return nil, executionWorkspaceGitError(err)
		}
		removedWorktrees = append(removedWorktrees, item.path)
		if _, err := git(root, "branch", "-d", item.branch); err != nil {
			return nil, executionWorkspaceGitError(err)
		}
		removedBranches = append(removedBranches, item.branch)
	}
	_, _ = git(root, "worktree", "prune")
	return map[string]any{
		"change": change, "status": "clean", "removed_worktrees": removedWorktrees,
		"removed_branches": removedBranches, "remaining": 0,
	}, nil
}

func executionWorkspaceRepositoryRoot(repo string, git func(string, ...string) (string, error)) (string, error) {
	root, err := safeRoot(repo)
	if err != nil {
		return "", workflowError("DIRTY_WORKSPACE", "o diretório não é uma raiz Git")
	}
	root, err = filepath.EvalSymlinks(root)
	if err != nil {
		return "", workflowError("DIRTY_WORKSPACE", "o diretório não é uma raiz Git")
	}
	root = filepath.Clean(root)
	discovered, err := git(root, "rev-parse", "--show-toplevel")
	if err != nil || strings.TrimSpace(discovered) == "" {
		return "", workflowError("DIRTY_WORKSPACE", "o diretório não é uma raiz Git")
	}
	discovered, err = filepath.Abs(strings.TrimSpace(discovered))
	if err != nil {
		return "", workflowError("DIRTY_WORKSPACE", "o diretório não é uma raiz Git")
	}
	discovered, err = filepath.EvalSymlinks(discovered)
	if err != nil {
		return "", workflowError("DIRTY_WORKSPACE", "o diretório não é uma raiz Git")
	}
	discovered = filepath.Clean(discovered)
	if discovered != root {
		return "", workflowError("DIRTY_WORKSPACE", "--repo deve apontar para "+discovered)
	}
	return root, nil
}

func executionWorkspaceIdentity(change, plan string) (string, string, error) {
	prefix := strings.SplitN(change, "-", 2)[0]
	if !executionChangePrefix.MatchString(prefix) {
		return "", "", workflowError("MODEL_MISMATCH", "change exige C seguido de três dígitos")
	}
	if !executionPlanID.MatchString(plan) {
		return "", "", workflowError("MODEL_MISMATCH", "plan exige P seguido de ao menos dois dígitos")
	}
	identity := strings.ToLower(prefix + "-" + plan)
	return identity, "bm/" + identity, nil
}

func executionWorkspaceCreate(root, change, plan, target string, dependencies executionWorkspaceDependencies) (map[string]any, error) {
	status, err := dependencies.git(root, "status", "--porcelain")
	if err != nil {
		return nil, executionWorkspaceGitError(err)
	}
	if status != "" {
		return nil, workflowError("DIRTY_WORKSPACE", "workspace de execução exige Git limpo")
	}
	pack, err := loadCoherencePackage(root, change)
	if err != nil {
		return nil, err
	}
	coherence := pack.contract
	if !oneOf(stateString(coherence["status"]), "approved", "approved_with_stale") {
		return nil, workflowError("COHERENCE_ERROR", "planejamento exige COHERENCE approved")
	}
	manifest, err := executionWorkspaceValidateApprovedPackage(pack)
	if err != nil {
		return nil, err
	}
	stalePlans, err := stringValues(coherence["stale_plans"], "stale_plans")
	if err != nil {
		return nil, workflowError("COHERENCE_ERROR", "stale_plans inválidos")
	}
	if containsString(stalePlans, plan) {
		return nil, workflowError("IMPACT_STALE", plan+" está stale")
	}
	contract, err := executionWorkspacePlan(pack.plans, plan)
	if err != nil {
		return nil, err
	}
	results, err := executionWorkspaceResults(pack.workspace, pack.directory)
	if err != nil {
		return nil, err
	}
	if _, completed := results[plan]; completed {
		return nil, workflowError("COHERENCE_ERROR", plan+" já foi concluído")
	}
	dependsOn, err := stringValues(contract.value["depends_on"], "depends_on")
	if err != nil {
		return nil, workflowError("MODEL_MISMATCH", err.Error())
	}
	missingDependencies := missingExecutionValues(dependsOn, func(value string) bool {
		_, exists := results[value]
		return exists
	})
	if len(missingDependencies) > 0 {
		return nil, workflowError("MISSING_PROVIDER", "dependências ainda não concluídas: "+strings.Join(missingDependencies, ", "))
	}
	effective, err := executionWorkspaceEffectiveModel(pack.current, pack.plans, results)
	if err != nil {
		return nil, err
	}
	consumes, err := stringValues(contract.value["consumes"], "consumes")
	if err != nil {
		return nil, workflowError("MODEL_MISMATCH", err.Error())
	}
	missingContracts := missingExecutionValues(consumes, func(value string) bool {
		return effective.hasComponent(value)
	})
	if len(missingContracts) > 0 {
		return nil, workflowError("MISSING_PROVIDER", "contratos consumidos ainda ausentes: "+strings.Join(missingContracts, ", "))
	}
	planPath, found := planFileForID(filepath.Join(pack.directory, "plans"), plan)
	if !found {
		return nil, workflowError("MODEL_MISMATCH", plan+" deve localizar exatamente um plano")
	}
	if err := pack.workspace.validateWorkspacePath(planPath); err != nil {
		return nil, workflowError("MODEL_MISMATCH", plan+" deve localizar exatamente um plano")
	}
	head, err := dependencies.git(root, "rev-parse", "HEAD")
	if err != nil {
		return nil, executionWorkspaceGitError(err)
	}
	if err := executionWorkspaceValidateCommittedPackage(root, pack, planPath, manifest, dependencies.git); err != nil {
		return nil, err
	}
	identity, branch, err := executionWorkspaceIdentity(filepath.Base(pack.directory), plan)
	if err != nil {
		return nil, err
	}
	destination, err := executionWorkspaceDestination(root, target, identity)
	if err != nil {
		return nil, err
	}
	if _, err := os.Lstat(destination); err == nil || !os.IsNotExist(err) {
		return nil, workflowError("DIRTY_WORKSPACE", "destino já existe: "+destination)
	}
	branches, err := dependencies.git(root, "for-each-ref", "--format=%(refname:short)", "refs/heads")
	if err != nil {
		return nil, executionWorkspaceGitError(err)
	}
	if containsString(nonEmptyLines(branches), branch) {
		return nil, workflowError("DIRTY_WORKSPACE", "branch já existe: "+branch)
	}
	if err := os.MkdirAll(filepath.Dir(destination), 0o755); err != nil {
		return nil, workflowError("DIRTY_WORKSPACE", err.Error())
	}
	rollback := func() {
		if _, statErr := os.Lstat(destination); statErr == nil {
			_, _ = dependencies.git(root, "worktree", "remove", "--force", destination)
		}
		_, _ = dependencies.git(root, "branch", "-D", branch)
	}
	if _, err := dependencies.git(root, "worktree", "add", "-b", branch, destination, head); err != nil {
		rollback()
		return nil, executionWorkspaceGitError(err)
	}
	metadata := map[string]any{
		"schema_version": 1, "source_repo": root, "change": filepath.Base(pack.directory),
		"plan": plan, "branch": branch, "base_commit": head,
		"coherence_digest": coherence["digest"], "created_at": utcNow(),
	}
	if err := dependencies.persist(newMethodWorkspace(destination), identity, metadata, plan); err != nil {
		rollback()
		return nil, err
	}
	return map[string]any{
		"workspace": destination, "branch": branch, "change": filepath.Base(pack.directory),
		"plan": plan, "base_commit": head,
	}, nil
}

func executionWorkspaceValidateApprovedPackage(pack coherencePackage) (map[string]string, error) {
	if pack.planningContract < 2 {
		return map[string]string{}, nil
	}
	findings, findingsOK := pack.contract["findings"].([]any)
	semantic, semanticOK := pack.contract["semantic"].(map[string]any)
	if !findingsOK || !semanticOK {
		return nil, workflowError("COHERENCE_ERROR", "pacote aprovado está incompleto")
	}
	manifest, err := coherenceArtifactManifest(pack.workspace, pack.directory)
	if err != nil {
		return nil, err
	}
	spec := map[string]any{}
	if pack.specContract != 0 {
		spec, err = loadModelSpecPackage(pack.workspace, pack.directory, pack.contract)
		if err != nil {
			return nil, err
		}
	}
	if !coherenceManifestEqual(pack.contract["artifact_manifest"], manifest) ||
		stateString(pack.contract["review_input_digest"]) != coherenceReviewDigest(pack.planningContract, manifest, spec) ||
		stateString(pack.contract["digest"]) != coherencePackageDigest(pack.current, pack.expected, pack.plans, findings, semantic, pack.planningContract, manifest, spec) {
		return nil, workflowError("STALE_EVIDENCE", "pacote aprovado mudou depois do checkpoint")
	}
	for key, expected := range spec {
		if key == "spec_contract" {
			if stateInt(pack.contract[key]) != stateInt(expected) {
				return nil, workflowError("STALE_EVIDENCE", "pacote aprovado mudou depois do checkpoint")
			}
		} else if stateString(pack.contract[key]) != stateString(expected) {
			return nil, workflowError("STALE_EVIDENCE", "pacote aprovado mudou depois do checkpoint")
		}
	}
	return manifest, nil
}

func executionWorkspacePlan(plans []planContract, identifier string) (planContract, error) {
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

func executionWorkspaceResults(workspace methodWorkspace, directory string) (map[string]map[string]any, error) {
	paths, _ := filepath.Glob(filepath.Join(directory, "results", "P*.md"))
	sort.Strings(paths)
	results := map[string]map[string]any{}
	for _, path := range paths {
		if err := workspace.validateWorkspacePath(path); err != nil {
			return nil, workflowError("DOCVIVA_INCOMPLETE", "resultado inválido: "+filepath.Base(path))
		}
		value, err := readStructuredFrontmatter(path)
		if err != nil {
			return nil, workflowError("DOCVIVA_INCOMPLETE", err.Error())
		}
		plan := stateString(value["plan"])
		if plan == "" || results[plan] != nil {
			return nil, workflowError("DOCVIVA_INCOMPLETE", "resultado inválido: "+filepath.Base(path))
		}
		results[plan] = value
	}
	return results, nil
}

func executionWorkspaceEffectiveModel(current projectModel, plans []planContract, results map[string]map[string]any) (projectModel, error) {
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

func missingExecutionValues(values []string, present func(string) bool) []string {
	missing := []string{}
	seen := map[string]bool{}
	for _, value := range values {
		if !present(value) && !seen[value] {
			missing = append(missing, value)
			seen[value] = true
		}
	}
	sort.Strings(missing)
	return missing
}

func executionWorkspaceValidateCommittedPackage(root string, pack coherencePackage, planPath string, manifest map[string]string, git func(string, ...string) (string, error)) error {
	required := []string{filepath.Join(pack.directory, "COHERENCE.md")}
	if pack.planningContract >= 2 {
		keys := make([]string, 0, len(manifest))
		for relative := range manifest {
			keys = append(keys, relative)
		}
		sort.Strings(keys)
		for _, relative := range keys {
			required = append(required, filepath.Join(pack.directory, filepath.FromSlash(relative)))
		}
	} else {
		required = append(required, filepath.Join(pack.directory, "SYSTEM_MODEL.md"), planPath)
	}
	seen := map[string]bool{}
	for _, path := range required {
		if err := pack.workspace.validateWorkspacePath(path); err != nil {
			return workflowError("COHERENCE_ERROR", "pacote contém path inválido")
		}
		relative, err := filepath.Rel(root, path)
		if err != nil || relative == ".." || strings.HasPrefix(relative, ".."+string(filepath.Separator)) {
			return workflowError("COHERENCE_ERROR", "pacote contém path inválido")
		}
		relative = filepath.ToSlash(relative)
		if seen[relative] {
			continue
		}
		seen[relative] = true
		if _, err := git(root, "ls-files", "--error-unmatch", relative); err != nil {
			return workflowError("COHERENCE_ERROR", "pacote não commitado: "+relative)
		}
		committed, err := git(root, "show", "HEAD:"+relative)
		if err != nil {
			return workflowError("COHERENCE_ERROR", "pacote não commitado: "+relative)
		}
		info, err := os.Lstat(path)
		if err != nil || info.Mode()&os.ModeSymlink != 0 || !info.Mode().IsRegular() {
			return workflowError("COHERENCE_ERROR", "pacote diverge do HEAD: "+relative)
		}
		content, err := os.ReadFile(path)
		if err != nil || committed != strings.TrimRight(string(content), "\n") {
			return workflowError("COHERENCE_ERROR", "pacote diverge do HEAD: "+relative)
		}
	}
	return nil
}

func executionWorkspaceDestination(root, target, identity string) (string, error) {
	var destination string
	if target == "" {
		destination = filepath.Join(filepath.Dir(root), ".bianchini-worktrees", filepath.Base(root), identity)
	} else {
		if err := rejectForeignNamespace(target, "target"); err != nil {
			return "", err
		}
		destination = target
	}
	resolved, err := resolveExecutionDestination(destination)
	if err != nil {
		return "", workflowError("DIRTY_WORKSPACE", err.Error())
	}
	relative, err := filepath.Rel(root, resolved)
	if err == nil && relative != ".." && !strings.HasPrefix(relative, ".."+string(filepath.Separator)) && !filepath.IsAbs(relative) {
		return "", workflowError("DIRTY_WORKSPACE", "destino do worktree deve ficar fora do repo")
	}
	return resolved, nil
}

func resolveExecutionDestination(path string) (string, error) {
	absolute, err := filepath.Abs(path)
	if err != nil {
		return "", err
	}
	absolute = filepath.Clean(absolute)
	probe, suffix := absolute, []string{}
	for {
		if _, err := os.Lstat(probe); err == nil {
			resolved, resolveErr := filepath.EvalSymlinks(probe)
			if resolveErr != nil {
				return "", resolveErr
			}
			for index := len(suffix) - 1; index >= 0; index-- {
				resolved = filepath.Join(resolved, suffix[index])
			}
			return filepath.Clean(resolved), nil
		} else if !os.IsNotExist(err) {
			return "", err
		}
		parent := filepath.Dir(probe)
		if parent == probe {
			return absolute, nil
		}
		suffix = append(suffix, filepath.Base(probe))
		probe = parent
	}
}

func persistExecutionWorkspace(workspace methodWorkspace, identity string, metadata map[string]any, plan string) error {
	encoded, err := json.MarshalIndent(metadata, "", "  ")
	if err != nil {
		return workflowError("DIRTY_WORKSPACE", err.Error())
	}
	encoded = append(encoded, '\n')
	if err := workspace.atomicWrite(filepath.Join(workspace.runtime, "workspace-"+identity+".json"), encoded); err != nil {
		return err
	}
	state, err := workspace.readState()
	if err != nil {
		return err
	}
	change := stateString(metadata["change"])
	state["current_unit"], state["status"] = plan, "executing"
	state["active_work"] = map[string]any{"kind": "change", "id": change, "status": "executing"}
	state["next_action"], state["updated_at"] = "Executar "+plan+" neste workspace isolado.", utcNow()
	return workspace.writeState(state, "# Estado atual")
}

func executionWorkspaceLocate(root, change, plan string, resume bool, git func(string, ...string) (string, error)) (map[string]any, error) {
	identity, branch, err := executionWorkspaceIdentity(change, plan)
	if err != nil {
		return nil, err
	}
	output, err := git(root, "worktree", "list", "--porcelain")
	if err != nil {
		return nil, executionWorkspaceGitError(err)
	}
	matches := []map[string]string{}
	for _, record := range parseExecutionWorktrees(output) {
		if record["branch"] == "refs/heads/"+branch {
			matches = append(matches, record)
		}
	}
	if len(matches) != 1 {
		return nil, workflowError("DIRTY_WORKSPACE", "workspace não localizado para "+identity)
	}
	path := filepath.Clean(matches[0]["worktree"])
	result := map[string]any{"workspace": path, "branch": branch, "change": change, "plan": plan}
	if resume {
		workspace := newMethodWorkspace(path)
		metadataPath := filepath.Join(workspace.runtime, "workspace-"+identity+".json")
		if err := workspace.validateWorkspacePath(metadataPath); err != nil {
			return nil, workflowError("DIRTY_WORKSPACE", "metadados do workspace estão ausentes")
		}
		metadata, err := readExecutionWorkspaceMetadata(metadataPath)
		if err != nil {
			return nil, err
		}
		result["metadata"] = metadata
	}
	return result, nil
}

func parseExecutionWorktrees(output string) []map[string]string {
	records := []map[string]string{}
	current := map[string]string{}
	for _, line := range append(strings.Split(output, "\n"), "") {
		if line == "" {
			if len(current) > 0 {
				records = append(records, current)
				current = map[string]string{}
			}
			continue
		}
		key, value, found := strings.Cut(line, " ")
		if !found {
			value = ""
		}
		current[key] = value
	}
	return records
}

func executionWorkspaceCheck(root string, git func(string, ...string) (string, error)) (map[string]any, error) {
	branch, err := git(root, "branch", "--show-current")
	if err != nil {
		return nil, executionWorkspaceGitError(err)
	}
	if !executionBranch.MatchString(branch) {
		return nil, workflowError("DIRTY_WORKSPACE", "branch de execução 0.4 inválida")
	}
	paths, _ := filepath.Glob(filepath.Join(root, ".bianchini", ".runtime", "workspace-*.json"))
	sort.Strings(paths)
	if len(paths) != 1 {
		return nil, workflowError("DIRTY_WORKSPACE", "metadados de execução ausentes ou ambíguos")
	}
	if err := newMethodWorkspace(root).validateWorkspacePath(paths[0]); err != nil {
		return nil, workflowError("DIRTY_WORKSPACE", "metadados de execução ausentes ou ambíguos")
	}
	metadata, err := readExecutionWorkspaceMetadata(paths[0])
	if err != nil {
		return nil, err
	}
	return map[string]any{"valid": true, "branch": branch, "workspace": root, "metadata": metadata}, nil
}

func readExecutionWorkspaceMetadata(path string) (map[string]any, error) {
	info, err := os.Lstat(path)
	if err != nil || info.Mode()&os.ModeSymlink != 0 || !info.Mode().IsRegular() {
		return nil, workflowError("DIRTY_WORKSPACE", "metadados do workspace estão ausentes")
	}
	if info.Size() > stateLimitBytes {
		return nil, workflowError("DIRTY_WORKSPACE", "metadados do workspace são inválidos")
	}
	content, err := os.ReadFile(path)
	if err != nil {
		return nil, workflowError("DIRTY_WORKSPACE", "metadados do workspace estão ausentes")
	}
	metadata := map[string]any{}
	if err := json.Unmarshal(content, &metadata); err != nil {
		return nil, workflowError("DIRTY_WORKSPACE", "metadados do workspace são inválidos")
	}
	return metadata, nil
}

func executionWorkspaceGitCommand(root string, args ...string) (string, error) {
	command := exec.Command("git", args...)
	command.Dir = root
	output, err := command.CombinedOutput()
	if err != nil {
		message := strings.TrimSpace(string(output))
		if message == "" {
			message = "comando Git falhou"
		}
		return "", fmt.Errorf("%s", message)
	}
	return strings.TrimSpace(string(output)), nil
}

func executionWorkspaceGitError(err error) error {
	message := strings.TrimSpace(err.Error())
	if message == "" {
		message = "comando Git falhou"
	}
	return workflowError("DIRTY_WORKSPACE", message)
}
