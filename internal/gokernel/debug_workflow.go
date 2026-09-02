package gokernel

import (
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
)

var (
	debugIDPattern   = regexp.MustCompile(`^D[0-9]{3}-[a-z0-9]+(?:-[a-z0-9]+)*$`)
	debugTransitions = map[string]string{
		"intake": "reproduced", "reproduced": "diagnosed", "diagnosed": "red",
		"red": "fixing", "fixing": "green", "green": "regression_checked",
		"regression_checked": "documented",
	}
	debugValueFlags = map[string]bool{
		"--repo": true, "--id": true, "--objective": true, "--expected": true,
		"--actual": true, "--environment": true, "--origin-ref": true,
		"--origin-evidence": true, "--relation": true, "--event": true,
		"--evidence": true, "--hypothesis": true, "--experiment": true,
		"--eliminated-hypothesis": true, "--root-cause": true,
		"--neighbor-regression": true, "--residual-risk": true, "--status": true,
		"--reason": true, "--docviva-kind": true, "--docviva-outcome": true,
		"--docviva-artifact": true, "--docviva-justification": true,
		"--learning-classification": true, "--learning-statement": true,
		"--learning-tag": true, "--learning-validity": true, "--learning-conflict": true,
	}
)

func runDebug(args []string) (any, error) {
	if len(args) == 0 {
		return nil, argparseError("the following arguments are required: action")
	}
	action := args[0]
	if !oneOf(action, "start", "list", "status", "resume", "checkpoint", "finish") {
		return nil, argparseError(fmt.Sprintf("argument action: invalid choice: '%s'", action))
	}
	flags, err := parseFlags(args[1:], debugValueFlags, map[string]bool{})
	if err != nil {
		return nil, err
	}
	if action == "start" {
		if lastValue(flags, "--objective") == "" || lastValue(flags, "--expected") == "" || lastValue(flags, "--actual") == "" || lastValue(flags, "--environment") == "" {
			return nil, userError("debug start exige --objective, --expected, --actual e --environment")
		}
		return debugStart(flags)
	}
	repo, err := workflowRepo(flags, false)
	if err != nil {
		return nil, err
	}
	switch action {
	case "list":
		return debugStatus(repo, "")
	case "status", "resume":
		if lastValue(flags, "--id") == "" {
			return nil, userError("debug " + action + " exige --id")
		}
		return debugStatus(repo, lastValue(flags, "--id"))
	case "checkpoint":
		if lastValue(flags, "--id") == "" || lastValue(flags, "--event") == "" || lastValue(flags, "--evidence") == "" {
			return nil, userError("debug checkpoint exige --id, --event e --evidence")
		}
		return debugCheckpoint(repo, flags)
	case "finish":
		if lastValue(flags, "--id") == "" {
			return nil, userError("debug finish exige --id")
		}
		return debugFinish(repo, flags)
	}
	return nil, argparseError(fmt.Sprintf("argument action: invalid choice: '%s'", action))
}

func debugStart(flags parsedFlags) (map[string]any, error) {
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
	originRefs := flags.values["--origin-ref"]
	invalid := make([]string, 0)
	for _, reference := range originRefs {
		if !debugReferenceExists(workspace, reference) {
			invalid = append(invalid, reference)
		}
	}
	if len(invalid) > 0 {
		return nil, workflowError("MODEL_MISMATCH", "referências inexistentes: "+strings.Join(invalid, ", "))
	}
	if len(originRefs) > 0 && !oneOf(lastValue(flags, "--relation"), "caused_by", "detected_in", "regression_of") {
		return nil, workflowError("MODEL_MISMATCH", "relação causal válida é obrigatória")
	}
	if len(originRefs) > 0 && strings.TrimSpace(lastValue(flags, "--origin-evidence")) == "" {
		return nil, workflowError("STALE_EVIDENCE", "relação com mudança anterior exige --origin-evidence")
	}
	baseID, err := allocateWorkflowID(workspace, "debug")
	if err != nil {
		return nil, err
	}
	slug, err := modelSlug(lastValue(flags, "--objective"))
	if err != nil {
		return nil, err
	}
	id := baseID + "-" + slug
	docBefore, err := snapshotDocViva(repo)
	if err != nil {
		return nil, err
	}
	value := map[string]any{
		"schema_version": 1, "docviva_contract": 1, "docviva_before": docBefore,
		"id": id, "status": "active", "stage": "intake",
		"objective": lastValue(flags, "--objective"), "expected": lastValue(flags, "--expected"),
		"actual": lastValue(flags, "--actual"), "environment": lastValue(flags, "--environment"),
		"origin_refs": originRefs, "relation": nullableString(lastValue(flags, "--relation")),
		"origin_evidence": nullableTrimmed(lastValue(flags, "--origin-evidence")),
		"hypotheses":      []any{}, "experiments": []any{}, "eliminated_hypotheses": []any{},
		"root_cause": nil, "red": nil, "green": nil, "neighboring_regressions": []any{},
		"residual_risk": nil, "events": []any{}, "created_at": utcNow(), "updated_at": utcNow(),
	}
	path, err := debugPath(workspace, id, false)
	if err != nil {
		return nil, err
	}
	document, _ := frontmatterDocument(value, "# Debug "+id+"\n\n"+lastValue(flags, "--objective"), false)
	if err := workspace.atomicWrite(path, document); err != nil {
		return nil, err
	}
	if err := updateWorkflowState(workspace, map[string]any{
		"active_work":  map[string]any{"kind": "debug", "id": id, "status": "active"},
		"current_unit": "intake", "status": "active",
		"next_action": "Reproduzir " + id + " de forma determinística.",
	}); err != nil {
		return nil, err
	}
	return map[string]any{"id": id, "status": "active", "stage": "intake"}, nil
}

