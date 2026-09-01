package gokernel

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"io/fs"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
)

var quickIDPattern = regexp.MustCompile(`^Q[0-9]{3}-[a-z0-9]+(?:-[a-z0-9]+)*$`)

func runDirectLifecycle(action string, args []string) (any, error) {
	flags, err := parseFlags(args, directValueFlags, directBooleanFlags)
	if err != nil {
		return nil, err
	}
	if action == "start" {
		if lastValue(flags, "--objective") == "" || lastValue(flags, "--scope") == "" {
			return nil, userError("direct start exige --objective e --scope")
		}
		if len(flags.values["--acceptance"]) == 0 || len(flags.values["--verification"]) == 0 {
			return nil, userError("direct start exige ao menos um --acceptance e um --verification")
		}
		return directWorkflowStart(flags)
	}
	repo, err := workflowRepo(flags, false)
	if err != nil {
		return nil, err
	}
	switch action {
	case "status":
		return directWorkflowStatus(repo, lastValue(flags, "--slug"))
	case "checkpoint":
		if lastValue(flags, "--slug") == "" || lastValue(flags, "--checkpoint") == "" || lastValue(flags, "--next-action") == "" {
			return nil, userError("direct checkpoint exige --slug, --checkpoint e --next-action")
		}
		return directWorkflowCheckpoint(repo, flags)
	case "finish":
		if lastValue(flags, "--slug") == "" || lastValue(flags, "--status") == "" || lastValue(flags, "--next-action") == "" {
			return nil, userError("direct finish exige --slug, --status e --next-action")
		}
		return directWorkflowFinish(repo, flags)
	default:
		return nil, argparseError(fmt.Sprintf("argument action: invalid choice: '%s'", action))
	}
}

func workflowRepo(flags parsedFlags, create bool) (string, error) {
	repo := lastValue(flags, "--repo")
	if repo == "" {
		var err error
		repo, err = os.Getwd()
		if err != nil {
			return "", workflowError("DIRTY_WORKSPACE", "o diretório não é uma raiz Git")
		}
	}
	root, err := repositoryRoot(repo)
	if err != nil {
		return "", err
	}
	workspace := newMethodWorkspace(root)
	if _, err := workspace.readState(); err == nil {
		return root, nil
	}
	if !create {
		if _, statErr := os.Lstat(workspace.dir); statErr == nil {
			return "", workflowError("DOCVIVA_INCOMPLETE", ".bianchini existe sem STATE.md válido")
		}
		return "", workflowError("DOCVIVA_INCOMPLETE", "Bianchini Method 0.4 não iniciado; execute model init")
	}
	if _, err := initializeModelWorkspace(root); err != nil {
		return "", err
	}
	return root, nil
}

