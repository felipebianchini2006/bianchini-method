package gokernel

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestReviewQuickRejectsLatestFailedRun(t *testing.T) {
	repo := workflowTestRepo(t, true)
	cmd := `python3 -c "from pathlib import Path; import sys; sys.exit(0 if Path('.bianchini/.runtime/external').read_text()=='up' else 1)"`
	started, err := runDirectLifecycle("start", []string{"--repo", repo, "--objective", "Revisar texto interno", "--scope", "texto interno", "--acceptance", "estado externo disponível", "--verification", cmd})
	if err != nil {
		t.Fatal(err)
	}
	id := stateString(started.(map[string]any)["id"])
	path := filepath.Join(repo, ".bianchini", ".runtime", "external")
	os.WriteFile(path, []byte("up"), 0600)
	args := []string{"--repo", repo, "--slug", id, "--checkpoint", "verificado", "--next-action", "fechar", "--command", cmd}
	if _, err = runDirectLifecycle("checkpoint", args); err != nil {
		t.Fatal(err)
	}
	os.WriteFile(path, []byte("down"), 0600)
	if _, err = runDirectLifecycle("checkpoint", args); err == nil {
		t.Fatal("expected actual command failure")
	}
	result, err := runDirectLifecycle("finish", []string{"--repo", repo, "--slug", id, "--status", "completed", "--next-action", "idle", "--verification", "checkpoint", "--docviva-kind", "internal", "--docviva-outcome", "not_applicable", "--docviva-justification", "somente texto interno"})
	if err == nil {
		t.Fatalf("BYPASS: newer failed proof did not prevent completion: %#v", result)
	}
}
func TestReviewGroupedRejectsOpenTaskFinding(t *testing.T) {
	plan := verificationPlan([]string{"go", "version"})
	plan["execution"] = "grouped"
	plan["review"] = "plan_gate"
	repo, change := executionWorkspaceRepository(t, plan)
	context := verificationContextPack(t, repo, change)
	verified, err := runVerify([]string{"task", "--repo", repo, "--change", change, "--plan", "P01", "--task", "T01", "--context-pack", context})
	if err != nil {
		t.Fatal(err)
	}
	evidence := filepath.Join(repo, ".bianchini", ".runtime", "finding.txt")
	os.WriteFile(evidence, []byte("Concrete inspection finding"), 0600)
	finding, _ := json.Marshal(map[string]any{"target": "contract", "observed": "contrato violado", "requirement": "REQ-001", "severity": "critical", "evidence": evidence, "expected_fix": "restaurar contrato"})
	_, err = runVerify([]string{"review", "--repo", repo, "--change", change, "--scope", "task", "--plan", "P01", "--task", "T01", "--reviewer", "independent", "--verdict", "changes_requested", "--finding", string(finding)})
	if err != nil {
		t.Fatal(err)
	}
	result, err := taskComplete(repo, change, "P01", "T01", context, "done", nil, []string{stateString(verified.(map[string]any)["proof_id"])}, "")
	if err == nil {
		t.Fatalf("BYPASS: unresolved critical task review accepted by grouped: %#v", result)
	}
}
func TestReviewSanitizeJSONSecret(t *testing.T) {
	got := sanitizeVerificationOutput([]byte(`{"api_key":"LOCAL_SECRET_SENTINEL","nested":{"password":"LOCAL_PASS_SENTINEL"}}`))
	if strings.Contains(got, "LOCAL_SECRET_SENTINEL") || strings.Contains(got, "LOCAL_PASS_SENTINEL") {
		t.Fatalf("LEAK: %s", got)
	}
}

func TestReviewFixLimitCannotBeBypassedByPassingOtherGate(t *testing.T) {
	repo := workflowTestRepo(t, true)
	ws := newMethodWorkspace(repo)
	pack := workflowProofPackage(ws, filepath.Join(ws.dir, "quick", "Q001-limit"), strings.Repeat("a", 64))
	request := verificationRequest{pack: pack, scope: "quick", unit: "Q001-limit/gate-01", seam: "shared-risk", packageDigest: strings.Repeat("a", 64)}
	failing, _ := legacyVerificationSpec(`python3 -c "raise SystemExit(1)"`, "failure")
	for i := 0; i <= 3; i++ {
		os.WriteFile(filepath.Join(repo, "version.txt"), []byte(strings.Repeat("x", i+1)), 0600)
		result, err := executeVerification(request, failing)
		if err == nil || !strings.Contains(err.Error(), "VERIFICATION_FAILED") {
			t.Fatalf("round %d: %v", i, err)
		}
		if stateInt(stateObject(result["proof"])["fix_round"]) != i {
			t.Fatalf("round %d proof: %#v", i, result)
		}
	}
	passing, _ := legacyVerificationSpec("go version", "control")
	request.unit = "Q001-limit/gate-02"
	if _, err := executeVerification(request, passing); err != nil {
		t.Fatal(err)
	}
	os.WriteFile(filepath.Join(repo, "version.txt"), []byte("fifth patch"), 0600)
	request.unit = "Q001-limit/gate-01"
	result, err := executeVerification(request, failing)
	if err == nil || !strings.Contains(err.Error(), "FIX_LIMIT_REACHED") {
		t.Fatalf("BYPASS: independent passing gate allowed correction beyond max: fix_round=%v err=%v", stateObject(result["proof"])["fix_round"], err)
	}
}
func TestReviewRedRejectsMissingPythonDependency(t *testing.T) {
	repo := workflowTestRepo(t, true)
	testPath := filepath.Join(repo, "regression.py")
	os.WriteFile(testPath, []byte("import definitely_missing_service_dependency\n"), 0600)
	started, err := runDebug([]string{"start", "--repo", repo, "--objective", "Corrigir autorização", "--expected", "acesso negado", "--actual", "acesso permitido", "--environment", "local"})
	if err != nil {
		t.Fatal(err)
	}
	id := stateString(started.(map[string]any)["id"])
	for _, stage := range []string{"reproduced", "diagnosed"} {
		args := []string{"checkpoint", "--repo", repo, "--id", id, "--event", stage, "--evidence", "observação"}
		if stage == "diagnosed" {
			args = append(args, "--root-cause", "permissão ausente")
		}
		if _, err := runDebug(args); err != nil {
			t.Fatal(err)
		}
	}
	result, err := runDebug([]string{"checkpoint", "--repo", repo, "--id", id, "--event", "red", "--evidence", "regressão", "--command", "python3 -B regression.py", "--test-file", testPath, "--failure-pattern", "ModuleNotFoundError"})
	if err == nil {
		t.Fatalf("BYPASS: missing test dependency accepted as RED: %#v", result)
	}
}
