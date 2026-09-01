package gokernel

import (
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"reflect"
	"regexp"
	"strconv"
	"strings"
)

var (
	legacyTaskHeading      = regexp.MustCompile(`(?mi)^###\s+(?:Tarefa|Task|Slice)\s+\S+.*$`)
	legacyAnyLevel3Heading = regexp.MustCompile(`(?m)^###\s+.*$`)
	legacyTaskSelector     = regexp.MustCompile(`^[A-Za-z0-9_.-]+$`)
	legacyTaskInterval     = regexp.MustCompile(`^(\d+)\s*-\s*(\d+)$`)
	legacyExecution        = regexp.MustCompile(`(?mi)^\*\*Execution:\*\*\s*([a-z_]+)\s*$`)
	legacyPrivateKey       = regexp.MustCompile(`(?ms)-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----`)
	legacySecretAssignment = regexp.MustCompile(`(?im)(\b(?:api[_-]?key|access[_-]?token|auth[_-]?token|password|passwd|secret)\b\s*[:=]\s*)[^\s]+`)
	legacyBearer           = regexp.MustCompile(`(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+`)
	legacyEmail            = regexp.MustCompile(`(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b`)
)

func legacyOutputPath(path, label string) (string, error) {
	if err := rejectForeignNamespace(path, label); err != nil {
		return "", err
	}
	absolute, err := filepath.Abs(path)
	if err != nil {
		return "", domainError("PATH_SAFETY", label+" inválido")
	}
	if info, statErr := os.Lstat(absolute); statErr == nil {
		if !info.Mode().IsRegular() || info.Mode()&os.ModeSymlink != 0 {
			return "", domainError("PATH_SAFETY", label+" deve ser arquivo regular")
		}
	} else if !os.IsNotExist(statErr) {
		return "", domainError("PATH_SAFETY", label+" inválido")
	}
	return absolute, nil
}

func legacyRequiredFlags(flags parsedFlags, names ...string) error {
	missing := make([]string, 0)
	for _, name := range names {
		if lastValue(flags, name) == "" {
			missing = append(missing, name)
		}
	}
	if len(missing) > 0 {
		return argparseError("the following arguments are required: " + strings.Join(missing, ", "))
	}
	return nil
}

func runTaskBrief(args []string) (any, error) {
	values := map[string]bool{
		"--plan": true, "--task": true, "--tasks": true, "--group": true,
		"--state": true, "--root": true, "--ledger-tail-lines": true, "--output": true,
	}
	flags, err := parseFlags(args, values, map[string]bool{"--hydrate-context": true})
	if err != nil {
		return nil, err
	}
	if err := legacyRequiredFlags(flags, "--plan", "--output"); err != nil {
		return nil, err
	}
	selectors := 0
	for _, name := range []string{"--task", "--tasks", "--group"} {
		if lastValue(flags, name) != "" {
			selectors++
		}
	}
	if selectors != 1 {
		return nil, argparseError("one of the arguments --task --tasks --group is required")
	}
	tail := 40
	if raw := lastValue(flags, "--ledger-tail-lines"); raw != "" {
		value, parseErr := strconv.Atoi(raw)
		if parseErr != nil {
			return nil, argparseError("argument --ledger-tail-lines: invalid int value: '" + raw + "'")
		}
		tail = value
	}
	return legacyWriteTaskBrief(
		lastValue(flags, "--plan"), lastValue(flags, "--task"), lastValue(flags, "--tasks"),
		lastValue(flags, "--group"), lastValue(flags, "--output"), lastValue(flags, "--state"),
		lastValue(flags, "--root"), flags.booleans["--hydrate-context"], tail,
	)
}