func directWorkflowStart(flags parsedFlags) (map[string]any, error) {
	repo, err := workflowRepo(flags, true)
	if err != nil {
		return nil, err
	}
	workspace := newMethodWorkspace(repo)
	state, err := workspace.readState()
	if err != nil {
		return nil, err
	}
	if state["active_work"] != nil {
		return nil, workflowError("COHERENCE_ERROR", "já existe trabalho ativo")
	}
	risk, err := classifyDirect(flags)
	if err != nil {
		return nil, err
	}
	identifier, err := allocateWorkflowID(workspace, "quick")
	if err != nil {
		return nil, err
	}
	slug, err := modelSlug(lastValue(flags, "--objective"))
	if err != nil {
		return nil, err
	}
	workID := identifier + "-" + slug
	directory := filepath.Join(workspace.dir, "quick", workID)
	if err := workspace.mkdirAll(directory); err != nil {
		return nil, err
	}
	modelBefore, err := readJSONFrontmatter(workspace.currentMod, "SYSTEM_MODEL atual")
	if err != nil {
		return nil, err
	}
	docBefore, err := snapshotDocViva(repo)
	if err != nil {
		return nil, err
	}
	baseHead, gitErr := workflowGit(repo, "rev-parse", "--verify", "HEAD")
	if gitErr != nil {
		baseHead = "UNBORN"
	}
	required := requiredDirectGuards(risk, flags)
	guards := uniqueSorted(flags.values["--guard"])
	missing := differenceSorted(required, guards)
	brief := map[string]any{
		"schema_version": 1, "docviva_contract": 1, "docviva_before": docBefore,
		"id": workID, "base_head": baseHead, "model_before": modelBefore,
		"status": "active", "objective": lastValue(flags, "--objective"),
		"scope": lastValue(flags, "--scope"), "acceptance": flags.values["--acceptance"],
		"verification": flags.values["--verification"], "risk": risk, "guards": guards,
		"required_guards": required, "missing_guards": missing,
		"flow":                           map[string]any{"webhook": flags.booleans["--webhook-flow"], "payment": flags.booleans["--payment-flow"]},
		"production_checkpoint_required": stateInt(stateObject(risk["dimensions"])["external_effect"]) == 2 || stateInt(stateObject(risk["dimensions"])["money"]) == 2,
		"created_at":                     utcNow(),
	}
	unsigned, err := canonicalJSON(brief)
	if err != nil {
		return nil, workflowError("MODEL_MISMATCH", err.Error())
	}
	brief["digest"] = sha256Bytes(unsigned)
	briefDocument, _ := frontmatterDocument(brief, "# Quick "+workID+"\n\n"+lastValue(flags, "--objective"), false)
	progress := map[string]any{"schema_version": 1, "id": workID, "status": "active", "events": []any{}}
	progressDocument, _ := frontmatterDocument(progress, "# Progresso\n\nNenhum checkpoint registrado.", false)
	if err := workspace.atomicWrite(filepath.Join(directory, "BRIEF.md"), briefDocument); err != nil {
		return nil, err
	}
	if err := workspace.atomicWrite(filepath.Join(directory, "PROGRESS.md"), progressDocument); err != nil {
		return nil, err
	}
	next := "Executar e verificar " + workID + "."
	if len(missing) > 0 {
		next = "Completar guards ausentes durante a execução: " + strings.Join(missing, ", ")
	}
	if err := updateWorkflowState(workspace, map[string]any{
		"active_work": map[string]any{"kind": "quick", "id": workID, "status": "active"},
		"status":      "active", "next_action": next,
	}); err != nil {
		return nil, err
	}
	result := cloneMap(brief)
	result["path"] = directory
	return result, nil
}

func requiredDirectGuards(risk map[string]any, flags parsedFlags) []string {
	dimensions := stateObject(risk["dimensions"])
	required := append([]string(nil), stringsFromAny(risk["additional_guards"])...)
	if stateInt(dimensions["external_effect"]) > 0 {
		required = append(required, "official_docs", "timeout_recovery", "rollback", "sandbox")
	}
	if stateInt(dimensions["migration"]) > 0 {
		required = append(required, "rollback")
	}
	if stateInt(dimensions["concurrency"]) > 0 {
		required = append(required, "idempotency", "deduplication", "replay_order")
	}
	if stateInt(dimensions["money"]) > 0 {
		required = append(required, "source_of_truth", "idempotency", "persistence", "reconciliation", "sandbox")
	}
	if stateString(risk["route"]) == "protected" {
		required = append(required, "local_contract")
	}
	if flags.booleans["--webhook-flow"] {
		required = append(required, "authenticity", "deduplication", "replay_order", "persistence")
	}
	if flags.booleans["--payment-flow"] {
		required = append(required, "source_of_truth", "idempotency", "timeout_recovery", "persistence", "reconciliation")
	}
	return uniqueSorted(required)
}

func directWorkflowStatus(repo, workID string) (map[string]any, error) {
	workspace := newMethodWorkspace(repo)
	if _, err := workspace.readState(); err != nil {
		return nil, err
	}
	if workID == "" {
		entries, err := os.ReadDir(filepath.Join(workspace.dir, "quick"))
		if err != nil {
			return nil, workflowError("MODEL_MISMATCH", err.Error())
		}
		items := make([]any, 0)
		for _, entry := range entries {
			if !entry.IsDir() || !quickIDPattern.MatchString(entry.Name()) || entry.Type()&os.ModeSymlink != 0 {
				continue
			}
			status, err := directWorkflowStatus(repo, entry.Name())
			if err != nil {
				return nil, err
			}
			items = append(items, map[string]any{"id": status["id"], "status": status["status"], "route": status["route"]})
		}
		return map[string]any{"items": items}, nil
	}
	directory, err := quickDirectory(workspace, workID)
	if err != nil {
		return nil, err
	}
	brief, err := readJSONFrontmatter(filepath.Join(directory, "BRIEF.md"), "brief do quick")
	if err != nil {
		return nil, err
	}
	status := stateString(brief["status"])
	if result, resultErr := readJSONFrontmatter(filepath.Join(directory, "RESULT.md"), "resultado do quick"); resultErr == nil {
		status = stateString(result["status"])
	}
	return map[string]any{
		"id": workID, "status": status, "route": stateString(stateObject(brief["risk"])["route"]),
		"missing_guards": stringsFromAny(brief["missing_guards"]), "path": directory,
	}, nil
}

