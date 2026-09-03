package gokernel

import (
	"encoding/json"
	"fmt"
	"io"
	"sort"
	"strconv"
	"strings"
)

const usageLine = "usage: bm <command> [options]\n"

type commandError struct {
	message   string
	argparse  bool
	rootUsage bool
	exitCode  int
}

func (e *commandError) Error() string { return e.message }

func Run(args []string, stdout, stderr io.Writer) int {
	if help, ok := staticCLIHelp(args); ok {
		_, _ = io.WriteString(stdout, help)
		return 0
	}
	if len(args) == 0 {
		return writeArgparseError(stderr, "", "the following arguments are required: command")
	}
	if spec, ok := actionCommandSpecs[args[0]]; ok {
		normalized, err := normalizeActionPosition(args[1:], spec)
		if err != nil {
			if cliErr, isCommandError := err.(*commandError); isCommandError && cliErr.argparse {
				command := args[0]
				if cliErr.rootUsage {
					command = ""
				}
				return writeArgparseError(stderr, command, cliErr.message)
			}
			fmt.Fprintln(stderr, err)
			return 2
		}
		args = append([]string{args[0]}, normalized...)
	}

	var result any
	var err error
	switch args[0] {
	case "version":
		result, err = runVersion(args[1:])
	case "validate-state":
		result, err = runValidateState(args[1:])
	case "model":
		result, err = runModel(args[1:])
	case "scope":
		result, err = runScope(args[1:])
	case "roadmap":
		result, err = runRoadmap(args[1:])
	case "coherence":
		result, err = runCoherence(args[1:])
	case "impact":
		result, err = runImpact(args[1:])
	case "plan":
		result, err = runPlan(args[1:])
	case "verify":
		result, err = runVerify(args[1:])
	case "change-policy":
		result, err = runChangePolicy(args[1:])
	case "policy":
		result, err = runPolicy(args[1:])
	case "adapter":
		result, err = runAdapter(args[1:])
	case "snapshot":
		result, err = runSnapshot(args[1:])
	case "planning-audit":
		result, err = runPlanningAudit(args[1:])
	case "design-audit":
		result, err = runDesignAudit(args[1:])
	case "planning-check":
		result, err = runPlanningCheck(args[1:])
	case "direct":
		result, err = runDirect(args[1:])
	case "debug":
		result, err = runDebug(args[1:])
	case "learn":
		result, err = runLearning(args[1:])
	case "migrate":
		result, err = runMigrate(args[1:])
	case "task-brief":
		result, err = runTaskBrief(args[1:])
	case "report":
		result, err = runReport(args[1:])
	case "review-package":
		result, err = runReviewPackage(args[1:])
	case "checkpoint":
		result, err = runCheckpoint(args[1:])
	case "proof-map":
		result, err = runProofMap(args[1:])
	case "mutation-evidence":
		result, err = runMutationEvidence(args[1:])
	case "telemetry":
		result, err = runTelemetry(args[1:])
	case "spec-diff":
		result, err = runSpecDiff(args[1:])
	case "status":
		result, err = runStatus(args[1:])
	case "workspace":
		result, err = runExecutionWorkspace(args[1:])
	case "context":
		result, err = runContext(args[1:])
	case "update-bm":
		result, err = runUpdate(args[1:])
	case "cycle-close":
		result, err = runCycleClose(args[1:])
	default:
		return writeArgparseError(stderr, "", argparseInvalidChoice("command", args[0], staticCLICommandChoices))
	}
	if err != nil {
		if cliErr, ok := err.(*commandError); ok {
			if cliErr.argparse {
				command := args[0]
				if cliErr.rootUsage {
					command = ""
				}
				return writeArgparseError(stderr, command, cliErr.message)
			}
			fmt.Fprintln(stderr, cliErr.message)
			if cliErr.exitCode > 0 {
				return cliErr.exitCode
			}
			return 2
		}
		fmt.Fprintln(stderr, err)
		return 2
	}
	if result == nil {
		return 0
	}
	if text, ok := result.(string); ok {
		_, _ = io.WriteString(stdout, text)
		return 0
	}
	encoder := json.NewEncoder(stdout)
	encoder.SetEscapeHTML(false)
	encoder.SetIndent("", "  ")
	if err := encoder.Encode(result); err != nil {
		fmt.Fprintf(stderr, "OUTPUT_ERROR: %v\n", err)
		return 2
	}
	return 0
}

type actionCommandSpec struct {
	actions      []string
	valueFlags   map[string]bool
	booleanFlags map[string]bool
}

func flagSet(names ...string) map[string]bool {
	result := make(map[string]bool, len(names))
	for _, name := range names {
		result[name] = true
	}
	return result
}

