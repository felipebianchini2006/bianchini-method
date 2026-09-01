package gokernel

import (
	"encoding/json"
	"fmt"
	"io"
	"strconv"
	"strings"
)

const usageLine = "usage: bm <command> [options]\n"

type commandError struct {
	message  string
	argparse bool
	exitCode int
}

func (e *commandError) Error() string { return e.message }

func Run(args []string, stdout, stderr io.Writer) int {
	if len(args) == 0 {
		return writeArgparseError(stderr, "the following arguments are required: command")
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
		result, err = runWorkspace(args[1:])
	default:
		return writeArgparseError(stderr, fmt.Sprintf("argument command: invalid choice: '%s'", args[0]))
	}
	if err != nil {
		if cliErr, ok := err.(*commandError); ok {
			if cliErr.argparse {
				return writeArgparseError(stderr, cliErr.message)
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
	if err := encoder.Encode(result); err != nil {
		fmt.Fprintf(stderr, "OUTPUT_ERROR: %v\n", err)
		return 2
	}
	return 0
}

func writeArgparseError(stderr io.Writer, message string) int {
	_, _ = io.WriteString(stderr, usageLine)
	fmt.Fprintf(stderr, "bm: error: %s\n", message)
	return 2
}

func argparseError(message string) error {
	return &commandError{message: message, argparse: true}
}

func domainError(code, message string) error {
	return &commandError{message: code + ": " + message}
}

func riskInputError(message string) error {
	return &commandError{message: "RISK_PATH_INVALID: " + message, exitCode: 3}
}

func runVersion(args []string) (any, error) {
	if len(args) == 0 {
		return fmt.Sprintf("bm-preview %s (go-preview, %s)\n", Version, BuildCommit), nil
	}
	if len(args) == 1 && args[0] == "--json" {
		return versionMetadata(), nil
	}
	return nil, argparseError("unrecognized arguments: " + strings.Join(args, " "))
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
	for _, arg := range args {
		if _, ok := valid[arg]; !ok {
			return nil, argparseError("unrecognized arguments: " + arg)
		}
		valid[arg] = true
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

func runWorkspace(args []string) (any, error) {
	if len(args) == 0 {
		return nil, argparseError("the following arguments are required: action")
	}
	if args[0] != "create" {
		return nil, argparseError(fmt.Sprintf("argument action: invalid choice: '%s'", args[0]))
	}
	unknown := make([]string, 0)
	for index := 1; index < len(args); index++ {
		arg := args[index]
		switch arg {
		case "--repo", "--plan":
			if index+1 >= len(args) {
				return nil, argparseError("argument " + arg + ": expected one argument")
			}
			index++
		default:
			unknown = append(unknown, arg)
			if strings.HasPrefix(arg, "--") && index+1 < len(args) && !strings.HasPrefix(args[index+1], "--") {
				unknown = append(unknown, args[index+1])
				index++
			}
		}
	}
	if len(unknown) > 0 {
		return nil, argparseError("unrecognized arguments: " + strings.Join(unknown, " "))
	}
	return nil, domainError("NOT_IMPLEMENTED", "workspace create não está disponível no backend go-preview")
}

type parsedFlags struct {
	values   map[string][]string
	booleans map[string]bool
}

func parseFlags(args []string, valueFlags, booleanFlags map[string]bool) (parsedFlags, error) {
	result := parsedFlags{values: map[string][]string{}, booleans: map[string]bool{}}
	unknown := make([]string, 0)
	for index := 0; index < len(args); index++ {
		arg := args[index]
		if booleanFlags[arg] {
			result.booleans[arg] = true
			continue
		}
		if valueFlags[arg] {
			if index+1 >= len(args) {
				return result, argparseError("argument " + arg + ": expected one argument")
			}
			index++
			result.values[arg] = append(result.values[arg], args[index])
			continue
		}
		unknown = append(unknown, arg)
	}
	if len(unknown) > 0 {
		return result, argparseError("unrecognized arguments: " + strings.Join(unknown, " "))
	}
	return result, nil
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
	if err != nil || value < 0 || value > 2 {
		return 0, argparseError("argument " + name + ": invalid choice: '" + raw + "'")
	}
	return value, nil
}