func debugCheckpoint(repo string, flags parsedFlags) (map[string]any, error) {
	workspace := newMethodWorkspace(repo)
	id := lastValue(flags, "--id")
	path, err := debugPath(workspace, id, false)
	if err != nil {
		return nil, err
	}
	value, err := readJSONFrontmatter(path, "debug ativo")
	if err != nil {
		return nil, err
	}
	event := lastValue(flags, "--event")
	expected := debugTransitions[stateString(value["stage"])]
	if event != expected {
		return nil, workflowError("ORDER_VIOLATION", fmt.Sprintf("após %s o próximo evento é %s", stateString(value["stage"]), expected))
	}
	evidence := strings.TrimSpace(lastValue(flags, "--evidence"))
	if evidence == "" {
		return nil, workflowError("STALE_EVIDENCE", "checkpoint exige evidência")
	}
	fingerprint, err := workflowTreeFingerprint(repo)
	if err != nil {
		return nil, err
	}
	rootCause := strings.TrimSpace(lastValue(flags, "--root-cause"))
	if event == "diagnosed" && rootCause == "" {
		return nil, workflowError("STALE_EVIDENCE", "diagnóstico exige --root-cause")
	}
	events := stateArray(value["events"])
	byEvent := map[string]map[string]any{}
	for _, raw := range events {
		item := stateObject(raw)
		if name := stateString(item["event"]); name != "" {
			byEvent[name] = item
		}
	}
	if event == "green" {
		red := byEvent["red"]
		if red == nil || stateString(red["fingerprint"]) == fingerprint {
			return nil, workflowError("STALE_EVIDENCE", "GREEN exige patch posterior à evidência RED")
		}
	}
	if event == "regression_checked" {
		green := byEvent["green"]
		if green == nil || stateString(green["fingerprint"]) != fingerprint {
			return nil, workflowError("STALE_EVIDENCE", "patch posterior ao GREEN exige repetir o GREEN")
		}
		if len(nonBlank(flags.values["--neighbor-regression"])) == 0 {
			return nil, workflowError("STALE_EVIDENCE", "regressão exige --neighbor-regression")
		}
	}
	if event == "documented" {
		regression := byEvent["regression_checked"]
		if regression == nil || stateString(regression["fingerprint"]) != fingerprint {
			return nil, workflowError("STALE_EVIDENCE", "patch posterior à regressão exige repetir os gates")
		}
		if strings.TrimSpace(lastValue(flags, "--residual-risk")) == "" {
			return nil, workflowError("STALE_EVIDENCE", "documentação exige --residual-risk")
		}
	}
	appendStringValues(value, "hypotheses", nonBlank(flags.values["--hypothesis"]))
	appendStringValues(value, "experiments", nonBlank(flags.values["--experiment"]))
	appendStringValues(value, "eliminated_hypotheses", nonBlank(flags.values["--eliminated-hypothesis"]))
	if rootCause != "" {
		value["root_cause"] = rootCause
	}
	if event == "red" {
		value["red"] = evidence
	}
	if event == "green" {
		value["green"] = evidence
	}
	regressions := nonBlank(flags.values["--neighbor-regression"])
	appendStringValues(value, "neighboring_regressions", regressions)
	if residual := strings.TrimSpace(lastValue(flags, "--residual-risk")); residual != "" {
		value["residual_risk"] = residual
	}
	value["stage"] = event
	value["updated_at"] = utcNow()
	events = append(events, map[string]any{"event": event, "evidence": evidence, "fingerprint": fingerprint, "at": utcNow()})
	value["events"] = events
	document, _ := frontmatterDocument(value, "# Debug "+id+"\n\n"+stateString(value["objective"]), false)
	if err := workspace.atomicWrite(path, document); err != nil {
		return nil, err
	}
	next := "Registrar " + debugTransitions[event] + " em " + id + "."
	if event == "documented" {
		next = "Finalizar " + id + "."
	}
	if err := updateWorkflowState(workspace, map[string]any{"current_unit": event, "next_action": next}); err != nil {
		return nil, err
	}
	return map[string]any{"id": id, "status": "active", "stage": event}, nil
}