var actionCommandSpecs = map[string]actionCommandSpec{
	"adapter": {
		actions: []string{"render", "install"}, valueFlags: flagSet("--host", "--repo"), booleanFlags: flagSet("--overwrite"),
	},
	"coherence": {
		actions: []string{"check", "approve"}, valueFlags: flagSet("--repo", "--change", "--semantic-report", "--digest", "--approved-by"), booleanFlags: flagSet("--structural-only"),
	},
	"context": {
		actions: []string{"pack", "verify"}, valueFlags: flagSet("--repo", "--unit", "--output", "--max-bytes", "--path"), booleanFlags: flagSet(),
	},
	"debug": {
		actions:      []string{"start", "list", "status", "resume", "checkpoint", "finish"},
		valueFlags:   flagSet("--repo", "--id", "--objective", "--expected", "--actual", "--environment", "--origin-ref", "--origin-evidence", "--relation", "--event", "--evidence", "--hypothesis", "--experiment", "--eliminated-hypothesis", "--root-cause", "--neighbor-regression", "--residual-risk", "--status", "--reason", "--docviva-kind", "--docviva-outcome", "--docviva-artifact", "--docviva-justification", "--learning-classification", "--learning-statement", "--learning-tag", "--learning-validity", "--learning-conflict"),
		booleanFlags: flagSet(),
	},
	"design-audit": {
		actions: []string{"seal", "verify"}, valueFlags: flagSet("--root", "--scope", "--manifest"), booleanFlags: flagSet(),
	},
	"direct": {
		actions: []string{"classify", "start", "status", "checkpoint", "finish", "reopen"}, valueFlags: directValueFlags, booleanFlags: directBooleanFlags,
	},
	"impact": {
		actions: []string{"analyze"}, valueFlags: flagSet("--repo", "--change", "--plan", "--changed-contract", "--changed-ownership", "--changed-interface", "--changed-data", "--changed-migration", "--changed-journey", "--changed-effect", "--changed-invariant"), booleanFlags: flagSet("--global-change"),
	},
	"learn": {
		actions: []string{"propose", "list", "approve", "reject", "deactivate"}, valueFlags: learningValueFlags, booleanFlags: flagSet(),
	},
	"migrate": {
		actions: []string{"check", "apply"}, valueFlags: flagSet("--repo"), booleanFlags: flagSet(),
	},
	"model": {
		actions: []string{"init", "validate"}, valueFlags: flagSet("--repo", "--change"), booleanFlags: flagSet(),
	},
	"mutation-evidence": {
		actions: []string{"verify"}, valueFlags: flagSet("--state", "--root", "--plan", "--risk-seam", "--tool", "--command", "--report", "--revision", "--classifications", "--output"), booleanFlags: flagSet(),
	},
	"plan": {
		actions: []string{"complete", "reopen"}, valueFlags: flagSet("--repo", "--change", "--plan", "--task", "--context-pack", "--actual-delta", "--result", "--verification", "--proof", "--review", "--reason", "--completed-task"), booleanFlags: flagSet(),
	},
	"planning-check": {
		actions: []string{"record"}, valueFlags: flagSet("--state", "--root", "--report"), booleanFlags: flagSet(),
	},
	"roadmap": {
		actions: []string{"sync", "next-wave"}, valueFlags: flagSet("--repo", "--change", "--format"), booleanFlags: flagSet(),
	},
	"scope": {
		actions: []string{"seal", "verify"}, valueFlags: flagSet("--repo", "--change", "--source", "--draft", "--pages", "--extraction"), booleanFlags: flagSet(),
	},
	"snapshot": {
		actions: []string{"create", "verify"}, valueFlags: flagSet("--root"), booleanFlags: flagSet(),
	},
	"telemetry": {
		actions: []string{"record", "summary"}, valueFlags: flagSet("--state", "--root", "--plan", "--phase", "--at", "--input-tokens", "--output-tokens", "--duration-ms", "--fix-rounds", "--gate-failures", "--homologation-bugs"), booleanFlags: flagSet(),
	},
	"workspace": {
		actions: []string{"create", "check", "locate", "resume", "finish"}, valueFlags: flagSet("--repo", "--plan", "--change", "--target"), booleanFlags: flagSet(),
	},
	"verify": {
		actions:      []string{"task", "plan", "release", "review", "status"},
		valueFlags:   flagSet("--repo", "--change", "--plan", "--task", "--context-pack", "--evidence", "--retry-reason", "--scope", "--reviewer", "--verdict", "--proof", "--finding", "--build", "--checksum", "--delivery"),
		booleanFlags: flagSet(),
	},
}

