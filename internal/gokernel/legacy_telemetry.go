package gokernel

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"
)

var legacyTelemetryMetrics = []string{
	"input_tokens", "output_tokens", "duration_ms", "fix_rounds",
	"gate_failures", "homologation_bugs",
}

var legacyTelemetryPhases = map[string]bool{
	"planning": true, "execution": true, "gate": true,
	"homologation": true, "final_review": true,
}

func runTelemetry(args []string) (any, error) {
	if len(args) == 0 {
		return nil, argparseError("the following arguments are required: action")
	}
	action := args[0]
	if !oneOf(action, "record", "summary") {
		return nil, argparseError(fmt.Sprintf("argument action: invalid choice: '%s'", action))
	}
	valueFlags := map[string]bool{
		"--state": true, "--root": true, "--plan": true, "--phase": true, "--at": true,
	}
	for _, metric := range legacyTelemetryMetrics {
		valueFlags["--"+strings.ReplaceAll(metric, "_", "-")] = true
	}
	flags, err := parseFlags(args[1:], valueFlags, map[string]bool{})
	if err != nil {
		return nil, err
	}
	if err := legacyRequiredFlags(flags, "--state", "--root"); err != nil {
		return nil, err
	}
	phase := lastValue(flags, "--phase")
	if phase == "" {
		phase = "execution"
	}
	if !legacyTelemetryPhases[phase] {
		return nil, argparseError("argument --phase: invalid choice: '" + phase + "'")
	}
	metrics := make(map[string]int, len(legacyTelemetryMetrics))
	for _, metric := range legacyTelemetryMetrics {
		flag := "--" + strings.ReplaceAll(metric, "_", "-")
		raw := lastValue(flags, flag)
		if raw == "" {
			metrics[metric] = 0
			continue
		}
		value, parseErr := strconv.Atoi(raw)
		if parseErr != nil {
			return nil, argparseError("argument " + flag + ": invalid int value: '" + raw + "'")
		}
		metrics[metric] = value
	}
	if action == "summary" {
		return legacyTelemetrySummary(lastValue(flags, "--state"), lastValue(flags, "--root"))
	}
	return legacyTelemetryRecord(
		lastValue(flags, "--state"), lastValue(flags, "--root"), lastValue(flags, "--plan"),
		phase, lastValue(flags, "--at"), metrics,
	)
}

func legacyTelemetryState(stateValue string) (map[string]any, error) {
	statePath, err := safeStandaloneFile(stateValue, "state")
	if err != nil {
		return nil, err
	}
	return validateStateFile(statePath, "")
}

func legacyTelemetryDestination(state map[string]any, rootValue string) (string, bool, error) {
	config, ok := state["telemetry"].(map[string]any)
	if !ok || !stateBool(config["enabled"]) {
		return "", false, nil
	}
	root, err := safeRoot(rootValue)
	if err != nil {
		return "", false, fmt.Errorf("raiz de telemetria não encontrada: %s", rootValue)
	}
	path := stateString(config["path"])
	if path == "" {
		return "", false, fmt.Errorf("telemetry.path é obrigatório quando telemetria está habilitada")
	}
	destination, err := confinedPath(root, path, "telemetry.path", false)
	if err != nil {
		return "", false, err
	}
	return destination, true, nil
}

func legacyTelemetryRecord(stateValue, rootValue, plan, phase, recordedAt string, metrics map[string]int) (map[string]any, error) {
	state, err := legacyTelemetryState(stateValue)
	if err != nil {
		return nil, err
	}
	destination, enabled, err := legacyTelemetryDestination(state, rootValue)
	if err != nil {
		return nil, err
	}
	if !enabled {
		return map[string]any{"enabled": false, "recorded": false}, nil
	}
	if plan != "" {
		found := false
		for _, raw := range stateArray(state["plans"]) {
			if stateString(stateObject(raw)["id"]) == plan {
				found = true
				break
			}
		}
		if !found {
			return nil, fmt.Errorf("plano de telemetria inexistente: %s", plan)
		}
	}
	positive := false
	for _, value := range metrics {
		if value < 0 {
			return nil, fmt.Errorf("métricas de telemetria não podem ser negativas")
		}
		if value > 0 {
			positive = true
		}
	}
	if !positive {
		return nil, fmt.Errorf("informe ao menos uma métrica maior que zero")
	}
	if recordedAt == "" {
		recordedAt = time.Now().UTC().Format("2006-01-02T15:04:05.999999999+00:00")
	} else if !legacyISO8601(recordedAt) {
		return nil, fmt.Errorf("--at deve usar timestamp ISO-8601")
	}
	var planValue any
	if plan != "" {
		planValue = plan
	}
	record := map[string]any{
		"schema_version": 1, "recorded_at": recordedAt, "plan": planValue,
		"phase": phase, "metrics": metrics,
	}
	line, err := legacyCompactJSON(record)
	if err != nil {
		return nil, err
	}
	if err := os.MkdirAll(filepath.Dir(destination), 0o755); err != nil {
		return nil, err
	}
	stream, err := os.OpenFile(destination, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0o666)
	if err != nil {
		return nil, err
	}
	_, writeErr := stream.Write(append(line, '\n'))
	closeErr := stream.Close()
	if writeErr != nil {
		return nil, writeErr
	}
	if closeErr != nil {
		return nil, closeErr
	}
	return map[string]any{"enabled": true, "recorded": true, "path": destination, "record": record}, nil
}