func debugStatus(repo, id string) (map[string]any, error) {
	workspace := newMethodWorkspace(repo)
	if _, err := workspace.readState(); err != nil {
		return nil, err
	}
	if id != "" {
		for _, resolved := range []bool{false, true} {
			path, err := debugPath(workspace, id, resolved)
			if err != nil {
				return nil, err
			}
			if regularFile(path) {
				value, err := readJSONFrontmatter(path, "debug")
				if err != nil {
					return nil, err
				}
				return map[string]any{"id": id, "status": value["status"], "stage": value["stage"], "path": path}, nil
			}
		}
		return nil, workflowError("MODEL_MISMATCH", "debug não encontrado: "+id)
	}
	items := make([]any, 0)
	for _, area := range []struct {
		name     string
		resolved bool
	}{{"active", false}, {"resolved", true}} {
		directory := filepath.Join(workspace.dir, "debug", area.name)
		entries, err := os.ReadDir(directory)
		if err != nil {
			return nil, workflowError("MODEL_MISMATCH", err.Error())
		}
		sort.Slice(entries, func(i, j int) bool { return entries[i].Name() < entries[j].Name() })
		for _, entry := range entries {
			if entry.Type()&os.ModeSymlink != 0 || entry.IsDir() || !strings.HasPrefix(entry.Name(), "D") || !strings.HasSuffix(entry.Name(), ".md") {
				continue
			}
			value, err := readJSONFrontmatter(filepath.Join(directory, entry.Name()), "debug")
			if err != nil {
				return nil, err
			}
			items = append(items, map[string]any{"id": value["id"], "status": value["status"], "stage": value["stage"], "resolved": area.resolved})
		}
	}
	return map[string]any{"items": items}, nil
}

