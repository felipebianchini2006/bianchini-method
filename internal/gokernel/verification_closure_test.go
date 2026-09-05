package gokernel

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestMandatoryPlanGateCannotBeOmitted(t *testing.T) {
	for _, runSecond := range []bool{false, true} {
		t.Run(map[bool]string{false: "never executed", true: "failed"}[runSecond], func(t *testing.T) {
			plan := verificationPlan([]string{"go", "version"})
			plan["verifications"] = []any{"go version", "go command-that-does-not-exist"}
			repo, change := executionWorkspaceRepository(t, plan)
			pack, coherence, err := approvedPlanPackage(repo, change)
			if err != nil {
				t.Fatal(err)
			}
			spec, _ := legacyVerificationSpec("go version", "gate do plano")
			proof, err := executeVerification(verificationRequest{pack: pack, scope: "plan", plan: "P01", unit: "P01/gate-01", seam: "plan-gate", packageDigest: stateString(coherence["digest"])}, spec)
			if err != nil {
				t.Fatal(err)
			}
			if runSecond {
				if _, err := runVerify([]string{"plan", "--repo", repo, "--change", change, "--plan", "P01"}); err == nil {
					t.Fatal("expected second gate to fail")
				}
			}
			ids := []string{stateString(proof["proof_id"])}
			if _, err := validateProofSet(pack, ids, "plan", "P01", "", true); err == nil || !strings.Contains(err.Error(), "GATE_COVERAGE") {
				t.Fatalf("omitted gate accepted: %v", err)
			}
			if _, err := runVerify([]string{"review", "--repo", repo, "--change", change, "--scope", "plan", "--plan", "P01", "--reviewer", "reviewer", "--verdict", "approved", "--proof", ids[0]}); err == nil {
				t.Fatal("review waived missing gate")
			}
		})
	}
}

func TestProofForDifferentCommandCannotCoverGate(t *testing.T) {
	repo, change := executionWorkspaceRepository(t, verificationPlan([]string{"go", "version"}))
	pack, coherence, err := approvedPlanPackage(repo, change)
	if err != nil {
		t.Fatal(err)
	}
	spec, _ := legacyVerificationSpec("go env GOOS", "gate do plano")
	proof, err := executeVerification(verificationRequest{pack: pack, scope: "plan", plan: "P01", unit: "P01/gate-01", seam: "plan-gate", packageDigest: stateString(coherence["digest"])}, spec)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := validateProofSet(pack, []string{stateString(proof["proof_id"])}, "plan", "P01", "", true); err == nil {
		t.Fatal("wrong command accepted")
	}
}

func TestExternalVerificationDoesNotReusePass(t *testing.T) {
	if os.PathSeparator == '\\' {
		t.Skip("shell fixture is POSIX")
	}
	external := filepath.Join(t.TempDir(), "service-state")
	if err := os.WriteFile(external, []byte("up"), 0600); err != nil {
		t.Fatal(err)
	}
	repo, change := executionWorkspaceRepository(t, verificationPlan([]string{"go", "version"}))
	pack, coherence, err := approvedPlanPackage(repo, change)
	if err != nil {
		t.Fatal(err)
	}
	spec := verificationSpec{kind: "command", argv: []string{"sh", "-c", `test "$(cat "$1")" = up`, "external", external}, cwd: ".", timeout: 30, proves: "live service is up"}
	request := verificationRequest{pack: pack, scope: "plan", plan: "P01", unit: "P01/gate-01", seam: "service", packageDigest: stateString(coherence["digest"])}
	if _, err := executeVerification(request, spec); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(external, []byte("down"), 0600); err != nil {
		t.Fatal(err)
	}
	if _, err := executeVerification(request, spec); err == nil || !strings.Contains(err.Error(), "VERIFICATION_FAILED") {
		t.Fatalf("external stale pass reused: %v", err)
	}
}

func TestGroupedTaskCompletesWithoutIndividualReview(t *testing.T) {
	plan := verificationPlan([]string{"go", "version"})
	plan["execution"], plan["review"] = "grouped", "plan_gate"
	repo, change := executionWorkspaceRepository(t, plan)
	context := verificationContextPack(t, repo, change)
	proof, err := runVerify([]string{"task", "--repo", repo, "--change", change, "--plan", "P01", "--task", "T01", "--context-pack", context})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := taskComplete(repo, change, "P01", "T01", context, "verified delivery", nil, []string{stateString(proof.(map[string]any)["proof_id"])}, ""); err != nil {
		t.Fatal(err)
	}
}