func directWorkflowCheckpoint(repo string, flags parsedFlags) (map[string]any, error) {
	workspace := newMethodWorkspace(repo)
	workID := lastValue(flags, "--slug")
	directory, err := quickDirectory(workspace, workID)
	if err != nil {
		return nil, err
	}
	if regularFile(filepath.Join(directory, "RESULT.md")) {
		return nil, workflowError("ORDER_VIOLATION", "quick terminal é imutável")
	}
	progressPath := filepath.Join(directory, "PROGRESS.md")
	progress, err := readJSONFrontmatter(progressPath, "progresso do quick")
	if err != nil {
		return nil, err
	}
	brief, err := readJSONFrontmatter(filepath.Join(directory, "BRIEF.md"), "brief do quick")
	if err != nil {
		return nil, err
	}
	fingerprint, err := workflowTreeFingerprint(repo)
	if err != nil {
		return nil, err
	}
	event := map[string]any{
		"summary":       strings.TrimSpace(lastValue(flags, "--checkpoint")),
		"changed_files": uniqueSorted(flags.values["--changed-file"]), "commands": flags.values["--command"],
		"evidence": flags.values["--evidence"], "blockers": flags.values["--blocker"],
		"guards": uniqueSorted(flags.values["--guard"]), "fingerprint": fingerprint,
		"at": utcNow(), "brief_digest": brief["digest"],
	}
	events := stateArray(progress["events"])
	events = append(events, event)
	finalRisk, missing, err := directFinalRisk(repo, brief, events)
	if err != nil {
		return nil, err
	}
	event["risk"] = finalRisk
	event["missing_guards"] = missing
	progress["events"] = events
	progress["updated_at"] = utcNow()
	document, _ := frontmatterDocument(progress, "# Progresso de "+workID+"\n\n"+strings.TrimSpace(lastValue(flags, "--checkpoint")), false)
	if err := workspace.atomicWrite(progressPath, document); err != nil {
		return nil, err
	}
	if err := updateWorkflowState(workspace, map[string]any{
		"next_action": lastValue(flags, "--next-action"), "blockers": anyStrings(flags.values["--blocker"]),
		"active_work": map[string]any{"kind": "quick", "id": workID, "status": "active"},
	}); err != nil {
		return nil, err
	}
	return map[string]any{"id": workID, "status": "active", "checkpoint": len(events), "risk": finalRisk, "missing_guards": missing}, nil
}

func directFinalRisk(repo string, brief map[string]any, events []any) (map[string]any, []string, error) {
	initial := stateObject(brief["risk"])
	if stateString(initial["risk_contract"]) != "quick-risk-floor-v1" {
		return initial, stringsFromAny(brief["missing_guards"]), nil
	}
	inputs := stateObject(initial["risk_inputs"])
	inputFlags := stateObject(inputs["flags"])
	flags := parsedFlags{values: map[string][]string{}, booleans: map[string]bool{}}
	for key, flag := range map[string]string{"scope": "--scope-score", "external_effect": "--external-effect-score", "migration": "--migration-score", "concurrency": "--concurrency-score", "money": "--money-score"} {
		flags.values[flag] = []string{fmt.Sprintf("%d", stateInt(inputFlags[key]))}
	}
	flags.booleans["--payment-flow"] = inputFlags["payment"] == true
	flags.booleans["--webhook-flow"] = inputFlags["webhook"] == true
	paths := stringsFromAny(inputs["declared_paths"])
	available := stringsFromAny(brief["guards"])
	for _, raw := range events {
		event := stateObject(raw)
		paths = append(paths, stringsFromAny(event["changed_files"])...)
		available = append(available, stringsFromAny(event["guards"])...)
	}
	diffPaths, err := workflowDiffPaths(repo, stateString(brief["base_head"]))
	if err != nil {
		return nil, nil, err
	}
	paths = append(paths, diffPaths...)
	flags.values["--changed-file"] = uniqueSorted(paths)
	assessed, err := classifyDirect(flags)
	if err != nil {
		return nil, nil, err
	}
	result := map[string]any{
		"schema_version": 1, "workflow": "quick", "risk_contract": "quick-risk-floor-v1",
		"declared_score": assessed["declared_score"], "derived_floor": assessed["derived_floor"],
		"diff_floor": assessed["diff_floor"], "initial_floor": assessed["initial_floor"],
		"effective_score": assessed["effective_score"], "route": assessed["route"],
		"reasons": assessed["reasons"], "additional_guards": assessed["additional_guards"],
		"phase": "finish", "start_floor": initial["derived_floor"],
	}
	startGuards := stringsFromAny(initial["additional_guards"])
	result["reclassified"] = stateInt(assessed["derived_floor"]) > stateInt(initial["derived_floor"]) || len(differenceSorted(stringsFromAny(assessed["additional_guards"]), startGuards)) > 0
	required := append(stringsFromAny(brief["required_guards"]), stringsFromAny(assessed["additional_guards"])...)
	return result, differenceSorted(uniqueSorted(required), uniqueSorted(available)), nil
}

