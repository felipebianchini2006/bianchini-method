package gokernel

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestStrictAndSliceRequireTheirTaskReview(t *testing.T) {
	for _, mode := range []string{"strict", "slice"} {
		t.Run(mode, func(t *testing.T) {
			plan := verificationPlan([]string{"go", "version"})
			plan["execution"] = mode
			if mode == "strict" {
				plan["review"] = "per_task"
			} else {
				plan["review"] = "per_slice"
			}
			repo, change := executionWorkspaceRepository(t, plan)
			context := verificationContextPack(t, repo, change)
			proof, err := runVerify([]string{"task", "--repo", repo, "--change", change, "--plan", "P01", "--task", "T01", "--context-pack", context})
			if err != nil {
				t.Fatal(err)
			}
			id := stateString(proof.(map[string]any)["proof_id"])
			if _, err := taskComplete(repo, change, "P01", "T01", context, "complete", nil, []string{id}, ""); err == nil || !strings.Contains(err.Error(), "REVIEW_REQUIRED") {
				t.Fatalf("missing review: %v", err)
			}
			review, err := runVerify([]string{"review", "--repo", repo, "--change", change, "--scope", "task", "--plan", "P01", "--task", "T01", "--reviewer", "fixture:review", "--verdict", "approved", "--proof", id})
			if err != nil {
				t.Fatal(err)
			}
			if _, err := taskComplete(repo, change, "P01", "T01", context, "complete", nil, []string{id}, stateString(review.(map[string]any)["review_id"])); err != nil {
				t.Fatal(err)
			}
		})
	}
}

func TestConcreteInspectionFindingDoesNotNeedArtificialRed(t *testing.T) {
	repo, change := executionWorkspaceRepository(t, verificationPlan([]string{"go", "version"}))
	if err := os.WriteFile(filepath.Join(repo, "inspection.txt"), []byte("handler authorizes any owner; violates REQ-001"), 0600); err != nil {
		t.Fatal(err)
	}
	args := []string{"review", "--repo", repo, "--change", change, "--scope", "plan", "--plan", "P01", "--reviewer", "fixture:review", "--verdict", "changes_requested"}
	if _, err := runVerify(append(args, "--finding", "looks bad")); err == nil {
		t.Fatal("vague finding accepted")
	}
	finding := `{"target":"handler", "observed":"any owner can read", "requirement":"REQ-001", "severity":"high", "evidence":"inspection.txt", "expected_fix":"restrict ownership"}`
	if _, err := runVerify(append(args, "--finding", finding)); err != nil {
		t.Fatal(err)
	}
}

func TestFixLimitSurvivesRenamingUnitAndChangingCode(t *testing.T) {
	repo, change := executionWorkspaceRepository(t, verificationPlan([]string{"go", "version"}))
	pack, c, err := approvedPlanPackage(repo, change)
	if err != nil {
		t.Fatal(err)
	}
	spec, _ := legacyVerificationSpec("go command-that-does-not-exist", "failure")
	request := verificationRequest{pack: pack, scope: "plan", plan: "P01", unit: "first-name", seam: "stable-problem", packageDigest: stateString(c["digest"])}
	for round := 0; round <= 3; round++ {
		if err := os.WriteFile(filepath.Join(repo, "code.txt"), []byte(strings.Repeat("x", round+1)), 0600); err != nil {
			t.Fatal(err)
		}
		request.unit = strings.Repeat("renamed", round+1)
		if _, err := executeVerification(request, spec); err == nil || !strings.Contains(err.Error(), "VERIFICATION_FAILED") {
			t.Fatalf("round %d: %v", round, err)
		}
	}
	if err := os.WriteFile(filepath.Join(repo, "code.txt"), []byte("another patch"), 0600); err != nil {
		t.Fatal(err)
	}
	request.unit = "renamed-again"
	if _, err := executeVerification(request, spec); err == nil || !strings.Contains(err.Error(), "FIX_LIMIT_REACHED") {
		t.Fatalf("limit reset: %v", err)
	}
}

func TestTechnicalDecisionDoesNotClaimHumanApproval(t *testing.T) {
	repo, change := executionWorkspaceRepository(t, verificationPlan([]string{"go", "version"}))
	pack, c, err := approvedPlanPackage(repo, change)
	if err != nil {
		t.Fatal(err)
	}
	// Prepare the reviewed fixture at the decision boundary, then exercise the CLI.
	c["status"] = "ready_for_approval"
	document, _ := frontmatterDocument(c, "# Reviewed fixture", false)
	if err := os.WriteFile(filepath.Join(pack.directory, "COHERENCE.md"), document, 0600); err != nil {
		t.Fatal(err)
	}
	result, err := runCoherence([]string{"approve", "--repo", repo, "--change", change, "--digest", stateString(c["digest"]), "--decided-by", "agent:test"})
	if err != nil {
		t.Fatal(err)
	}
	if result.(map[string]any)["approved_by"] != nil {
		t.Fatal("invented human approval")
	}
	payload, err := readStructuredFrontmatter(filepath.Join(pack.directory, "COHERENCE.md"))
	if err != nil {
		t.Fatal(err)
	}
	approval := stateObject(payload["approval"])
	if approval["approved_by"] != nil || stateString(approval["kind"]) != "technical_decision" {
		t.Fatalf("approval: %#v", approval)
	}
}
