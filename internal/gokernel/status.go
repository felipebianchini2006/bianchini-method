package gokernel

import (
	"fmt"
	"strings"
)

func runStatus(args []string) (any, error) {
	flags, positionals, err := parseArguments(args, map[string]bool{"--format": true, "--root": true}, map[string]bool{})
	if err != nil {
		return nil, err
	}
	if len(positionals) == 0 {
		return nil, argparseError("the following arguments are required: state")
	}
	if len(positionals) > 1 {
		return nil, unrecognizedArgumentsError(positionals[1:])
	}
	state := positionals[0]
	format := lastValue(flags, "--format")
	if format == "" {
		format = "json"
	}
	root := lastValue(flags, "--root")
	if format != "json" && format != "text" {
		return nil, argparseError(argparseInvalidChoice("--format", format, []string{"json", "text"}))
	}
	path, err := safeStandaloneFile(state, "state")
	if err != nil {
		return nil, err
	}
	snapshot, err := loadStateFile(path)
	if err != nil {
		return nil, err
	}
	if stateInt(snapshot["method_version"]) == 1 {
		if format == "json" {
			return map[string]any{
				"implicit_legacy": false,
				"method_mode":     "legacy-superpowers",
				"method_version":  1,
				"mode":            "legacy-superpowers",
				"status":          "legacy",
			}, nil
		}
		return "# Status do projeto\n\n- Método: v1 legado (Superpowers)\n- Marcador implícito: não\n", nil
	}
	validated, err := validateStateValue(snapshot, "")
	if err != nil {
		return nil, err
	}
	summary, err := statusV2Summary(validated, state, root)
	if err != nil {
		return nil, err
	}
	if format == "json" {
		return summary, nil
	}
	return renderStatusV2(summary, statusPlanOrder(validated)), nil
}

func statusV2Summary(state map[string]any, statePath, root string) (map[string]any, error) {
	plans := stateArray(state["plans"])
	declared := stateObject(state["active_execution"])
	activePlanID := stateString(declared["plan_id"])
	if activePlanID == "" {
		for _, rawPlan := range plans {
			plan := stateObject(rawPlan)
			if stateString(plan["status"]) == "in_progress" {
				activePlanID = stateString(plan["id"])
				break
			}
		}
	}
	activePlan := map[string]any{}
	completed := map[string]bool{}
	planStatuses := map[string]any{}
	for _, rawPlan := range plans {
		plan := stateObject(rawPlan)
		identifier := stateString(plan["id"])
		planStatuses[identifier] = stateString(plan["status"])
		if stateString(plan["status"]) == "completed" {
			completed[identifier] = true
		}
		if identifier == activePlanID {
			activePlan = plan
		}
	}
	nextPlan := map[string]any{}
	for _, rawPlan := range plans {
		plan := stateObject(rawPlan)
		if stateString(plan["status"]) != "approved" {
			continue
		}
		ready := true
		for _, dependency := range stateStringSlice(plan["depends_on"]) {
			if !completed[dependency] {
				ready = false
				break
			}
		}
		if ready {
			nextPlan = plan
			break
		}
	}
	telemetryConfig := stateObject(state["telemetry"])
	telemetry := map[string]any{"enabled": stateBool(telemetryConfig["enabled"]), "path": telemetryConfig["path"]}
	if root != "" {
		var err error
		telemetry, err = legacyTelemetrySummaryFromState(state, root)
		if err != nil {
			return nil, err
		}
	}
	verification := map[string]any{}
	for key, raw := range stateObject(state["verification"]) {
		verification[key] = stateString(stateObject(raw)["status"])
	}
	planning := stateObject(state["planning"])
	approval := stateObject(state["approval"])
	approvalPackage := stateObject(approval["package"])
	var activePlanValue any
	var activeUnitValue any
	var executionModeValue any
	var gateValue any
	var workspaceValue any
	if activePlanID != "" {
		activePlanValue = activePlanID
	}
	if value := stateString(declared["unit"]); value != "" {
		activeUnitValue = value
	}
	if value := stateString(activePlan["execution"]); value != "" {
		executionModeValue = value
	}
	if value := stateString(declared["gate"]); value != "" {
		gateValue = value
	}
	if value := stateString(declared["workspace"]); value != "" {
		workspaceValue = value
	}
	var nextPlanValue any
	var nextModeValue any
	if value := stateString(nextPlan["id"]); value != "" {
		nextPlanValue = value
	}
	if value := stateString(nextPlan["execution"]); value != "" {
		nextModeValue = value
	}
	return map[string]any{
		"method_version":            2,
		"method_mode":               state["method_mode"],
		"assurance_profile":         state["assurance_profile"],
		"planning_version":          state["planning_version"],
		"planning_status":           state["planning_status"],
		"planning_quality_version":  nullableInt(planning["quality_version"]),
		"readiness":                 planning["readiness"],
		"user_actions":              planning["user_actions"],
		"design_manifest":           planning["design_manifest"],
		"change_root":               planning["change_root"],
		"current_specs":             planning["current_specs"],
		"checker":                   planning["checker"],
		"approval":                  approval["status"],
		"approval_digest":           approvalPackage["manifest_digest"],
		"approved_plans":            approval["approved_plans"],
		"architecture_audit":        state["architecture_audit"],
		"architecture_audit_status": state["architecture_audit_status"],
		"manual_pdf":                state["manual_pdf"],
		"plans":                     planStatuses,
		"active_plan":               activePlanValue,
		"active_unit":               activeUnitValue,
		"execution_mode":            executionModeValue,
		"next_plan":                 nextPlanValue,
		"next_execution_mode":       nextModeValue,
		"current_gate":              gateValue,
		"workspace":                 workspaceValue,
		"active_execution": map[string]any{
			"plan": activePlanValue, "unit": activeUnitValue, "mode": executionModeValue,
			"gate": gateValue, "workspace": workspaceValue,
		},
		"verification": verification,
		"telemetry":    telemetry,
		"release":      state["release"],
		"blockers":     state["blockers"],
		"next_action":  state["next_action"],
	}, nil
}