func directWorkflowFinish(repo string, flags parsedFlags) (map[string]any, error) {
	workspace := newMethodWorkspace(repo)
	workID := lastValue(flags, "--slug")
	directory, err := quickDirectory(workspace, workID)
	if err != nil {
		return nil, err
	}
	status := lastValue(flags, "--status")
	if status != "completed" && status != "blocked" {
		return nil, workflowError("MODEL_MISMATCH", "status terminal de quick inválido")
	}
	resultPath := filepath.Join(directory, "RESULT.md")
	if regularFile(resultPath) {
		return nil, workflowError("ORDER_VIOLATION", "quick terminal é imutável")
	}
	brief, err := readJSONFrontmatter(filepath.Join(directory, "BRIEF.md"), "brief do quick")
	if err != nil {
		return nil, err
	}
	var finalRisk map[string]any
	var docViva any
	if status == "completed" {
		storedDigest := stateString(brief["digest"])
		unsigned := cloneMap(brief)
		delete(unsigned, "digest")
		encoded, _ := canonicalJSON(unsigned)
		if storedDigest != sha256Bytes(encoded) {
			return nil, workflowError("STALE_EVIDENCE", "BRIEF.md mudou após a classificação")
		}
		if brief["production_checkpoint_required"] == true && !flags.booleans["--production-authorized"] {
			return nil, workflowError("EXTERNAL_AUTHORITY_REQUIRED", "efeito real exige checkpoint explícito")
		}
		verification := append(append([]string(nil), flags.values["--verification"]...), flags.values["--evidence"]...)
		if len(verification) == 0 {
			return nil, workflowError("STALE_EVIDENCE", "conclusão exige evidência de verificação")
		}
		progress, err := readJSONFrontmatter(filepath.Join(directory, "PROGRESS.md"), "progresso do quick")
		if err != nil {
			return nil, err
		}
		events := stateArray(progress["events"])
		if len(events) == 0 {
			return nil, workflowError("STALE_EVIDENCE", "conclusão exige checkpoint verificado")
		}
		last := stateObject(events[len(events)-1])
		if stateString(last["brief_digest"]) != storedDigest {
			return nil, workflowError("STALE_EVIDENCE", "checkpoint pertence a outro brief")
		}
		fingerprint, err := workflowTreeFingerprint(repo)
		if err != nil {
			return nil, err
		}
		if stateString(last["fingerprint"]) != fingerprint {
			return nil, workflowError("STALE_EVIDENCE", "código mudou após o último checkpoint")
		}
		var missing []string
		finalRisk, missing, err = directFinalRisk(repo, brief, events)
		if err != nil {
			return nil, err
		}
		if len(missing) > 0 {
			return nil, workflowError("MISSING_GUARD", "guards ausentes: "+strings.Join(missing, ", "))
		}
		kind, outcome := lastValue(flags, "--docviva-kind"), lastValue(flags, "--docviva-outcome")
		if kind == "" || outcome == "" {
			return nil, workflowError("DOCVIVA_INCOMPLETE", "quick concluído exige classificação DocViva explícita")
		}
		docViva, err = verifyDocViva(repo, stringMap(brief["docviva_before"]), kind, outcome, flags.values["--docviva-artifact"], lastValue(flags, "--docviva-justification"), docVivaKindRequired(kind))
		if err != nil {
			return nil, err
		}
	} else {
		if len(flags.values["--blocker"]) == 0 {
			return nil, workflowError("MODEL_MISMATCH", "quick bloqueado exige motivo")
		}
		finalRisk = stateObject(brief["risk"])
	}
	fingerprint, err := workflowTreeFingerprint(repo)
	if err != nil {
		return nil, err
	}
	verification := append(append([]string(nil), flags.values["--verification"]...), flags.values["--evidence"]...)
	result := map[string]any{
		"schema_version": 1, "id": workID, "status": status, "behaviors": flags.values["--behavior"],
		"verification": verification, "limitations": flags.values["--limitation"], "blockers": flags.values["--blocker"],
		"production_authorized": flags.booleans["--production-authorized"], "docviva": docViva,
		"risk": finalRisk, "fingerprint": fingerprint, "finished_at": utcNow(),
	}
	document, _ := frontmatterDocument(result, "# Resultado de "+workID+"\n\nStatus: "+status+".", false)
	if err := workspace.atomicWrite(resultPath, document); err != nil {
		return nil, err
	}
	stateStatus := "idle"
	if status == "blocked" {
		stateStatus = "blocked"
	}
	if err := updateWorkflowState(workspace, map[string]any{
		"active_work": nil, "current_unit": nil, "status": stateStatus,
		"blockers":       anyStrings(flags.values["--blocker"]),
		"last_completed": map[string]any{"kind": "quick", "id": workID, "status": status},
		"next_action":    lastValue(flags, "--next-action"),
	}); err != nil {
		return nil, err
	}
	return map[string]any{"id": workID, "status": status, "path": resultPath, "docviva": docViva, "risk": finalRisk}, nil
}

