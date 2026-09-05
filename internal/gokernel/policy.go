package gokernel

import (
	"strconv"
	"strings"
)

var structuralFindingClasses = map[string]bool{
	"crash_window": true, "partial_commit": true, "toctou": true,
	"external_effect_before_persistence": true, "retry_after_timeout": true,
	"concurrent_idempotency": true, "recovery_after_restart": true,
}

var mutationRelevantChanges = map[string]bool{
	"authorization": true, "business-rule": true, "calculation": true,
	"data-transform": true, "financial": true, "inventory": true,
	"migration": true, "money": true, "offline": true, "parser": true,
	"payment": true, "permission": true, "security": true,
	"state-machine": true, "stock": true, "sync": true,
}

var pureNonLogicChanges = map[string]bool{
	"copy": true, "docs": true, "documentation": true, "mechanical": true,
	"style": true, "visual": true,
}

func runPolicy(args []string) (map[string]any, error) {
	valueFlags := map[string]bool{
		"--profile": true, "--risk": true, "--change": true,
		"--manual-pdf": true, "--round": true, "--risk-seam": true,
		"--seam-round": true, "--structural-finding": true,
		"--consecutive-seam-findings": true,
	}
	flags, err := parseFlags(args, valueFlags, map[string]bool{"--manual-in-scope": true})
	if err != nil {
		return nil, err
	}
	profile := lastValue(flags, "--profile")
	if profile == "" {
		return nil, argparseError("the following arguments are required: --profile")
	}
	if !oneOf(profile, "lean", "standard", "full") {
		return nil, argparseError(argparseInvalidChoice("--profile", profile, []string{"lean", "standard", "full"}))
	}
	risk := lastValue(flags, "--risk")
	if risk == "" {
		return nil, argparseError("the following arguments are required: --risk")
	}
	if !oneOf(risk, "low", "medium", "high", "critical") {
		return nil, argparseError(argparseInvalidChoice("--risk", risk, []string{"low", "medium", "high", "critical"}))
	}
	manualPDF := lastValue(flags, "--manual-pdf")
	if manualPDF == "" {
		manualPDF = "scope"
	}
	if !oneOf(manualPDF, "none", "quick_start", "full", "scope") {
		return nil, argparseError(argparseInvalidChoice("--manual-pdf", manualPDF, []string{"none", "quick_start", "full", "scope"}))
	}
	round, err := intFlag(flags, "--round", 0)
	if err != nil {
		return nil, err
	}
	seamRound, hasSeamRound, err := optionalIntFlag(flags, "--seam-round")
	if err != nil {
		return nil, err
	}
	consecutive, _, err := optionalIntFlag(flags, "--consecutive-seam-findings")
	if err != nil {
		return nil, err
	}
	riskSeam := lastValue(flags, "--risk-seam")
	if (hasSeamRound || consecutive != 0) && riskSeam == "" {
		return nil, &commandError{message: "--seam-round e --consecutive-seam-findings exigem --risk-seam"}
	}
	findings := append([]string{}, flags.values["--structural-finding"]...)
	for _, finding := range findings {
		if !structuralFindingClasses[finding] {
			return nil, argparseError(argparseInvalidChoice("--structural-finding", finding, []string{"crash_window", "partial_commit", "toctou", "external_effect_before_persistence", "retry_after_timeout", "concurrent_idempotency", "recovery_after_restart"}))
		}
	}
	change := lastValue(flags, "--change")
	if change == "" {
		change = "behavioral"
	}
	return policyResult(profile, risk, change, manualPDF, flags.booleans["--manual-in-scope"], round, riskSeam, seamRound, findings, consecutive), nil
}

