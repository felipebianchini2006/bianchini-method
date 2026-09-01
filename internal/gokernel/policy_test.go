package gokernel

import (
	"encoding/json"
	"reflect"
	"strings"
	"testing"
)

func TestPolicyVerticalParity(t *testing.T) {
	tests := []struct {
		name string
		args []string
		want map[string]any
	}{
		{
			name: "lean low visual",
			args: []string{"policy", "--profile", "lean", "--risk", "low", "--change", "visual"},
			want: map[string]any{
				"execution": "grouped", "review": "plan_gate", "test_cadence": "group_seam",
				"max_fix_rounds": float64(2), "risk_seam": nil, "breaker_scope": "unit",
				"effective_fix_round": float64(0), "structural_findings": []any{},
				"hypothesis_invalidated": false, "redesign_required": false, "breaker": false,
				"architecture_audit_required": false, "architecture_audit_mode": "manual_report_only",
				"manual_required": false, "manual_level": "none",
				"visual_validation": "screenshot_or_visual_regression",
			},
		},
		{
			name: "critical structural breaker",
			args: []string{
				"policy", "--profile", "full", "--risk", "critical", "--round", "1",
				"--structural-finding", "crash_window", "--structural-finding", "toctou",
			},
			want: map[string]any{
				"execution": "strict", "review": "per_task", "test_cadence": "red_green_per_task",
				"max_fix_rounds": float64(5), "risk_seam": nil, "breaker_scope": "unit",
				"effective_fix_round":    float64(1),
				"structural_findings":    []any{"crash_window", "toctou"},
				"hypothesis_invalidated": true, "redesign_required": true, "breaker": true,
				"architecture_audit_required": false, "architecture_audit_mode": "manual_report_only",
				"manual_required": false, "manual_level": "none", "visual_validation": "behavioral_seam",
			},
		},
		{
			name: "seam round and scoped manual",
			args: []string{
				"policy", "--profile", "standard", "--risk", "medium", "--change", "business-rule",
				"--manual-pdf", "scope", "--manual-in-scope", "--round", "1",
				"--risk-seam", "payments-ledger", "--seam-round", "3",
			},
			want: map[string]any{
				"execution": "slice", "review": "per_slice", "test_cadence": "slice_seam",
				"max_fix_rounds": float64(3), "risk_seam": "payments-ledger", "breaker_scope": "risk_seam",
				"effective_fix_round": float64(3), "structural_findings": []any{},
				"hypothesis_invalidated": false, "redesign_required": false, "breaker": true,
				"architecture_audit_required": false, "architecture_audit_mode": "manual_report_only",
				"manual_required": true, "manual_level": "scope", "visual_validation": "behavioral_seam",
			},
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			code, stdout, stderr := runCLI(t, test.args...)
			if code != 0 || stderr != "" {
				t.Fatalf("code=%d stderr=%q", code, stderr)
			}
			var got map[string]any
			if err := json.Unmarshal([]byte(stdout), &got); err != nil {
				t.Fatalf("invalid JSON: %v", err)
			}
			for key, want := range test.want {
				if !reflect.DeepEqual(got[key], want) {
					t.Errorf("%s=%#v want=%#v", key, got[key], want)
				}
			}
			for _, required := range []string{"test_strategy", "mutation_policy", "autonomy_policy", "plan_change_policy", "homologation_order"} {
				if _, ok := got[required]; !ok {
					t.Errorf("missing %s", required)
				}
			}
		})
	}
}

func TestPolicyRejectsInvalidSeamAndChoices(t *testing.T) {
	tests := []struct {
		name       string
		args       []string
		code       int
		stderrPart string
	}{
		{"seam requires name", []string{"policy", "--profile", "full", "--risk", "high", "--seam-round", "3"}, 2, "--risk-seam"},
		{"invalid profile", []string{"policy", "--profile", "tiny", "--risk", "low"}, 2, "invalid choice"},
		{"missing risk", []string{"policy", "--profile", "lean"}, 2, "--risk"},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			code, stdout, stderr := runCLI(t, test.args...)
			if code != test.code || stdout != "" || !strings.Contains(stderr, test.stderrPart) {
				t.Fatalf("code=%d stdout=%q stderr=%q", code, stdout, stderr)
			}
		})
	}
}