func legacyWriteTaskBrief(planValue, task, tasks, group, outputValue, stateValue, rootValue string, hydrate bool, ledgerTail int) (map[string]any, error) {
	if ledgerTail < 0 {
		return nil, fmt.Errorf("--ledger-tail-lines não pode ser negativo")
	}
	plan, err := safeStandaloneFile(planValue, "plan")
	if err != nil {
		return nil, err
	}
	contentBytes, err := os.ReadFile(plan)
	if err != nil || !validUTF8Text(contentBytes) {
		return nil, fmt.Errorf("plan deve ser UTF-8 textual")
	}
	content := string(contentBytes)
	labels := make([]string, 0)
	sections := make([]string, 0)
	title := group
	if group != "" {
		labels = []string{group}
		section, extractErr := legacyExtractGroup(content, group)
		if extractErr != nil {
			return nil, fmt.Errorf("grupo %q não encontrado em %s", group, planValue)
		}
		sections = []string{section}
	} else {
		labels, err = legacyParseTaskSelector(tasks + task)
		if err != nil {
			return nil, err
		}
		title = strings.Join(labels, ", ")
		for _, label := range labels {
			section, extractErr := legacyExtractTask(content, label)
			if extractErr != nil {
				return nil, fmt.Errorf("tarefa %s não encontrada em %s", label, planValue)
			}
			sections = append(sections, section)
		}
		if len(labels) > 1 {
			for index, section := range sections {
				match := legacyExecution.FindStringSubmatch(section)
				if len(match) != 2 {
					return nil, fmt.Errorf("tarefa %s não declara Execution", labels[index])
				}
				if match[1] != "grouped" {
					return nil, fmt.Errorf("brief com várias tarefas exige Execution: grouped em todas as unidades")
				}
			}
		}
	}
	planDigest := sha256Bytes(contentBytes)
	unitDigests := make([]string, len(sections))
	for index, section := range sections {
		unitDigests[index] = sha256Bytes([]byte(section))
	}
	groupDigest := sha256Bytes([]byte(strings.Join(sections, "\n--- bm-unit ---\n")))
	kind := "task"
	if group != "" {
		kind = "heading"
	} else if len(labels) > 1 {
		kind = "group"
	}
	groupID := ""
	if kind == "group" || kind == "heading" {
		groupID = "group-" + groupDigest[:12]
	}
	displayGroup := groupID
	if displayGroup == "" {
		displayGroup = "n/a"
	}
	var metadata strings.Builder
	for index, label := range labels {
		fmt.Fprintf(&metadata, "- Unit `%s` SHA-256: `%s`\n", label, unitDigests[index])
	}
	brief := fmt.Sprintf(
		"# Task Brief %s\n\n- Plan: `%s`\n- Plan SHA-256: `%s`\n- Kind: `%s`\n- Group ID: `%s`\n- Group SHA-256: `%s`\n%s\n%s",
		title, planValue, planDigest, kind, displayGroup, groupDigest, metadata.String(), strings.Join(sections, "\n"),
	)
	contextDigest := any(nil)
	if hydrate {
		if stateValue == "" || rootValue == "" {
			return nil, fmt.Errorf("--hydrate-context exige --state e --root")
		}
		context, digest, hydrateErr := legacyHydrateTaskContext(rootValue, stateValue, plan, labels, sections, ledgerTail)
		if hydrateErr != nil {
			return nil, hydrateErr
		}
		brief = strings.TrimRight(brief, "\n") + "\n\n" + context
		contextDigest = digest
	}
	output, err := legacyOutputPath(outputValue, "output")
	if err != nil {
		return nil, err
	}
	if err := atomicWrite(output, []byte(strings.TrimRight(brief, "\n")+"\n")); err != nil {
		return nil, err
	}
	return map[string]any{
		"brief": outputValue, "plan_digest": planDigest, "kind": kind,
		"group_id": func() any {
			if groupID == "" {
				return nil
			}
			return groupID
		}(),
		"group_digest": groupDigest, "tasks": labels, "unit_digests": unitDigests,
		"hydrated": hydrate, "context_digest": contextDigest,
	}, nil
}

