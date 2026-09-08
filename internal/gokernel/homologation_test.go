package gokernel

import (
	"bytes"
	"github.com/felipebianchini2006/bianchini-method/internal/acceptance"
	"image"
	"image/png"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func passingScenarioResults(t *testing.T, root string, release map[string]any) []any {
	t.Helper()
	directory := filepath.Join(filepath.Dir(stateString(release["homologation"])), "evidence")
	if err := os.MkdirAll(directory, 0700); err != nil {
		t.Fatal(err)
	}
	var results []any
	for _, raw := range stateArray(release["scenario_requirements"]) {
		scenario := stateObject(raw)
		name := stateString(scenario["plan"]) + "-" + stateString(scenario["id"]) + ".txt"
		path := filepath.Join(directory, name)
		content := []byte("Observed expected CLI result on candidate; executable returned successfully.\n")
		if err := os.WriteFile(path, content, 0600); err != nil {
			t.Fatal(err)
		}
		relative, _ := filepath.Rel(root, path)
		evidence := []any{}
		for _, kind := range stateArray(scenario["evidence_kinds"]) {
			evidence = append(evidence, map[string]any{"kind": kind, "path": filepath.ToSlash(relative), "sha256": sha256Bytes(content)})
		}
		results = append(results, map[string]any{"plan": scenario["plan"], "id": scenario["id"], "result": "passed", "fingerprint": release["fingerprint"], "observed": "CLI expected result verified", "evidence": evidence})
	}
	return results
}

func TestHomologationEvidenceCannotBeOmittedOrForged(t *testing.T) {
	root := t.TempDir()
	candidate := map[string]any{"id": "RC-001"}
	plan := planContract{id: "P01", value: map[string]any{"requirements": []any{"REQ-001"}, "scenarios": []any{map[string]any{"id": "SC-001", "requirements": []any{"REQ-001"}, "risk": "contract regression", "platform": "cli", "profile": "operator", "state": "success", "expected": "result", "evidence_kinds": []any{"observation", "log"}}}}}
	pack := coherencePackage{workspace: methodWorkspace{root: root}, directory: filepath.Join(root, ".bianchini", "changes", "C001-test"), plans: []planContract{plan}, expected: projectModel{sections: map[string]map[string]map[string]any{}}}
	required, err := requiredAcceptanceScenarios(pack)
	if err != nil {
		t.Fatal(err)
	}
	release := map[string]any{"candidate": candidate, "fingerprint": strings.Repeat("a", 64), "scenario_requirements": scenarioValues(required), "homologation": homologationDocumentPath(pack, candidate)}
	good := map[string]any{"scenarios": passingScenarioResults(t, root, release)}
	if err := validateHomologationScenarios(pack, release, good); err != nil {
		t.Fatal(err)
	}
	for _, test := range []struct {
		name   string
		mutate func(map[string]any)
	}{
		{"missing scenarios", func(h map[string]any) { delete(h, "scenarios") }},
		{"unexecuted", func(h map[string]any) { stateObject(stateArray(h["scenarios"])[0])["result"] = "not_run" }},
		{"old candidate", func(h map[string]any) {
			stateObject(stateArray(h["scenarios"])[0])["fingerprint"] = strings.Repeat("b", 64)
		}},
		{"forged digest", func(h map[string]any) {
			row := stateObject(stateArray(h["scenarios"])[0])
			stateObject(stateArray(row["evidence"])[0])["sha256"] = strings.Repeat("b", 64)
		}},
		{"escape", func(h map[string]any) {
			row := stateObject(stateArray(h["scenarios"])[0])
			stateObject(stateArray(row["evidence"])[0])["path"] = "../outside.txt"
		}},
		{"missing kind", func(h map[string]any) {
			row := stateObject(stateArray(h["scenarios"])[0])
			row["evidence"] = stateArray(row["evidence"])[:1]
		}},
	} {
		t.Run(test.name, func(t *testing.T) {
			h := cloneMap(good)
			test.mutate(h)
			if err := validateHomologationScenarios(pack, release, h); err == nil {
				t.Fatal("invalid evidence accepted")
			}
		})
	}
	release["scenario_requirements"] = []any{}
	if err := validateHomologationScenarios(pack, release, good); err == nil {
		t.Fatal("release removed required scenario")
	}
}

func TestHomologationRequiresJourneyProfilesPlatformsAndStates(t *testing.T) {
	plan := planContract{id: "P01", value: map[string]any{"requirements": []any{"REQ-001"}, "scenarios": []any{map[string]any{"id": "SC-001", "requirements": []any{"REQ-001"}, "journey": "JRN-001", "risk": "contract regression", "platform": "cli", "profile": "operator", "state": "success", "expected": "result", "evidence_kinds": []any{"observation"}}}}}
	for _, dimension := range []string{"profiles", "platforms", "states"} {
		t.Run(dimension, func(t *testing.T) {
			pack := coherencePackage{plans: []planContract{plan}, expected: projectModel{sections: map[string]map[string]map[string]any{"journeys": {"JRN-001": {dimension: []any{"missing"}}}}}}
			if _, err := requiredAcceptanceScenarios(pack); err == nil {
				t.Fatal("missing journey dimension accepted")
			}
		})
	}
}

func TestHomologationKnownDefectsMustBeResolved(t *testing.T) {
	for _, severity := range []string{"critical", "high", "medium", "low"} {
		for _, status := range []string{"open", "accepted"} {
			h := map[string]any{"findings": []any{map[string]any{"severity": severity, "status": status}}, "gates": []any{map[string]any{"proof_id": "proof", "result": "passed"}}}
			if err := validateHomologationGates(t.TempDir(), t.TempDir(), h, []string{"proof"}); err == nil {
				t.Fatalf("%s %s accepted", severity, status)
			}
		}
	}
}

func TestReleaseRejectsUncommittedProduct(t *testing.T) {
	root := t.TempDir()
	executionWorkspaceGit(t, root, "init", "-q")
	executionWorkspaceGit(t, root, "config", "user.email", "test@example.invalid")
	executionWorkspaceGit(t, root, "config", "user.name", "Test")
	path := filepath.Join(root, "app.txt")
	if err := os.WriteFile(path, []byte("base"), 0600); err != nil {
		t.Fatal(err)
	}
	executionWorkspaceGit(t, root, "add", ".")
	executionWorkspaceGit(t, root, "commit", "-q", "-m", "base")
	if err := verificationProductClean(root); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, []byte("modified"), 0600); err != nil {
		t.Fatal(err)
	}
	if err := verificationProductClean(root); err == nil {
		t.Fatal("uncommitted product accepted")
	}
	executionWorkspaceGit(t, root, "add", "app.txt")
	if err := verificationProductClean(root); err == nil {
		t.Fatal("staged product accepted")
	}
	executionWorkspaceGit(t, root, "commit", "-q", "-m", "change")
	if err := os.WriteFile(filepath.Join(root, "new.txt"), []byte("untracked"), 0600); err != nil {
		t.Fatal(err)
	}
	if err := verificationProductClean(root); err == nil {
		t.Fatal("untracked product accepted")
	}
	if err := os.Remove(filepath.Join(root, "new.txt")); err != nil {
		t.Fatal(err)
	}
	if err := os.Mkdir(filepath.Join(root, ".bianchini"), 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(root, ".bianchini", "STATE.md"), []byte("state"), 0600); err != nil {
		t.Fatal(err)
	}
	if err := verificationProductClean(root); err != nil {
		t.Fatalf("method record prevented RC: %v", err)
	}
}