func quickDirectory(workspace methodWorkspace, workID string) (string, error) {
	if !quickIDPattern.MatchString(workID) {
		return "", workflowError("MODEL_MISMATCH", "ID de quick inválido")
	}
	directory, err := workspace.confined(filepath.Join(".bianchini", "quick", workID))
	if err != nil {
		return "", err
	}
	if err := workspace.validateWorkspacePath(directory); err != nil {
		return "", err
	}
	info, err := os.Lstat(directory)
	if err != nil || info.Mode()&os.ModeSymlink != 0 || !info.IsDir() {
		return "", workflowError("MODEL_MISMATCH", "quick não encontrado: "+workID)
	}
	return directory, nil
}

func allocateWorkflowID(workspace methodWorkspace, kind string) (string, error) {
	prefix, width := "", 0
	switch kind {
	case "quick":
		prefix, width = "Q", 3
	case "debug":
		prefix, width = "D", 3
	default:
		return "", workflowError("MODEL_MISMATCH", "tipo de ID desconhecido: "+kind)
	}
	if err := workspace.mkdirAll(workspace.runtime); err != nil {
		return "", err
	}
	countersPath := filepath.Join(workspace.runtime, "id-counters.json")
	counters := map[string]any{}
	if content, err := os.ReadFile(countersPath); err == nil {
		loaded, decodeErr := decodeJSONObject(content)
		if decodeErr != nil {
			return "", workflowError("MODEL_MISMATCH", "registro de IDs inválido")
		}
		counters = loaded
	}
	largest := 0
	pattern := regexp.MustCompile("^" + prefix + `([0-9]+)(?:\b|[-_.])`)
	err := filepath.WalkDir(workspace.dir, func(path string, entry fs.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if entry.Type()&os.ModeSymlink != 0 {
			if entry.IsDir() {
				return filepath.SkipDir
			}
			return nil
		}
		match := pattern.FindStringSubmatch(entry.Name())
		if len(match) == 2 {
			var value int
			_, _ = fmt.Sscanf(match[1], "%d", &value)
			largest = maxInt(largest, value)
		}
		return nil
	})
	if err != nil {
		return "", workflowError("MODEL_MISMATCH", err.Error())
	}
	value := maxInt(largest, stateInt(counters[kind])) + 1
	counters[kind] = value
	encoded, _ := canonicalJSON(counters)
	if err := workspace.atomicWrite(countersPath, append(encoded, '\n')); err != nil {
		return "", err
	}
	return fmt.Sprintf("%s%0*d", prefix, width, value), nil
}