func legacyParseTaskSelector(selector string) ([]string, error) {
	seen := make(map[string]bool)
	result := make([]string, 0)
	for _, raw := range strings.Split(selector, ",") {
		token := strings.TrimSpace(raw)
		if token == "" {
			continue
		}
		if match := legacyTaskInterval.FindStringSubmatch(token); match != nil {
			start, _ := strconv.Atoi(match[1])
			end, _ := strconv.Atoi(match[2])
			if end < start {
				return nil, fmt.Errorf("intervalo de tarefas inválido: %s", token)
			}
			for value := start; value <= end; value++ {
				label := strconv.Itoa(value)
				if !seen[label] {
					seen[label] = true
					result = append(result, label)
				}
			}
		} else if legacyTaskSelector.MatchString(token) {
			if !seen[token] {
				seen[token] = true
				result = append(result, token)
			}
		} else {
			return nil, fmt.Errorf("seletor de tarefa inválido: %s", token)
		}
	}
	if len(result) == 0 {
		return nil, fmt.Errorf("nenhuma tarefa selecionada")
	}
	return result, nil
}

func legacyExtractTask(content, task string) (string, error) {
	pattern := regexp.MustCompile(`(?mi)^###\s+(?:Tarefa|Task|Slice)\s+` + regexp.QuoteMeta(task) + `\b.*$`)
	match := pattern.FindStringIndex(content)
	if match == nil {
		return "", fmt.Errorf("not found")
	}
	end := len(content)
	for _, next := range legacyTaskHeading.FindAllStringIndex(content[match[1]:], -1) {
		end = match[1] + next[0]
		break
	}
	return strings.TrimRight(content[match[0]:end], "\r\n") + "\n", nil
}

func legacyExtractGroup(content, heading string) (string, error) {
	pattern := regexp.MustCompile(`(?m)^###\s+` + regexp.QuoteMeta(heading) + `\s*$`)
	match := pattern.FindStringIndex(content)
	if match == nil {
		return "", fmt.Errorf("not found")
	}
	end := len(content)
	if next := legacyAnyLevel3Heading.FindStringIndex(content[match[1]:]); next != nil {
		end = match[1] + next[0]
	}
	return strings.TrimRight(content[match[0]:end], "\r\n") + "\n", nil
}