func nullableInt(value any) any {
	if value == nil {
		return nil
	}
	return stateInt(value)
}

func renderStatusV2(summary map[string]any, planOrder []string) string {
	plans := formatStatusPairs(stateObject(summary["plans"]), planOrder)
	verification := formatStatusPairs(stateObject(summary["verification"]), []string{"fast", "plan", "release"})
	release := stateObject(summary["release"])
	blockers := stateArray(summary["blockers"])
	telemetry := stateObject(summary["telemetry"])
	telemetryLine := "desativada"
	if stateBool(telemetry["enabled"]) {
		if _, hasTotals := telemetry["totals"]; hasTotals {
			totals := stateObject(telemetry["totals"])
			telemetryLine = fmt.Sprintf(
				"ativa, registros=%d, tokens=%d, duração_ms=%d, fix_rounds=%d, falhas_gate=%d, bugs_homologação=%d",
				stateInt(telemetry["records"]), stateInt(totals["input_tokens"])+stateInt(totals["output_tokens"]),
				stateInt(totals["duration_ms"]), stateInt(totals["fix_rounds"]), stateInt(totals["gate_failures"]),
				stateInt(totals["homologation_bugs"]),
			)
		} else {
			telemetryLine = "ativa (resumo exige --root)"
		}
	}
	checker := stateObject(summary["checker"])
	return "# Status do projeto\n\n" +
		fmt.Sprintf("- Método: v2 %s / planejamento %s\n", statusText(summary["method_mode"], "n/a"), statusText(summary["planning_version"], "n/a")) +
		fmt.Sprintf("- Perfil: %s\n", statusText(summary["assurance_profile"], "n/a")) +
		fmt.Sprintf("- Planejamento: %s / qualidade v%s\n", statusText(summary["planning_status"], "n/a"), statusText(summary["planning_quality_version"], "legado")) +
		fmt.Sprintf("- Readiness: %s / checker %s\n", statusText(summary["readiness"], "não aplicável"), statusText(checker["status"], "não aplicável")) +
		fmt.Sprintf("- Design: %s\n", statusText(summary["design_manifest"], "não aplicável")) +
		fmt.Sprintf("- Specs atuais: %s / mudança %s\n", statusText(summary["current_specs"], "não aplicável"), statusText(summary["change_root"], "não aplicável")) +
		fmt.Sprintf("- Aprovação: %s / digest %s\n", statusText(summary["approval"], "n/a"), statusText(summary["approval_digest"], "None")) +
		fmt.Sprintf("- Planos: %s\n", statusText(plans, "nenhum")) +
		fmt.Sprintf("- Plano ativo: %s / unidade %s / modo %s\n", statusText(summary["active_plan"], "nenhum"), statusText(summary["active_unit"], "nenhuma"), statusText(summary["execution_mode"], "n/a")) +
		fmt.Sprintf("- Próximo plano: %s / modo %s\n", statusText(summary["next_plan"], "nenhum"), statusText(summary["next_execution_mode"], "n/a")) +
		fmt.Sprintf("- Gate atual: %s\n", statusText(summary["current_gate"], "nenhum")) +
		fmt.Sprintf("- Gates: %s\n", verification) +
		fmt.Sprintf("- Release: %s / homologação %s / revisão %s / entrega %s\n", statusText(release["status"], "n/a"), statusText(release["homologation"], "n/a"), statusText(release["final_review"], "n/a"), statusText(release["delivery"], "n/a")) +
		fmt.Sprintf("- Auditoria: %s / %s\n", statusText(summary["architecture_audit"], "n/a"), statusText(summary["architecture_audit_status"], "n/a")) +
		fmt.Sprintf("- Manual: %s\n", statusText(summary["manual_pdf"], "n/a")) +
		fmt.Sprintf("- Telemetria: %s\n", telemetryLine) +
		fmt.Sprintf("- Bloqueios: %d\n", len(blockers)) +
		fmt.Sprintf("- Próxima ação: %s\n", statusText(summary["next_action"], ""))
}

func statusText(value any, fallback string) string {
	if value == nil {
		return fallback
	}
	if text, ok := value.(string); ok {
		if text == "" {
			return fallback
		}
		return text
	}
	if number := stateInt(value); number != 0 {
		return fmt.Sprintf("%d", number)
	}
	return fallback
}

func formatStatusPairs(values map[string]any, keys []string) string {
	parts := make([]string, 0, len(keys))
	for _, key := range keys {
		if value, exists := values[key]; exists {
			parts = append(parts, key+"="+statusText(value, ""))
		}
	}
	return strings.Join(parts, ", ")
}

func statusPlanOrder(state map[string]any) []string {
	result := make([]string, 0, len(stateArray(state["plans"])))
	for _, raw := range stateArray(state["plans"]) {
		if identifier := stateString(stateObject(raw)["id"]); identifier != "" {
			result = append(result, identifier)
		}
	}
	return result
}