func updateWorkflowState(workspace methodWorkspace, changes map[string]any) error {
	state, err := workspace.readState()
	if err != nil {
		return err
	}
	for key, value := range changes {
		state[key] = value
	}
	state["updated_at"] = utcNow()
	return workspace.writeState(state, "# Estado atual\n\nEste arquivo é um índice compacto. Siga os ponteiros para detalhes.")
}

func workflowGit(repo string, args ...string) (string, error) {
	command := exec.Command("git", args...)
	command.Dir = repo
	output, err := command.CombinedOutput()
	if err != nil {
		return "", fmt.Errorf("git %s: %s", strings.Join(args, " "), strings.TrimSpace(string(output)))
	}
	return strings.TrimSpace(string(output)), nil
}

func workflowTreeFingerprint(repo string) (string, error) {
	head, err := workflowGit(repo, "rev-parse", "--verify", "HEAD")
	var diff string
	if err == nil {
		diff, err = workflowGit(repo, "diff", "--binary", "HEAD", "--", ".", ":(exclude).bianchini", ":(exclude).planning")
	} else {
		head = "UNBORN"
		diff, err = workflowGit(repo, "diff", "--binary", "--", ".", ":(exclude).bianchini", ":(exclude).planning")
	}
	if err != nil {
		return "", workflowError("DIRTY_WORKSPACE", err.Error())
	}
	untracked, err := workflowGit(repo, "ls-files", "--others", "--exclude-standard", "--", ".", ":(exclude).bianchini", ":(exclude).planning")
	if err != nil {
		return "", workflowError("DIRTY_WORKSPACE", err.Error())
	}
	digest := sha256.New()
	_, _ = digest.Write([]byte(head + "\n" + diff))
	paths := nonEmptyLines(untracked)
	sort.Strings(paths)
	for _, relative := range paths {
		if err := validateRiskPath(relative); err != nil {
			return "", workflowError("STALE_EVIDENCE", "arquivo não rastreado escapou do repo")
		}
		path := filepath.Join(repo, filepath.FromSlash(relative))
		info, statErr := os.Lstat(path)
		if statErr != nil || info.Mode()&os.ModeSymlink != 0 || !info.Mode().IsRegular() {
			continue
		}
		content, readErr := os.ReadFile(path)
		if readErr != nil {
			return "", workflowError("STALE_EVIDENCE", readErr.Error())
		}
		_, _ = digest.Write([]byte(relative))
		fileDigest := sha256.Sum256(content)
		_, _ = digest.Write(fileDigest[:])
	}
	return hex.EncodeToString(digest.Sum(nil)), nil
}

func workflowDiffPaths(repo, baseHead string) ([]string, error) {
	args := []string{"diff", "--name-only"}
	if baseHead != "" && baseHead != "UNBORN" {
		if _, err := workflowGit(repo, "rev-parse", "--verify", baseHead+"^{commit}"); err != nil {
			return nil, workflowError("STALE_EVIDENCE", "base Git do quick não pertence ao HEAD atual")
		}
		command := exec.Command("git", "merge-base", "--is-ancestor", baseHead, "HEAD")
		command.Dir = repo
		if err := command.Run(); err != nil {
			return nil, workflowError("STALE_EVIDENCE", "base Git do quick não pertence ao HEAD atual")
		}
		args = append(args, baseHead)
	} else if baseHead != "UNBORN" {
		if _, err := workflowGit(repo, "rev-parse", "--verify", "HEAD"); err == nil {
			args = append(args, "HEAD")
		}
	}
	args = append(args, "--", ".", ":(exclude).bianchini", ":(exclude).planning")
	tracked, err := workflowGit(repo, args...)
	if err != nil {
		return nil, workflowError("DIRTY_WORKSPACE", err.Error())
	}
	paths := nonEmptyLines(tracked)
	if baseHead == "UNBORN" {
		if _, err := workflowGit(repo, "rev-parse", "--verify", "HEAD"); err == nil {
			listed, listErr := workflowGit(repo, "ls-files", "--", ".", ":(exclude).bianchini", ":(exclude).planning")
			if listErr != nil {
				return nil, workflowError("DIRTY_WORKSPACE", listErr.Error())
			}
			paths = append(paths, nonEmptyLines(listed)...)
		}
	}
	untracked, err := workflowGit(repo, "ls-files", "--others", "--exclude-standard", "--", ".", ":(exclude).bianchini", ":(exclude).planning")
	if err != nil {
		return nil, workflowError("DIRTY_WORKSPACE", err.Error())
	}
	paths = append(paths, nonEmptyLines(untracked)...)
	return uniqueSorted(paths), nil
}