func legacyHydrateTaskContextBaseline(rootValue, stateValue, planPath string, labels, sections []string, ledgerTail int) (string, string, error) {
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
	if stateInt(state["method_version"]) != 2 || stateInt(stateObject(state["planning"])["quality_version"]) != 2 {
		return "", "", fmt.Errorf("contexto hidratado exige PROJECT_STATE v2 e planning.quality_version 2")
	}
	planRelative, err := legacyRelative(root, planPath)
	if err != nil {
		return "", "", err
	}
	var selected map[string]any
	for _, raw := range stateArray(state["plans"]) {
		item := stateObject(raw)
		if stateString(item["path"]) == planRelative {
			selected = item
			break
		}
	}
	if selected == nil {
		return "", "", fmt.Errorf("plan não pertence ao PROJECT_STATE informado")
	}
	changes := make([]string, 0)
	for _, section := range sections {
		if match := regexp.MustCompile(`(?mi)^\*\*Change:\*\*\s*([^\r\n]+)`).FindStringSubmatch(section); len(match) == 2 {
			changes = append(changes, strings.TrimSpace(match[1]))
		}
	}
	metadata := map[string]any{
		"schema_version": 1, "planning_version": state["planning_version"],
		"package_digest": stateObject(stateObject(state["approval"])["package"])["manifest_digest"],
		"plan_id":        selected["id"], "plan_path": planRelative,
		"profile": state["assurance_profile"], "risk": selected["risk"],
		"execution": selected["execution"], "review": selected["review"],
		"test_seams": selected["test_seams"], "units": labels, "changes": changes,
		"verification_fast": stateObject(stateObject(state["verification"])["fast"])["commands"],
		"ledger_tail_lines": 0,
	}
	ledgerLines := make([]string, 0)
	if ledgerValue := stateString(selected["ledger"]); ledgerValue != "" && ledgerTail > 0 {
		if ledgerPath, pathErr := confinedPath(root, ledgerValue, "plan.ledger", true); pathErr == nil {
			data, _ := os.ReadFile(ledgerPath)
			all := strings.Split(strings.TrimRight(string(data), "\r\n"), "\n")
			if len(all) > ledgerTail {
				all = all[len(all)-ledgerTail:]
			}
			ledgerLines = all
		}
	}
	metadata["ledger_tail_lines"] = len(ledgerLines)
	metadataBytes, _ := json.MarshalIndent(metadata, "", "  ")
	var rendered strings.Builder
	rendered.WriteString("## Contexto hidratado\n\n```json\n")
	rendered.Write(metadataBytes)
	rendered.WriteString("\n```\n\n### Readiness aplicável\n\n```json\n[]\n```\n\n### Specs aplicáveis\n\n### Verification.fast\n\n")
	for _, command := range stateStringSlice(metadata["verification_fast"]) {
		fmt.Fprintf(&rendered, "- `%s`\n", command)
	}
	if len(stateStringSlice(metadata["verification_fast"])) == 0 {
		rendered.WriteString("- Nenhum comando configurado.\n")
	}
	rendered.WriteString("\n### Último estado operacional\n\n")
	if len(ledgerLines) == 0 {
		rendered.WriteString("Nenhum ledger registrado para o plano.\n")
	} else {
		rendered.WriteString("```text\n" + strings.Join(ledgerLines, "\n") + "\n```\n")
	}
	context := rendered.String()
	return context, sha256Bytes([]byte(context)), nil
}

func runReport(args []string) (any, error) {
	flags, err := parseFlags(args, map[string]bool{"--brief": true, "--output": true}, map[string]bool{})
	if err != nil {
		return nil, err
	}
	if err := legacyRequiredFlags(flags, "--brief", "--output"); err != nil {
		return nil, err
	}
	briefValue := lastValue(flags, "--brief")
	brief, err := safeStandaloneFile(briefValue, "brief")
	if err != nil {
		return nil, err
	}
	outputValue := lastValue(flags, "--output")
	output, err := legacyOutputPath(outputValue, "output")
	if err != nil {
		return nil, err
	}
	digest, err := legacyFileDigest(brief)
	if err != nil {
		return nil, err
	}
	content := fmt.Sprintf("# Implementer Report\n\n- Brief: `%s`\n- Status: IN_PROGRESS\n\n## Changes\n\n## Verification\n\n## Decisions\n\n## Concerns\n", briefValue)
	if err := atomicWrite(output, []byte(content)); err != nil {
		return nil, err
	}
	return map[string]any{"report": outputValue, "brief_digest": digest}, nil
}

func runReviewPackage(args []string) (any, error) {
	flags, err := parseFlags(args, map[string]bool{"--cwd": true, "--base": true, "--head": true, "--brief": true, "--report": true, "--output": true}, map[string]bool{})
	if err != nil {
		return nil, err
	}
	if err := legacyRequiredFlags(flags, "--base", "--brief", "--report", "--output"); err != nil {
		return nil, err
	}
	cwd := lastValue(flags, "--cwd")
	if cwd == "" {
		cwd, _ = os.Getwd()
	}
	head := lastValue(flags, "--head")
	if head == "" {
		head = "HEAD"
	}
	return legacyWriteReviewPackage(cwd, lastValue(flags, "--base"), head, lastValue(flags, "--brief"), lastValue(flags, "--report"), lastValue(flags, "--output"))
}