func debugFinish(repo string, flags parsedFlags) (map[string]any, error) {
	workspace := newMethodWorkspace(repo)
	id := lastValue(flags, "--id")
	status := lastValue(flags, "--status")
	if status == "" {
		status = "resolved"
	}
	if !oneOf(status, "resolved", "blocked", "escalated") {
		return nil, workflowError("MODEL_MISMATCH", "status terminal inválido")
	}
	source, err := debugPath(workspace, id, false)
	if err != nil {
		return nil, err
	}
	value, err := readJSONFrontmatter(source, "debug ativo")
	if err != nil {
		return nil, err
	}
	if status == "resolved" && stateString(value["stage"]) != "documented" {
		return nil, workflowError("ORDER_VIOLATION", "debug resolvido exige RED, GREEN, regressão e documentação")
	}
	var docViva any
	if status == "resolved" {
		events := stateArray(value["events"])
		if len(events) == 0 {
			return nil, workflowError("STALE_EVIDENCE", "alteração posterior à documentação exige repetir os gates")
		}
		fingerprint, err := workflowTreeFingerprint(repo)
		if err != nil {
			return nil, err
		}
		if stateString(stateObject(events[len(events)-1])["fingerprint"]) != fingerprint {
			return nil, workflowError("STALE_EVIDENCE", "alteração posterior à documentação exige repetir os gates")
		}
		missing := make([]string, 0)
		for _, key := range []string{"root_cause", "red", "green", "neighboring_regressions", "residual_risk"} {
			if emptyWorkflowValue(value[key]) {
				missing = append(missing, key)
			}
		}
		if len(missing) > 0 {
			return nil, workflowError("DOCVIVA_INCOMPLETE", "debug não documenta: "+strings.Join(missing, ", "))
		}
		kind, outcome := lastValue(flags, "--docviva-kind"), lastValue(flags, "--docviva-outcome")
		if kind == "" || outcome == "" {
			return nil, workflowError("DOCVIVA_INCOMPLETE", "debug resolvido exige classificação DocViva explícita")
		}
		docViva, err = verifyDocViva(repo, stringMap(value["docviva_before"]), kind, outcome, flags.values["--docviva-artifact"], lastValue(flags, "--docviva-justification"), docVivaKindRequired(kind))
		if err != nil {
			return nil, err
		}
	} else if strings.TrimSpace(lastValue(flags, "--reason")) == "" {
		return nil, workflowError("MODEL_MISMATCH", "debug bloqueado ou escalado exige motivo")
	}
	learningFields := []string{"--learning-classification", "--learning-statement", "--learning-validity"}
	learningRequested := len(flags.values["--learning-tag"]) > 0 || len(flags.values["--learning-conflict"]) > 0
	for _, name := range learningFields {
		learningRequested = learningRequested || lastValue(flags, name) != ""
	}
	if learningRequested {
		if status != "resolved" {
			return nil, workflowError("LEARNING_CANDIDATE_INVALID", "somente debug resolvido pode nomear aprendizado")
		}
		if lastValue(flags, "--learning-classification") == "" || lastValue(flags, "--learning-statement") == "" || len(flags.values["--learning-tag"]) == 0 || lastValue(flags, "--learning-validity") == "" {
			return nil, userError("nomeação de aprendizado exige classification, statement, tag e validity")
		}
		value["learning_candidate"] = map[string]any{
			"classification": lastValue(flags, "--learning-classification"), "statement": lastValue(flags, "--learning-statement"),
			"tags": flags.values["--learning-tag"], "validity": lastValue(flags, "--learning-validity"), "conflicts": flags.values["--learning-conflict"],
		}
	}
	value["status"] = status
	value["reason"] = nullableString(lastValue(flags, "--reason"))
	value["docviva"] = docViva
	value["finished_at"] = utcNow()
	target, err := debugPath(workspace, id, true)
	if err != nil {
		return nil, err
	}
	if regularFile(target) {
		return nil, workflowError("ORDER_VIOLATION", "debug terminal é imutável")
	}
	document, _ := frontmatterDocument(value, "# Debug "+id+"\n\n"+stateString(value["objective"]), false)
	if err := workspace.atomicWrite(source, document); err != nil {
		return nil, err
	}
	if err := durableRename(source, target); err != nil {
		return nil, workflowError("MODEL_MISMATCH", err.Error())
	}
	stateStatus := "idle"
	if status == "blocked" {
		stateStatus = "blocked"
	}
	if err := updateWorkflowState(workspace, map[string]any{
		"active_work": nil, "current_unit": nil, "status": stateStatus,
		"last_completed": map[string]any{"kind": "debug", "id": id, "status": status},
		"next_action":    "Revisar o resultado do debug e seguir o trabalho registrado.",
	}); err != nil {
		return nil, err
	}
	return map[string]any{"id": id, "status": status, "stage": value["stage"], "path": target, "docviva": docViva}, nil
}

func debugPath(workspace methodWorkspace, id string, resolved bool) (string, error) {
	if !debugIDPattern.MatchString(id) {
		return "", workflowError("MODEL_MISMATCH", "ID de debug inválido")
	}
	area := "active"
	if resolved {
		area = "resolved"
	}
	path, err := workspace.confined(filepath.Join(".bianchini", "debug", area, id+".md"))
	if err != nil {
		return "", err
	}
	if err := workspace.validateWorkspacePath(path); err != nil {
		return "", err
	}
	return path, nil
}

func debugReferenceExists(workspace methodWorkspace, reference string) bool {
	if !regexp.MustCompile(`^C[0-9]{3}(?:-[a-z0-9-]+)?/P[0-9]{2}$`).MatchString(reference) {
		return false
	}
	parts := strings.Split(reference, "/")
	for _, base := range []string{workspace.changes, filepath.Join(workspace.dir, "archive")} {
		entries, err := os.ReadDir(base)
		if err != nil {
			continue
		}
		for _, entry := range entries {
			if entry.Type()&os.ModeSymlink != 0 || !entry.IsDir() || !strings.HasPrefix(entry.Name(), parts[0]) {
				continue
			}
			plan, found := planFileForID(filepath.Join(base, entry.Name(), "plans"), parts[1])
			if found && regularFile(plan) {
				return true
			}
		}
	}
	return false
}

func appendStringValues(value map[string]any, key string, additions []string) {
	items := stateArray(value[key])
	for _, addition := range additions {
		items = append(items, addition)
	}
	value[key] = items
}

func nonBlank(values []string) []string {
	result := make([]string, 0, len(values))
	for _, value := range values {
		if value = strings.TrimSpace(value); value != "" {
			result = append(result, value)
		}
	}
	return result
}

func nullableString(value string) any {
	if value == "" {
		return nil
	}
	return value
}

func nullableTrimmed(value string) any {
	return nullableString(strings.TrimSpace(value))
}

func emptyWorkflowValue(value any) bool {
	if value == nil {
		return true
	}
	if text, ok := value.(string); ok {
		return strings.TrimSpace(text) == ""
	}
	if values, ok := value.([]any); ok {
		return len(values) == 0
	}
	return false
}
