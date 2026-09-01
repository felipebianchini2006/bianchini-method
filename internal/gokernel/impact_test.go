package gokernel

import (
	"path/filepath"
	"strings"
	"testing"
)

func TestImpactFrozenMissingWorkspaceError(t *testing.T) {
	repo := t.TempDir()
	code, stdout, stderr := runCLI(t, "impact", "analyze", "--repo", repo, "--change", "fixture", "--plan", "P01")
	expected := "erro de entrada/IO: STATE.md ausente: " + filepath.Join(repo, ".bianchini", "STATE.md") + "\n"
	if code != 2 || stdout != "" || stderr != expected {
		t.Fatalf("code=%d stdout=%q stderr=%q", code, stdout, stderr)
	}
}

func TestProjectImpactRadiusAndEvidence(t *testing.T) {
	plans := []planContract{
		impactPlan(t, "P01", nil, []string{"shared"}, nil),
		impactPlan(t, "P02", []string{"P01"}, []string{"middle"}, []string{"shared"}),
		impactPlan(t, "P03", []string{"P02"}, []string{"final"}, []string{"middle"}),
	}
	model, err := projectModelFromMapping(map[string]any{"schema_version": 1})
	if err != nil {
		t.Fatal(err)
	}
	tests := []struct {
		name       string
		values     map[string][]string
		booleans   map[string]bool
		radius     string
		direct     string
		transitive string
	}{
		{name: "contract is transitive", values: map[string][]string{"--changed-contract": {"shared"}}, booleans: map[string]bool{}, radius: "transitive", direct: "P02", transitive: "P03"},
		{name: "unknown contract is local", values: map[string][]string{"--changed-contract": {"isolated"}}, booleans: map[string]bool{}, radius: "local"},
		{name: "global follows graph", values: map[string][]string{}, booleans: map[string]bool{"--global-change": true}, radius: "global", direct: "P02", transitive: "P03"},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			result, err := projectImpact(plans, model, "P01", parsedFlags{values: test.values, booleans: test.booleans})
			if err != nil {
				t.Fatal(err)
			}
			if result["radius"] != test.radius || strings.Join(stateStringSlice(result["direct_plans"]), ",") != test.direct || strings.Join(stateStringSlice(result["transitive_plans"]), ",") != test.transitive {
				t.Fatalf("result=%#v", result)
			}
			if len(stateStringSlice(result["verifications"])) == 0 {
				t.Fatalf("verification missing: %#v", result)
			}
		})
	}
}

func impactPlan(t *testing.T, identifier string, dependsOn, provides, consumes []string) planContract {
	t.Helper()
	value := roadmapPlan(identifier, dependsOn)
	value["provides"] = stringSliceAny(provides)
	value["consumes"] = stringSliceAny(consumes)
	plan, err := parsePlanContract(value)
	if err != nil {
		t.Fatal(err)
	}
	return plan
}