func legacyGitOutput(cwd string, args ...string) (string, error) {
	command := exec.Command("git", args...)
	command.Dir = cwd
	output, err := command.CombinedOutput()
	if err != nil {
		return "", fmt.Errorf("git %s: %s", strings.Join(args, " "), strings.TrimSpace(string(output)))
	}
	return strings.TrimSpace(string(output)), nil
}

func legacyRedactSensitiveDiff(diff string) (string, int) {
	redacted := diff
	total := 0
	patterns := []struct {
		pattern     *regexp.Regexp
		replacement string
	}{
		{legacyPrivateKey, "[REDACTED PRIVATE KEY]"},
		{legacySecretAssignment, "${1}[REDACTED]"},
		{legacyBearer, "Bearer [REDACTED]"},
		{legacyEmail, "[REDACTED EMAIL]"},
	}
	for _, item := range patterns {
		total += len(item.pattern.FindAllStringIndex(redacted, -1))
		redacted = item.pattern.ReplaceAllString(redacted, item.replacement)
	}
	return redacted, total
}

func legacyWriteReviewPackage(cwdValue, base, head, briefValue, reportValue, outputValue string) (map[string]any, error) {
	cwd, err := safeRoot(cwdValue)
	if err != nil {
		return nil, err
	}
	brief, err := safeStandaloneFile(briefValue, "brief")
	if err != nil {
		return nil, err
	}
	report, err := safeStandaloneFile(reportValue, "report")
	if err != nil {
		return nil, err
	}
	commits, err := legacyGitOutput(cwd, "log", "--oneline", base+".."+head)
	if err != nil {
		return nil, err
	}
	stat, err := legacyGitOutput(cwd, "diff", "--stat", base, head)
	if err != nil {
		return nil, err
	}
	rawDiff, err := legacyGitOutput(cwd, "diff", "-U10", base, head)
	if err != nil {
		return nil, err
	}
	diff, redactions := legacyRedactSensitiveDiff(rawDiff)
	briefDigest, _ := legacyFileDigest(brief)
	reportDigest, _ := legacyFileDigest(report)
	content := fmt.Sprintf(
		"# Review Package\n\n- Base: `%s`\n- Head: `%s`\n- Brief: `%s` (%s)\n- Report: `%s` (%s)\n- Security notice: sanitização heurística; %d ocorrência(s) removida(s). Revise antes de compartilhar.\n\n## Commits\n\n```text\n%s\n```\n\n## Stat\n\n```text\n%s\n```\n\n## Diff\n\n```diff\n%s\n```\n",
		base, head, briefValue, briefDigest, reportValue, reportDigest, redactions, commits, stat, diff,
	)
	output, err := legacyOutputPath(outputValue, "output")
	if err != nil {
		return nil, err
	}
	if err := atomicWrite(output, []byte(content)); err != nil {
		return nil, err
	}
	return map[string]any{"review_package": outputValue, "base": base, "head": head, "redactions": redactions}, nil
}

func runCheckpoint(args []string) (any, error) {
	flags, err := parseFlags(args, map[string]bool{"--state": true, "--ledger": true, "--cwd": true, "--output": true}, map[string]bool{})
	if err != nil {
		return nil, err
	}
	if err := legacyRequiredFlags(flags, "--state", "--ledger", "--output"); err != nil {
		return nil, err
	}
	cwd := lastValue(flags, "--cwd")
	if cwd == "" {
		cwd, _ = os.Getwd()
	}
	return legacyWriteCheckpoint(lastValue(flags, "--state"), lastValue(flags, "--ledger"), cwd, lastValue(flags, "--output"))
}