func snapshotDocViva(repo string) (map[string]string, error) {
	current := filepath.Join(repo, ".bianchini", "current")
	if err := rejectSymlinkChain(repo, current, "DocViva"); err != nil {
		return nil, err
	}
	info, err := os.Lstat(current)
	if err != nil || !info.IsDir() {
		return nil, workflowError("DOCVIVA_CURRENT_MISSING", ".bianchini/current ausente")
	}
	result := map[string]string{}
	err = filepath.WalkDir(current, func(path string, entry fs.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if path == current {
			return nil
		}
		relative, _ := filepath.Rel(repo, path)
		relative = filepath.ToSlash(relative)
		if entry.Type()&os.ModeSymlink != 0 {
			return workflowError("DOCVIVA_SYMLINK", "symlink não permitido: "+relative)
		}
		if entry.IsDir() {
			return nil
		}
		if !entry.Type().IsRegular() {
			return workflowError("DOCVIVA_PATH_INVALID", "entrada não regular: "+relative)
		}
		content, err := os.ReadFile(path)
		if err != nil || !validUTF8Text(content) {
			return workflowError("DOCVIVA_CONTENT_INVALID", relative+" não é UTF-8")
		}
		result[relative] = sha256Bytes(content)
		return nil
	})
	if err != nil {
		return nil, err
	}
	return result, nil
}

func verifyDocViva(repo string, before map[string]string, kind, outcome string, artifacts []string, justification string, required bool) (map[string]any, error) {
	if !oneOf(kind, "internal", "behavioral", "contract", "architecture", "rule") || !oneOf(outcome, "updated", "not_applicable", "no_op") {
		return nil, workflowError("DOCVIVA_CLASSIFICATION_INVALID", "kind ou outcome não suportado")
	}
	declared := make([]string, 0, len(artifacts))
	seen := map[string]bool{}
	for _, artifact := range artifacts {
		if err := validateDocVivaRelative(artifact); err != nil {
			return nil, err
		}
		if seen[artifact] {
			return nil, workflowError("DOCVIVA_DECLARATION_INVALID", "artifacts contém duplicatas")
		}
		seen[artifact] = true
		declared = append(declared, artifact)
	}
	sort.Strings(declared)
	after, err := snapshotDocViva(repo)
	if err != nil {
		return nil, err
	}
	created, modified, removed := []string{}, []string{}, []string{}
	for path, digest := range after {
		beforeDigest, exists := before[path]
		if !exists {
			created = append(created, path)
		} else if digest != beforeDigest {
			modified = append(modified, path)
		}
	}
	for path := range before {
		if _, exists := after[path]; !exists {
			removed = append(removed, path)
		}
	}
	sort.Strings(created)
	sort.Strings(modified)
	sort.Strings(removed)
	changed := append(append(append([]string{}, created...), modified...), removed...)
	sort.Strings(changed)
	if strings.Join(declared, "\x00") != strings.Join(changed, "\x00") {
		return nil, workflowError("DOCVIVA_DECLARATION_MISMATCH", "artifacts declarados não correspondem exatamente aos digests alterados")
	}
	proof := strings.TrimSpace(justification)
	switch outcome {
	case "not_applicable":
		if kind != "internal" || required || proof == "" || len(changed) > 0 {
			return nil, workflowError("DOCVIVA_NOT_APPLICABLE_INVALID", "not_applicable exige trabalho interno, justificativa e digests iguais")
		}
	case "no_op":
		if proof == "" || len(changed) > 0 {
			return nil, workflowError("DOCVIVA_NO_OP_INVALID", "no_op exige prova textual e digests iguais")
		}
	case "updated":
		if required && len(changed) == 0 || len(changed) == 0 {
			return nil, workflowError("DOCVIVA_UPDATE_REQUIRED", "outcome updated exige ao menos um artefato current alterado")
		}
		if required && !docVivaCorresponds(kind, changed) {
			return nil, workflowError("DOCVIVA_ARTIFACT_MISMATCH", "nenhum artefato alterado corresponde à classificação "+kind)
		}
	}
	return map[string]any{
		"schema_version": 1, "status": "verified", "kind": kind, "outcome": outcome,
		"required": required, "artifacts": declared, "created": created, "modified": modified,
		"removed": removed, "changed": changed, "before_digest": docVivaSnapshotDigest(before),
		"after_digest": docVivaSnapshotDigest(after), "justification": proof,
	}, nil
}

