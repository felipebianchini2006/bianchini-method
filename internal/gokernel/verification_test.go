package gokernel

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func verificationPlan(argv []string) map[string]any {
	plan := roadmapPlan("P01", nil)
	task := stateObject(stateArray(plan["tasks"])[0])
	verify := stateObject(task["verify"])
	delete(verify, "run")
	verify["argv"] = stringSliceAny(argv)
	verify["cwd"] = "."
	verify["timeout_seconds"] = 30
	task["verify"] = verify
	plan["tasks"] = []any{task}
	plan["verifications"] = []any{"go version"}
	return plan
}

func verificationContextPack(t *testing.T, repo, change string) string {
	t.Helper()
	directory := filepath.Join(repo, ".bianchini", "changes", change)
	if err := os.WriteFile(filepath.Join(directory, "SCOPE.md"), []byte("# Escopo\n\n### REQ-001 — Contrato\n\nContrato verificável.\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	specPath := filepath.Join(directory, "specs", "expected", "system.md")
	if err := os.WriteFile(specPath, []byte("# Sistema\n\n## REQ-001\n\nO contrato deve ser observável.\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	manifestValue := map[string]any{
		"schema_version": 1, "spec_contract": 1,
		"specs": []any{map[string]any{
			"id": "system", "path": "system.md",
			"requirements": []any{map[string]any{"id": "REQ-001", "scope": []any{"REQ-001"}}},
		}},
		"risk_coverage": []any{},
	}
	manifestBytes, _ := json.MarshalIndent(manifestValue, "", "  ")
	if err := os.WriteFile(filepath.Join(directory, "specs", "MANIFEST.json"), append(manifestBytes, '\n'), 0o600); err != nil {
		t.Fatal(err)
	}
	if _, err := runRoadmap([]string{"sync", "--repo", repo, "--change", change}); err != nil {
		t.Fatal(err)
	}
	workspace, _, plans, err := loadRoadmapPackage(repo, change)
	if err != nil {
		t.Fatal(err)
	}
	current, err := loadProjectModel(workspace.currentMod)
	if err != nil {
		t.Fatal(err)
	}
	expected, err := loadProjectModel(filepath.Join(directory, "SYSTEM_MODEL.md"))
	if err != nil {
		t.Fatal(err)
	}
	manifest, err := coherenceArtifactManifest(workspace, directory)
	if err != nil {
		t.Fatal(err)
	}
	coherencePath := filepath.Join(directory, "COHERENCE.md")
	coherence, err := readStructuredFrontmatter(coherencePath)
	if err != nil {
		t.Fatal(err)
	}
	findings := stateArray(coherence["findings"])
	semantic := stateObject(coherence["semantic"])
	coherence["artifact_manifest"] = manifest
	coherence["review_input_digest"] = coherenceReviewDigest(2, manifest, nil)
	coherence["digest"] = coherencePackageDigest(current, expected, plans, findings, semantic, 2, manifest, nil)
	document, err := frontmatterDocument(coherence, "# Coerência\n\nStatus: approved.", false)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(coherencePath, document, 0o600); err != nil {
		t.Fatal(err)
	}
	state, err := workspace.readState()
	if err != nil {
		t.Fatal(err)
	}
	state["digest"] = coherence["digest"]
	if err := workspace.writeState(state, "# Estado atual"); err != nil {
		t.Fatal(err)
	}
	executionWorkspaceGit(t, repo, "add", ".bianchini")
	executionWorkspaceGit(t, repo, "commit", "-q", "-m", "prepare context scope")
	code, stdout, stderr := runCLI(t, "context", "pack", "--repo", repo, "--unit", strings.SplitN(change, "-", 2)[0]+"/P01/T01")
	if code != 0 {
		t.Fatalf("context pack: code=%d stderr=%q", code, stderr)
	}
	var value map[string]any
	if err := json.Unmarshal([]byte(stdout), &value); err != nil {
		t.Fatal(err)
	}
	return filepath.Join(repo, stateString(value["path"]))
}

func TestVerifyTaskExecutesStructuredCommandAndReusesPassingProof(t *testing.T) {
	repo, change := executionWorkspaceRepository(t, verificationPlan([]string{"go", "version"}))
	pack := verificationContextPack(t, repo, change)
	first, err := runVerify([]string{"task", "--repo", repo, "--change", change, "--plan", "P01", "--task", "T01", "--context-pack", pack})
	if err != nil {
		t.Fatal(err)
	}
	proofID := stateString(first.(map[string]any)["proof_id"])
	if !verificationProofID.MatchString(proofID) || first.(map[string]any)["reused"] != false {
		t.Fatalf("first=%#v", first)
	}
	second, err := runVerify([]string{"task", "--repo", repo, "--change", change, "--plan", "P01", "--task", "T01", "--context-pack", pack})
	if err != nil {
		t.Fatal(err)
	}
	if stateString(second.(map[string]any)["proof_id"]) != proofID || second.(map[string]any)["reused"] != true {
		t.Fatalf("second=%#v", second)
	}
	content, err := os.ReadFile(filepath.Join(repo, ".bianchini", "changes", change, "results", "proofs", proofID+".json"))
	if err != nil {
		t.Fatal(err)
	}
	proof, err := decodeStrictJSONObject(content)
	if err != nil || stateString(proof["status"]) != "passed" || stateInt(proof["exit_code"]) != 0 || stateString(proof["source_fingerprint"]) == "" {
		t.Fatalf("proof=%#v err=%v", proof, err)
	}
}

func TestVerifyTaskFailedProofCannotLoopWithoutReason(t *testing.T) {
	repo, change := executionWorkspaceRepository(t, verificationPlan([]string{os.Args[0], "-invalid-verification-flag"}))
	pack := verificationContextPack(t, repo, change)
	arguments := []string{"task", "--repo", repo, "--change", change, "--plan", "P01", "--task", "T01", "--context-pack", pack}
	if _, err := runVerify(arguments); err == nil || !strings.Contains(err.Error(), "VERIFICATION_FAILED") {
		t.Fatalf("first err=%v", err)
	}
	packValue, _, err := approvedPlanPackage(repo, change)
	if err != nil {
		t.Fatal(err)
	}
	proofs, err := loadVerificationProofs(packValue)
	if err != nil || len(proofs) != 1 {
		t.Fatalf("proofs=%d err=%v", len(proofs), err)
	}
	failedProof := ""
	for identifier := range proofs {
		failedProof = identifier
	}
	if _, err := runVerify([]string{"review", "--repo", repo, "--change", change, "--scope", "task", "--plan", "P01", "--task", "T01", "--reviewer", "independent", "--verdict", "changes_requested", "--proof", failedProof, "--finding", "comportamento aprovado falhou"}); err != nil {
		t.Fatal(err)
	}
	if _, err := runVerify(arguments); err == nil || !strings.Contains(err.Error(), "VERIFICATION_RETRY_REQUIRED") {
		t.Fatalf("second err=%v", err)
	}
	withReason := append(append([]string{}, arguments...), "--retry-reason", "flake de ambiente investigado")
	if _, err := runVerify(withReason); err == nil || !strings.Contains(err.Error(), "VERIFICATION_FAILED") {
		t.Fatalf("retry err=%v", err)
	}
	packValue, _, err = approvedPlanPackage(repo, change)
	if err != nil {
		t.Fatal(err)
	}
	proofs, err = loadVerificationProofs(packValue)
	if err != nil || len(proofs) != 2 {
		t.Fatalf("proofs=%d err=%v", len(proofs), err)
	}
}

func TestProcedureProofChangesWhenEvidenceChanges(t *testing.T) {
	plan := verificationPlan([]string{"go", "version"})
	task := stateObject(stateArray(plan["tasks"])[0])
	verify := stateObject(task["verify"])
	delete(verify, "argv")
	verify["kind"] = "procedure"
	verify["run"] = "operar a jornada pública e capturar o resultado"
	task["verify"] = verify
	plan["tasks"] = []any{task}
	repo, change := executionWorkspaceRepository(t, plan)
	pack := verificationContextPack(t, repo, change)
	evidence := filepath.Join(repo, ".bianchini", "changes", change, "results", "manual.txt")
	if err := os.WriteFile(evidence, []byte("primeira observação\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	arguments := []string{"task", "--repo", repo, "--change", change, "--plan", "P01", "--task", "T01", "--context-pack", pack, "--evidence", evidence}
	first, err := runVerify(arguments)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(evidence, []byte("observação corrigida\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	packValue, _, err := approvedPlanPackage(repo, change)
	if err != nil {
		t.Fatal(err)
	}
	firstProof := stateString(first.(map[string]any)["proof_id"])
	if _, err := validateProofSet(packValue, []string{firstProof}, "task", "P01", "T01", true); err == nil || !strings.Contains(err.Error(), "evidência atual") {
		t.Fatalf("proof antigo deveria ficar stale após alterar evidência: %v", err)
	}
	second, err := runVerify(arguments)
	if err != nil {
		t.Fatal(err)
	}
	if stateString(first.(map[string]any)["proof_id"]) == stateString(second.(map[string]any)["proof_id"]) || second.(map[string]any)["reused"] != false {
		t.Fatalf("evidência alterada foi reutilizada: first=%#v second=%#v", first, second)
	}
}

func TestManualProofCoverageRequiresExistingMatchingArtifact(t *testing.T) {
	repo := t.TempDir()
	evidence := filepath.Join(repo, "evidence.txt")
	content := []byte("jornada observada\n")
	if err := os.WriteFile(evidence, content, 0o600); err != nil {
		t.Fatal(err)
	}
	requirements := []any{map[string]any{"plan": "P01", "task": "T01"}}
	proofs := []any{map[string]any{
		"plan": "P01", "task": "T01", "evidence": "evidence.txt",
		"evidence_sha256": sha256Bytes(content),
	}}
	if !manualProofCoverage(repo, requirements, proofs) {
		t.Fatal("artefato real e íntegro deveria cobrir o procedimento")
	}
	stateObject(proofs[0])["evidence_sha256"] = strings.Repeat("a", 64)
	if manualProofCoverage(repo, requirements, proofs) {
		t.Fatal("hash forjado não pode cobrir o procedimento")
	}
	stateObject(proofs[0])["evidence_sha256"] = sha256Bytes(content)
	if err := os.WriteFile(evidence, []byte("alterado\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	if manualProofCoverage(repo, requirements, proofs) {
		t.Fatal("artefato alterado não pode cobrir o procedimento")
	}
}

func TestProofAndReviewBecomeStaleAfterCodeChanges(t *testing.T) {
	repo, change := executionWorkspaceRepository(t, verificationPlan([]string{"go", "version"}))
	packPath := verificationContextPack(t, repo, change)
	verified, err := runVerify([]string{"task", "--repo", repo, "--change", change, "--plan", "P01", "--task", "T01", "--context-pack", packPath})
	if err != nil {
		t.Fatal(err)
	}
	proofID := stateString(verified.(map[string]any)["proof_id"])
	reviewed, err := runVerify([]string{"review", "--repo", repo, "--change", change, "--scope", "task", "--plan", "P01", "--task", "T01", "--reviewer", "independent-reviewer", "--verdict", "approved", "--proof", proofID})
	if err != nil {
		t.Fatal(err)
	}
	reviewID := stateString(reviewed.(map[string]any)["review_id"])
	pack, _, err := approvedPlanPackage(repo, change)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := validateProofSet(pack, []string{proofID}, "task", "P01", "T01", true); err != nil {
		t.Fatal(err)
	}
	if err := validateVerificationReview(pack, reviewID, "task", "P01", "T01", []string{proofID}, true); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(repo, "implementation.txt"), []byte("changed\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	executionWorkspaceGit(t, repo, "add", "implementation.txt")
	executionWorkspaceGit(t, repo, "commit", "-q", "-m", "change implementation")
	if _, err := validateProofSet(pack, []string{proofID}, "task", "P01", "T01", true); err == nil || !strings.Contains(err.Error(), "estado atual") {
		t.Fatalf("proof stale err=%v", err)
	}
	if err := validateVerificationReview(pack, reviewID, "task", "P01", "T01", []string{proofID}, true); err == nil || !strings.Contains(err.Error(), "estado atual") {
		t.Fatalf("review stale err=%v", err)
	}
}

func TestTypedPlanCompletionRejectsNarrativeVerification(t *testing.T) {
	repo, change := executionWorkspaceRepository(t, verificationPlan([]string{"go", "version"}))
	contextPack := verificationContextPack(t, repo, change)
	_, err := taskComplete(repo, change, "P01", "T01", contextPack, "feito", []string{"parece funcionar"}, nil, "")
	if err == nil || !strings.Contains(err.Error(), "não aceita texto") {
		t.Fatalf("err=%v", err)
	}
}

func TestTypedLifecycleRequiresProofReviewReleaseAndHomologation(t *testing.T) {
	repo, change := executionWorkspaceRepository(t, verificationPlan([]string{"go", "version"}))
	contextPack := verificationContextPack(t, repo, change)
	taskProofValue, err := runVerify([]string{"task", "--repo", repo, "--change", change, "--plan", "P01", "--task", "T01", "--context-pack", contextPack})
	if err != nil {
		t.Fatal(err)
	}
	taskProof := stateString(taskProofValue.(map[string]any)["proof_id"])
	taskReviewValue, err := runVerify([]string{"review", "--repo", repo, "--change", change, "--scope", "task", "--plan", "P01", "--task", "T01", "--reviewer", "independent", "--verdict", "approved", "--proof", taskProof})
	if err != nil {
		t.Fatal(err)
	}
	taskReview := stateString(taskReviewValue.(map[string]any)["review_id"])
	if _, err := taskComplete(repo, change, "P01", "T01", contextPack, "resultado real", nil, []string{taskProof}, taskReview); err != nil {
		t.Fatal(err)
	}
	planProofValue, err := runVerify([]string{"plan", "--repo", repo, "--change", change, "--plan", "P01"})
	if err != nil {
		t.Fatal(err)
	}
	planProofs := planProofValue.(map[string]any)["proof_ids"].([]string)
	planReviewArgs := []string{"review", "--repo", repo, "--change", change, "--scope", "plan", "--plan", "P01", "--reviewer", "independent", "--verdict", "approved"}
	for _, proof := range planProofs {
		planReviewArgs = append(planReviewArgs, "--proof", proof)
	}
	planReviewValue, err := runVerify(planReviewArgs)
	if err != nil {
		t.Fatal(err)
	}
	deltaPath := filepath.Join(repo, ".bianchini", ".runtime", "actual-delta.json")
	if err := os.WriteFile(deltaPath, []byte("{}\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	if _, err := completePlan(repo, change, "P01", deltaPath, "plano realmente entregue", nil, planProofs, stateString(planReviewValue.(map[string]any)["review_id"]), []string{"T01"}); err != nil {
		t.Fatal(err)
	}
	executionWorkspaceGit(t, repo, "add", ".bianchini")
	executionWorkspaceGit(t, repo, "commit", "-q", "-m", "complete plan with proofs")
	if _, err := closeChange(repo, change); err == nil || !strings.Contains(err.Error(), "RELEASE_REQUIRED") {
		t.Fatalf("close without release err=%v", err)
	}
	releaseValue, err := runVerify([]string{"release", "--repo", repo, "--change", change, "--build", "test-build", "--checksum", strings.Repeat("a", 64), "--delivery", "not_applicable"})
	if err != nil {
		t.Fatal(err)
	}
	release := releaseValue.(map[string]any)
	releaseProofs := release["proof_ids"].([]string)
	reviewArgs := []string{"review", "--repo", repo, "--change", change, "--scope", "release", "--reviewer", "independent", "--verdict", "approved"}
	for _, proof := range releaseProofs {
		reviewArgs = append(reviewArgs, "--proof", proof)
	}
	if _, err := runVerify(reviewArgs); err != nil {
		t.Fatal(err)
	}
	executionWorkspaceGit(t, repo, "add", ".bianchini")
	executionWorkspaceGit(t, repo, "commit", "-q", "-m", "verify and review release")
	if _, err := closeChange(repo, change); err == nil || !strings.Contains(err.Error(), "HOMOLOGATION_REQUIRED") {
		t.Fatalf("close without homologation err=%v", err)
	}
	homologation := map[string]any{
		"schema_version": 1, "fingerprint": release["fingerprint"], "rc": release["candidate"],
		"change": change, "status": "accepted", "gates": []any{"real public journey"},
		"blockers": []any{}, "findings": []any{}, "required_refs": []any{"results/RELEASE.md"},
	}
	document, err := frontmatterDocument(homologation, "# Homologação\n\nJornada pública executada.", false)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(repo, ".bianchini", "changes", change, "results", "HOMOLOGATION.md"), document, 0o600); err != nil {
		t.Fatal(err)
	}
	executionWorkspaceGit(t, repo, "add", ".bianchini")
	executionWorkspaceGit(t, repo, "commit", "-q", "-m", "accept homologation")
	closed, err := closeChange(repo, change)
	if err != nil {
		t.Fatal(err)
	}
	if stateString(closed["status"]) != "completed" {
		t.Fatalf("closed=%#v", closed)
	}
}