func legacyWriteCheckpoint(stateValue, ledgerValue, cwdValue, outputValue string) (map[string]any, error) {
	cwd, err := safeRoot(cwdValue)
	if err != nil {
		return nil, err
	}
	statePath, err := safeStandaloneFile(stateValue, "state")
	if err != nil {
		return nil, err
	}
	state, err := legacyReadJSONDocument(statePath, "state")
	if err != nil {
		return nil, err
	}
	if stateInt(state["method_version"]) == 2 {
		state, err = validateStateFile(statePath, "")
		if err != nil {
			return nil, err
		}
	}
	ledgerLines := []string{}
	if ledgerPath, pathErr := safeStandaloneFile(ledgerValue, "ledger"); pathErr == nil {
		data, readErr := os.ReadFile(ledgerPath)
		if readErr == nil {
			ledgerLines = strings.Split(strings.TrimRight(string(data), "\r\n"), "\n")
			if len(ledgerLines) > 80 {
				ledgerLines = ledgerLines[len(ledgerLines)-80:]
			}
		}
	} else if _, statErr := os.Lstat(ledgerValue); !os.IsNotExist(statErr) {
		return nil, pathErr
	}
	branch, err := legacyGitOutput(cwd, "branch", "--show-current")
	if err != nil {
		return nil, err
	}
	head, err := legacyGitOutput(cwd, "rev-parse", "HEAD")
	if err != nil {
		return nil, err
	}
	status, err := legacyGitOutput(cwd, "status", "--porcelain")
	if err != nil {
		return nil, err
	}
	plans := make([]map[string]any, 0)
	for _, raw := range stateArray(state["plans"]) {
		plan := stateObject(raw)
		plans = append(plans, map[string]any{"id": plan["id"], "status": plan["status"], "ledger": plan["ledger"]})
	}
	checkpoint := map[string]any{
		"method_version": state["method_version"], "planning_status": state["planning_status"],
		"approval": stateObject(state["approval"])["status"], "plans": plans,
		"release": state["release"], "next_action": state["next_action"], "workspace": cwd,
		"git":         map[string]any{"branch": branch, "head": head, "dirty": status != ""},
		"ledger_tail": ledgerLines,
	}
	encoded, _ := legacyJSONBytes(checkpoint, true)
	output, err := legacyOutputPath(outputValue, "output")
	if err != nil {
		return nil, err
	}
	if err := atomicWrite(output, encoded); err != nil {
		return nil, err
	}
	digest, _ := legacyFileDigest(output)
	return map[string]any{"checkpoint": outputValue, "digest": digest}, nil
}

func runProofMap(args []string) (any, error) {
	flags, err := parseFlags(args, map[string]bool{"--state": true, "--evidence": true, "--mutation-evidence": true, "--output": true}, map[string]bool{})
	if err != nil {
		return nil, err
	}
	if err := legacyRequiredFlags(flags, "--state", "--evidence", "--output"); err != nil {
		return nil, err
	}
	return legacyWriteProofMap(lastValue(flags, "--state"), lastValue(flags, "--evidence"), flags.values["--mutation-evidence"], lastValue(flags, "--output"))
}

func legacyReadJSONArray(path, label string) ([]any, error) {
	file, err := safeStandaloneFile(path, label)
	if err != nil {
		return nil, err
	}
	data, err := os.ReadFile(file)
	if err != nil || !validUTF8Text(data) {
		return nil, fmt.Errorf("%s inválida", label)
	}
	var value []any
	if err := json.Unmarshal(data, &value); err != nil {
		return nil, fmt.Errorf("%s inválida: %w", label, err)
	}
	for _, item := range value {
		if _, ok := item.(map[string]any); !ok {
			return nil, fmt.Errorf("evidência deve ser uma lista JSON de objetos")
		}
	}
	return value, nil
}