func legacyISO8601(value string) bool {
	normalized := strings.Replace(value, "Z", "+00:00", 1)
	for _, layout := range []string{
		"2006-01-02T15:04:05.999999999Z07:00", "2006-01-02T15:04:05Z07:00",
		"2006-01-02T15:04:05.999999999", "2006-01-02T15:04:05",
		"2006-01-02 15:04:05.999999999Z07:00", "2006-01-02 15:04:05Z07:00",
		"2006-01-02 15:04:05.999999999", "2006-01-02 15:04:05", time.DateOnly,
	} {
		if _, err := time.Parse(layout, normalized); err == nil {
			return true
		}
	}
	return false
}

func legacyTelemetryEmptyMetrics() map[string]any {
	result := make(map[string]any, len(legacyTelemetryMetrics))
	for _, metric := range legacyTelemetryMetrics {
		result[metric] = 0
	}
	return result
}

func legacyTelemetrySummary(stateValue, rootValue string) (map[string]any, error) {
	state, err := legacyTelemetryState(stateValue)
	if err != nil {
		return nil, err
	}
	return legacyTelemetrySummaryFromState(state, rootValue)
}

func legacyTelemetrySummaryFromState(state map[string]any, rootValue string) (map[string]any, error) {
	destination, enabled, err := legacyTelemetryDestination(state, rootValue)
	if err != nil {
		return nil, err
	}
	if !enabled {
		return map[string]any{"enabled": false, "records": 0, "totals": legacyTelemetryEmptyMetrics(), "plans": map[string]any{}}, nil
	}
	data, readErr := os.ReadFile(destination)
	if os.IsNotExist(readErr) {
		return map[string]any{"enabled": true, "path": destination, "records": 0, "totals": legacyTelemetryEmptyMetrics(), "plans": map[string]any{}}, nil
	}
	if readErr != nil {
		return nil, readErr
	}
	totals := legacyTelemetryEmptyMetrics()
	plans := make(map[string]any)
	records := 0
	for index, line := range strings.Split(string(data), "\n") {
		if strings.TrimSpace(line) == "" {
			continue
		}
		var record map[string]any
		decoder := json.NewDecoder(bytes.NewReader([]byte(line)))
		decoder.UseNumber()
		if decodeErr := decoder.Decode(&record); decodeErr != nil {
			return nil, fmt.Errorf("telemetria inválida na linha %d: %s", index+1, legacyJSONErrorMessage(decodeErr))
		}
		var trailing any
		if trailingErr := decoder.Decode(&trailing); trailingErr != io.EOF {
			return nil, fmt.Errorf("telemetria inválida na linha %d: dados extras", index+1)
		}
		metrics, ok := record["metrics"].(map[string]any)
		if !ok {
			return nil, fmt.Errorf("telemetria inválida na linha %d: metrics ausente", index+1)
		}
		records++
		plan := stateString(record["plan"])
		if plan == "" {
			plan = "_release"
		}
		planTotals, ok := plans[plan].(map[string]any)
		if !ok {
			planTotals = legacyTelemetryEmptyMetrics()
			plans[plan] = planTotals
		}
		for _, metric := range legacyTelemetryMetrics {
			value, metricErr := legacyTelemetryInteger(metrics[metric])
			if metricErr != nil || value < 0 {
				return nil, fmt.Errorf("telemetria inválida na linha %d: %s", index+1, metric)
			}
			totals[metric] = stateInt(totals[metric]) + value
			planTotals[metric] = stateInt(planTotals[metric]) + value
		}
	}
	return map[string]any{"enabled": true, "path": destination, "records": records, "totals": totals, "plans": plans}, nil
}

func legacyTelemetryInteger(value any) (int, error) {
	if value == nil {
		return 0, nil
	}
	switch number := value.(type) {
	case json.Number:
		parsed, err := strconv.ParseInt(number.String(), 10, 64)
		if err != nil {
			return 0, err
		}
		return int(parsed), nil
	case int:
		return number, nil
	default:
		return 0, fmt.Errorf("não inteiro")
	}
}

func legacyJSONErrorMessage(err error) string {
	if syntax, ok := err.(*json.SyntaxError); ok {
		return syntax.Error()
	}
	return err.Error()
}
