package gokernel

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestCoherenceRejectsJourneyCoverageBeforeApproval(t *testing.T) {
	plan := roadmapPlan("P01", nil)
	stateObject(stateArray(plan["scenarios"])[0])["journey"] = "JRN-missing"
	repo, change := executionWorkspaceRepository(t, plan)
	result, err := coherenceCheck(repo, change, true, "")
	if err != nil {
		t.Fatal(err)
	}
	if result["status"] != "changes_required" {
		t.Fatalf("invalid journey passed check: %v", result)
	}
	// Simulate a review from an older CLI that did not run the global check.
	path := filepath.Join(repo, ".bianchini", "changes", change, "COHERENCE.md")
	value, err := readStructuredFrontmatter(path)
	if err != nil {
		t.Fatal(err)
	}
	value["status"] = "ready_for_approval"
	doc, _ := frontmatterDocument(value, "# Review from older CLI", false)
	if err := os.WriteFile(path, doc, 0600); err != nil {
		t.Fatal(err)
	}
	if _, err := coherenceApprove(repo, change, stateString(result["digest"]), "test"); err == nil || !strings.Contains(err.Error(), "SCENARIO_COVERAGE") {
		t.Fatalf("invalid journey approved: %v", err)
	}
}

func TestPlanSchemaTransitionPreservesCurrentDocuments(t *testing.T) {
	for _, schema := range []int{2, 3} {
		plan := roadmapPlan("P01", nil)
		plan["schema_version"] = schema
		if _, err := parsePlanContract(plan); err != nil {
			t.Fatal(err)
		}
	}
	plan := roadmapPlan("P01", nil)
	delete(plan, "scenarios")
	if _, err := parsePlanContract(plan); err == nil || !strings.Contains(err.Error(), "WORKSPACE_UPGRADE_REQUIRED") {
		t.Fatalf("legacy contract not diagnosed: %v", err)
	}
}