func normalizeActionPosition(args []string, spec actionCommandSpec) ([]string, error) {
	position := -1
	separator := -1
	for index := 0; index < len(args); index++ {
		arg := args[index]
		if arg == "--" {
			separator = index
			if index+1 < len(args) {
				position = index + 1
			}
			break
		}
		requested, value, equals := strings.Cut(arg, "=")
		name, kind, matches := resolveFlag(requested, spec.valueFlags, spec.booleanFlags)
		if len(matches) > 1 {
			return nil, argparseError("ambiguous option: " + requested + " could match " + strings.Join(matches, ", "))
		}
		if equals {
			if kind == "boolean" {
				return nil, argparseError("argument " + name + ": ignored explicit argument '" + value + "'")
			}
			if kind == "value" || strings.HasPrefix(arg, "--") {
				continue
			}
		}
		if kind == "boolean" || strings.HasPrefix(arg, "--") && kind == "" {
			continue
		}
		if kind == "value" {
			if index+1 >= len(args) || strings.HasPrefix(args[index+1], "--") {
				return nil, argparseError("argument " + name + ": expected one argument")
			}
			index++
			continue
		}
		position = index
		break
	}
	if position < 0 {
		return nil, argparseError("the following arguments are required: action")
	}
	action := args[position]
	if !oneOf(action, spec.actions...) {
		return nil, argparseError(argparseInvalidChoice("action", action, spec.actions))
	}
	if position == 0 {
		return args, nil
	}
	normalized := []string{action}
	before := args[:position]
	if separator >= 0 {
		before = args[:separator]
	}
	normalized = append(normalized, before...)
	normalized = append(normalized, args[position+1:]...)
	return normalized, nil
}

func writeArgparseError(stderr io.Writer, command, message string) int {
	usage := usageLine
	program := "bm"
	if help, ok := staticCLIHelpByPath[command]; ok {
		usage = strings.SplitN(help, "\n\n", 2)[0] + "\n"
	}
	if command != "" {
		program += " " + command
	}
	_, _ = io.WriteString(stderr, usage)
	fmt.Fprintf(stderr, "%s: error: %s\n", program, message)
	return 2
}

func argparseError(message string) error {
	return &commandError{message: message, argparse: true}
}

func unrecognizedArgumentsError(arguments []string) error {
	return &commandError{message: "unrecognized arguments: " + strings.Join(arguments, " "), argparse: true, rootUsage: true}
}

func argparseInvalidChoice(label, value string, choices []string) string {
	quoted := make([]string, 0, len(choices))
	for _, choice := range choices {
		quoted = append(quoted, "'"+choice+"'")
	}
	return fmt.Sprintf("argument %s: invalid choice: '%s' (choose from %s)", label, value, strings.Join(quoted, ", "))
}

func domainError(code, message string) error {
	return &commandError{message: code + ": " + message}
}

func riskInputError(message string) error {
	return &commandError{message: "RISK_PATH_INVALID: " + message, exitCode: 3}
}

func runVersion(args []string) (any, error) {
	if len(args) == 0 {
		return fmt.Sprintf("bm %s (go, %s)\n", Version, BuildCommit), nil
	}
	flags, err := parseFlags(args, map[string]bool{}, map[string]bool{"--json": true})
	if err != nil {
		return nil, err
	}
	if flags.booleans["--json"] {
		return versionMetadata(), nil
	}
	return nil, unrecognizedArgumentsError(args)
}

func runChangePolicy(args []string) (any, error) {
	valid := map[string]bool{
		"--scope-change":           false,
		"--public-contract-change": false,
		"--approved-design-change": false,
		"--new-cost":               false,
		"--irreversible-action":    false,
		"--external-impossibility": false,
		"--critical-invariant":     false,
		"--plan-command":           false,
		"--file-location":          false,
		"--internal-order":         false,
	}
	flags, err := parseFlags(args, map[string]bool{}, valid)
	if err != nil {
		return nil, err
	}
	for name := range valid {
		valid[name] = flags.booleans[name]
	}
	planInvalidating := valid["--scope-change"] || valid["--public-contract-change"] ||
		valid["--approved-design-change"] || valid["--external-impossibility"] ||
		valid["--critical-invariant"]
	authorizationOnly := (valid["--new-cost"] || valid["--irreversible-action"]) && !planInvalidating
	bounded := valid["--plan-command"] || valid["--file-location"] || valid["--internal-order"]

	classification := "implementation_detail"
	action := "decide_reversibly_record_if_material_and_continue"
	reapproval := false
	if planInvalidating {
		classification = "material_change"
		action = "invalidate_package_and_replan_affected_scope"
		reapproval = true
	} else if authorizationOnly {
		classification = "material_change"
		action = "pause_for_owner_authorization_without_replanning"
		reapproval = true
	} else if bounded {
		classification = "bounded_amendment"
		action = "record_in_ledger_and_continue"
	}
	return map[string]any{
		"action":                action,
		"classification":        classification,
		"extra_review_required": planInvalidating,
		"plan_files_mutable":    false,
		"plan_invalidating":     planInvalidating,
		"reapproval_required":   reapproval,
		"redesign_allowed":      planInvalidating,
	}, nil
}