func legacyWriteProofMap(stateValue, evidenceValue string, mutationValues []string, outputValue string) (map[string]any, error) {
	statePath, err := safeStandaloneFile(stateValue, "state")
	if err != nil {
		return nil, err
	}
	state, err := validateStateFile(statePath, "")
	if err != nil {
		return nil, err
	}
	evidence, err := legacyReadJSONArray(evidenceValue, "evidência")
	if err != nil {
		return nil, err
	}
	candidateRaw := stateObject(state["release"])["candidate"]
	candidate, candidateOK := candidateRaw.(map[string]any)
	if !candidateOK {
		return nil, fmt.Errorf("release candidate com fingerprint é obrigatório para proof-map")
	}
	fingerprint := map[string]any{"id": candidate["id"], "revision": candidate["revision"], "build": candidate["build"], "checksum": candidate["checksum"]}
	mutationSources := make([]string, 0, len(mutationValues))
	for _, mutationValue := range mutationValues {
		mutationPath, pathErr := safeStandaloneFile(mutationValue, "evidência de mutação")
		if pathErr != nil {
			return nil, fmt.Errorf("evidência de mutação ausente: %s", mutationValue)
		}
		mutation, readErr := legacyReadJSONDocument(mutationPath, "evidência de mutação")
		if readErr != nil || stateInt(mutation["schema_version"]) != 1 {
			return nil, fmt.Errorf("evidência de mutação inválida: %s", mutationValue)
		}
		mutationCandidate, candidateOK := mutation["candidate"].(map[string]any)
		command := stateString(mutation["command"])
		result := stateString(mutation["result"])
		if result == "" {
			result = stateString(mutation["status"])
		}
		if !candidateOK || strings.TrimSpace(command) == "" || !oneOf(result, "passed", "blocked") {
			return nil, fmt.Errorf("evidência de mutação incompleta: %s", mutationValue)
		}
		evidence = append(evidence, map[string]any{
			"type": "mutation", "command": command, "result": result, "evidence": mutationValue,
			"rc": mutationCandidate["id"], "revision": mutationCandidate["revision"],
			"build": mutationCandidate["build"], "checksum": mutationCandidate["checksum"],
		})
		mutationSources = append(mutationSources, mutationValue)
	}
	byCommand := make(map[string]map[string]any)
	manualGaps := make([]string, 0)
	for _, raw := range evidence {
		item := stateObject(raw)
		if command := stateString(item["command"]); command != "" {
			byCommand[command] = item
		}
		if stateString(item["type"]) == "manual_gap" && stateString(item["journey"]) != "" {
			manualGaps = append(manualGaps, stateString(item["journey"]))
		}
	}
	commands := stateStringSlice(stateObject(stateObject(state["verification"])["release"])["commands"])
	rows := make([]map[string]any, 0, len(commands))
	gaps := make([]string, 0)
	for _, command := range commands {
		item := byCommand[command]
		var evidenceFingerprint map[string]any
		if item != nil {
			identifier := item["rc"]
			if identifier == nil {
				identifier = item["id"]
			}
			evidenceFingerprint = map[string]any{"id": identifier, "revision": item["revision"], "build": item["build"], "checksum": item["checksum"]}
		}
		proven := item != nil && stateString(item["result"]) == "passed" && reflect.DeepEqual(evidenceFingerprint, fingerprint)
		row := map[string]any{"command": command, "proven": proven, "source_type": nil, "candidate": evidenceFingerprint, "evidence": nil}
		if item != nil {
			row["source_type"] = item["type"]
			row["evidence"] = item["evidence"]
		}
		rows = append(rows, row)
		if !proven {
			gaps = append(gaps, command)
		}
	}
	proof := map[string]any{
		"candidate": fingerprint, "automated": rows, "automated_total": len(rows),
		"automated_proven": len(rows) - len(gaps), "automation_gaps": gaps,
		"manual_gaps": manualGaps, "mutation_evidence": mutationSources,
	}
	output, err := legacyOutputPath(outputValue, "output")
	if err != nil {
		return nil, err
	}
	encoded, _ := legacyJSONBytes(proof, true)
	if err := atomicWrite(output, encoded); err != nil {
		return nil, err
	}
	result := map[string]any{"proof_map": outputValue}
	for key, value := range proof {
		result[key] = value
	}
	return result, nil
}