func policyResult(profile, risk, change, manualPDF string, manualInScope bool, round int, riskSeam string, seamRound int, findings []string, consecutive int) map[string]any {
	execution, review, cadence := "strict", "per_task", "red_green_per_task"
	if risk == "low" {
		execution, review, cadence = "grouped", "plan_gate", "group_seam"
	} else if risk == "medium" {
		execution, review, cadence = "slice", "per_slice", "slice_seam"
	}
	maxRounds := map[string]int{"lean": 2, "standard": 3, "full": 5}[profile]
	effectiveRound := maxInt(round, seamRound)
	invalidated := len(findings) > 0 || consecutive >= 2
	manualRequired := manualPDF == "quick_start" || manualPDF == "full" || (manualPDF == "scope" && manualInScope)
	manualLevel := "none"
	if manualRequired {
		manualLevel = manualPDF
	}
	normalizedChange := strings.ReplaceAll(strings.ToLower(strings.TrimSpace(change)), "_", "-")
	visualValidation := "behavioral_seam"
	if normalizedChange == "visual" {
		visualValidation = "screenshot_or_visual_regression"
	}
	var seam any
	breakerScope := "unit"
	if riskSeam != "" {
		seam = riskSeam
		breakerScope = "risk_seam"
	}
	return map[string]any{
		"execution": execution, "review": review, "test_cadence": cadence,
		"max_fix_rounds": maxRounds, "risk_seam": seam, "breaker_scope": breakerScope,
		"effective_fix_round": effectiveRound, "structural_findings": findings,
		"hypothesis_invalidated": invalidated, "redesign_required": false,
		"breaker":                     effectiveRound >= maxRounds || invalidated,
		"architecture_audit_required": false, "architecture_audit_mode": "manual_report_only",
		"manual_required": manualRequired, "manual_level": manualLevel,
		"visual_validation": visualValidation,
		"test_strategy": map[string]any{
			"fast":    []string{"targeted_unit_if_logic_changed", "targeted_integration_if_boundary_changed", "related_regression"},
			"plan":    []string{"affected_unit_suite", "affected_integration_and_contracts", "affected_regression", "critical_journey_e2e", "selective_mutation_if_required"},
			"release": []string{"complete_unit_suite", "applicable_integration_and_contracts", "critical_journey_e2e", "full_regression", "current_mutation_evidence_if_required", "release_build"},
		},
		"mutation_policy": map[string]any{
			"mode": mutationModeForChange(risk, normalizedChange), "scope": "changed_material_risk_seams",
			"run_stage": "plan_and_release_only", "global_score_gate": false,
			"blocking_rule":                     "survivor_changes_approved_high_or_critical_behavior",
			"install_new_tool_during_execution": false,
		},
		"autonomy_policy": map[string]any{
			"decision_order":  []string{"approved_owner_decision", "existing_repository_pattern", "existing_stack_and_dependencies", "official_documentation", "lowest_risk_reversible_option"},
			"stop_categories": []string{"essential_external_credential", "new_cost", "destructive_or_irreversible_action", "material_scope_contract_or_design_change", "proven_real_impossibility"},
		},
		"plan_change_policy": map[string]any{
			"implementation_detail":             "decide_and_continue",
			"bounded_amendment":                 "record_in_ledger_without_editing_approved_plan",
			"plan_invalidating_material_change": "invalidate_and_replan_affected_scope",
			"authorization_material_change":     "pause_for_owner_authorization_without_replanning",
		},
		"homologation_order": []string{"automated_regression", "coded_e2e", "proof_map", "real_system_pass", "visual_sweep"},
	}
}

func mutationModeForChange(risk, change string) string {
	if risk == "low" || pureNonLogicChanges[change] {
		return "not_required"
	}
	if risk == "high" || risk == "critical" {
		return "required_selective"
	}
	if mutationRelevantChanges[change] {
		return "selective"
	}
	return "not_required"
}

func intFlag(flags parsedFlags, name string, fallback int) (int, error) {
	value, present, err := optionalIntFlag(flags, name)
	if err != nil {
		return 0, err
	}
	if !present {
		return fallback, nil
	}
	return value, nil
}

func optionalIntFlag(flags parsedFlags, name string) (int, bool, error) {
	raw := lastValue(flags, name)
	if raw == "" {
		return 0, false, nil
	}
	value, err := strconv.Atoi(raw)
	if err != nil {
		return 0, false, argparseError("argument " + name + ": invalid int value: '" + raw + "'")
	}
	return value, true, nil
}

func oneOf(value string, choices ...string) bool {
	for _, choice := range choices {
		if value == choice {
			return true
		}
	}
	return false
}