type parsedFlags struct {
	values   map[string][]string
	booleans map[string]bool
}

func parseFlags(args []string, valueFlags, booleanFlags map[string]bool) (parsedFlags, error) {
	result, positionals, err := parseArgumentsMode(args, valueFlags, booleanFlags, false)
	if err != nil {
		return result, err
	}
	if len(positionals) > 0 {
		return result, unrecognizedArgumentsError(positionals)
	}
	return result, nil
}

func parseArguments(args []string, valueFlags, booleanFlags map[string]bool) (parsedFlags, []string, error) {
	return parseArgumentsMode(args, valueFlags, booleanFlags, true)
}

func parseArgumentsMode(args []string, valueFlags, booleanFlags map[string]bool, allowPositionals bool) (parsedFlags, []string, error) {
	result := parsedFlags{values: map[string][]string{}, booleans: map[string]bool{}}
	unknown := make([]string, 0)
	positionals := make([]string, 0)
	for index := 0; index < len(args); index++ {
		arg := args[index]
		if arg == "--" {
			remaining := args[index+1:]
			if allowPositionals {
				positionals = append(positionals, remaining...)
				break
			}
			if len(remaining) == 0 {
				unknown = append(unknown, "--")
			} else {
				unknown = append(unknown, remaining...)
				positionals = append(positionals, remaining...)
			}
			break
		}
		requested, value, equals := strings.Cut(arg, "=")
		name, kind, matches := resolveFlag(requested, valueFlags, booleanFlags)
		if len(matches) > 1 {
			return result, positionals, argparseError("ambiguous option: " + requested + " could match " + strings.Join(matches, ", "))
		}
		if equals {
			if kind == "value" {
				result.values[name] = append(result.values[name], value)
				continue
			}
			if kind == "boolean" {
				return result, positionals, argparseError("argument " + name + ": ignored explicit argument '" + value + "'")
			}
			unknown = append(unknown, arg)
			continue
		}
		if kind == "boolean" {
			result.booleans[name] = true
			continue
		}
		if kind == "value" {
			if index+1 >= len(args) || strings.HasPrefix(args[index+1], "--") {
				return result, positionals, argparseError("argument " + name + ": expected one argument")
			}
			index++
			result.values[name] = append(result.values[name], args[index])
			continue
		}
		if strings.HasPrefix(arg, "--") {
			unknown = append(unknown, arg)
		} else {
			positionals = append(positionals, arg)
			if !allowPositionals {
				unknown = append(unknown, arg)
			}
		}
	}
	hasUnknownFlag := false
	for _, arg := range unknown {
		if strings.HasPrefix(arg, "--") {
			hasUnknownFlag = true
			break
		}
	}
	if hasUnknownFlag {
		return result, positionals, unrecognizedArgumentsError(unknown)
	}
	return result, positionals, nil
}

func resolveFlag(requested string, valueFlags, booleanFlags map[string]bool) (string, string, []string) {
	if requested == "--" {
		return "", "", nil
	}
	if valueFlags[requested] {
		return requested, "value", []string{requested}
	}
	if booleanFlags[requested] {
		return requested, "boolean", []string{requested}
	}
	if !strings.HasPrefix(requested, "--") {
		return "", "", nil
	}
	matches := make([]string, 0)
	for name := range valueFlags {
		if strings.HasPrefix(name, requested) {
			matches = append(matches, name)
		}
	}
	for name := range booleanFlags {
		if strings.HasPrefix(name, requested) {
			matches = append(matches, name)
		}
	}
	sort.Strings(matches)
	if len(matches) != 1 {
		return "", "", matches
	}
	name := matches[0]
	if valueFlags[name] {
		return name, "value", matches
	}
	return name, "boolean", matches
}

func lastValue(flags parsedFlags, name string) string {
	values := flags.values[name]
	if len(values) == 0 {
		return ""
	}
	return values[len(values)-1]
}

func scoreValue(flags parsedFlags, name string) (int, error) {
	raw := lastValue(flags, name)
	if raw == "" {
		return 0, nil
	}
	value, err := strconv.Atoi(raw)
	if err != nil {
		return 0, argparseError("argument " + name + ": invalid int value: '" + raw + "'")
	}
	if value < 0 || value > 2 {
		return 0, argparseError(argparseInvalidChoice(name, raw, []string{"0", "1", "2"}))
	}
	return value, nil
}