func TestHomologationRejectsStringBlockingFlag(t *testing.T) {
	root := t.TempDir()
	h := map[string]any{"findings": []any{map[string]any{"severity": "info", "status": "accepted", "blocking": "true"}}, "gates": []any{map[string]any{"proof_id": "p1", "result": "passed"}}}
	if err := validateHomologationGates(root, root, h, []string{"p1"}); err == nil {
		t.Fatal("ambiguous blocking flag accepted")
	}
}

func TestHomologationResolutionMustBelongToCandidateEvidence(t *testing.T) {
	root := t.TempDir()
	content := []byte("unrelated repository document")
	if err := os.WriteFile(filepath.Join(root, "README.md"), content, 0600); err != nil {
		t.Fatal(err)
	}
	evidenceRoot := filepath.Join(root, ".bianchini", "changes", "C001", "homologation", "RC-001", "evidence")
	h := map[string]any{"findings": []any{map[string]any{"severity": "low", "status": "resolved", "resolution_evidence": "README.md", "resolution_sha256": sha256Bytes(content)}}, "gates": []any{map[string]any{"proof_id": "p1", "result": "passed"}}}
	if err := validateHomologationGates(root, evidenceRoot, h, []string{"p1"}); err == nil {
		t.Fatal("unrelated resolution accepted")
	}
	if manualProofCoverage(root, evidenceRoot, []any{map[string]any{"plan": "P01", "task": "T01"}}, []any{map[string]any{"plan": "P01", "task": "T01", "evidence": "README.md", "evidence_sha256": sha256Bytes(content)}}) {
		t.Fatal("unrelated procedure proof accepted")
	}
}

func TestHomologationScreenshotRequiresDecodableImage(t *testing.T) {
	root := t.TempDir()
	directory := filepath.Join(root, "evidence")
	if err := os.Mkdir(directory, 0700); err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(directory, "screen.png")
	invalid := []byte("a screenshot was taken")
	if err := os.WriteFile(path, invalid, 0600); err != nil {
		t.Fatal(err)
	}
	evidence := acceptance.Evidence{Kind: "screenshot", Path: "evidence/screen.png", SHA256: sha256Bytes(invalid)}
	if err := inspectHomologationEvidence(root, directory, evidence); err == nil {
		t.Fatal("text masquerading as screenshot accepted")
	}
	var buffer bytes.Buffer
	if err := png.Encode(&buffer, image.NewRGBA(image.Rect(0, 0, 2, 2))); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, buffer.Bytes(), 0600); err != nil {
		t.Fatal(err)
	}
	evidence.SHA256 = sha256Bytes(buffer.Bytes())
	if err := inspectHomologationEvidence(root, directory, evidence); err != nil {
		t.Fatal(err)
	}
}