func docVivaSnapshotDigest(snapshot map[string]string) string {
	encoded, _ := canonicalJSON(snapshot)
	return sha256Bytes(encoded)
}

func validateDocVivaRelative(path string) error {
	if path == "" || strings.Contains(path, "\\") || filepath.IsAbs(path) || filepath.ToSlash(filepath.Clean(path)) != path || !strings.HasPrefix(path, ".bianchini/current/") {
		return workflowError("DOCVIVA_PATH_INVALID", "artifact declarado não pertence a .bianchini/current")
	}
	for _, part := range strings.Split(path, "/") {
		if part == "" || part == "." || part == ".." || strings.EqualFold(part, ".planning") {
			return workflowError("DOCVIVA_PATH_INVALID", "artifact declarado usa path inválido")
		}
	}
	return nil
}

func docVivaCorresponds(kind string, paths []string) bool {
	for _, path := range paths {
		switch kind {
		case "architecture":
			if path == ".bianchini/current/ARCHITECTURE.md" {
				return true
			}
		case "behavioral", "rule":
			if path == ".bianchini/current/SYSTEM_MODEL.md" || strings.HasPrefix(path, ".bianchini/current/specs/") && strings.HasSuffix(path, ".md") {
				return true
			}
		case "contract":
			if strings.HasPrefix(path, ".bianchini/current/specs/") && strings.HasSuffix(path, ".md") {
				return true
			}
		default:
			return true
		}
	}
	return false
}

func docVivaKindRequired(kind string) bool {
	return oneOf(kind, "behavioral", "contract", "architecture", "rule")
}

func rejectSymlinkChain(root, path, label string) error {
	current := root
	relative, err := filepath.Rel(root, path)
	if err != nil || relative == ".." || strings.HasPrefix(relative, ".."+string(filepath.Separator)) {
		return workflowError("DOCVIVA_PATH_INVALID", label+" fora do repositório")
	}
	for _, part := range strings.Split(relative, string(filepath.Separator)) {
		current = filepath.Join(current, part)
		if info, statErr := os.Lstat(current); statErr == nil && info.Mode()&os.ModeSymlink != 0 {
			return workflowError("DOCVIVA_SYMLINK", label+" atravessa symlink")
		}
	}
	return nil
}

func regularFile(path string) bool {
	info, err := os.Lstat(path)
	return err == nil && info.Mode().IsRegular() && info.Mode()&os.ModeSymlink == 0
}

func userError(message string) error {
	return &commandError{message: message}
}

func differenceSorted(left, right []string) []string {
	set := map[string]bool{}
	for _, value := range right {
		set[value] = true
	}
	result := make([]string, 0)
	for _, value := range uniqueSorted(left) {
		if !set[value] {
			result = append(result, value)
		}
	}
	return result
}

func stringsFromAny(value any) []string {
	result := make([]string, 0)
	switch values := value.(type) {
	case []string:
		return append(result, values...)
	case []any:
		for _, raw := range values {
			if text, ok := raw.(string); ok {
				result = append(result, text)
			}
		}
	}
	return result
}

func stringMap(value any) map[string]string {
	result := map[string]string{}
	switch values := value.(type) {
	case map[string]string:
		for key, item := range values {
			result[key] = item
		}
	case map[string]any:
		for key, item := range values {
			if text, ok := item.(string); ok {
				result[key] = text
			}
		}
	}
	return result
}

func anyStrings(values []string) []any {
	result := make([]any, len(values))
	for index, value := range values {
		result[index] = value
	}
	return result
}

func nonEmptyLines(value string) []string {
	if value == "" {
		return nil
	}
	result := make([]string, 0)
	for _, line := range strings.Split(value, "\n") {
		if line = strings.TrimSpace(line); line != "" {
			result = append(result, line)
		}
	}
	return result
}
