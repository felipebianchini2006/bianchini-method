package gokernel

import (
	"os"
	"path/filepath"
	"strings"
)

func debugProofPackage(workspace methodWorkspace, value map[string]any) coherencePackage {
	id := stateString(value["id"])
	digest := waveStableDigest(map[string]any{"id": id, "expected": value["expected"], "actual": value["actual"]})
	return workflowProofPackage(workspace, filepath.Join(workspace.dir, "debug", "evidence", id), digest)
}

func executeDebugProof(workspace methodWorkspace, value map[string]any, event string, flags parsedFlags) (string, error) {
	raw := lastValue(flags, "--command")
	if raw == "" {
		return "", workflowError("STALE_EVIDENCE", event+" exige --command executável")
	}
	spec, err := legacyVerificationSpec(raw, stateString(value["expected"]))
	if err != nil {
		return "", err
	}
	pack := debugProofPackage(workspace, value)
	if event == "red" {
		pattern := lastValue(flags, "--failure-pattern")
		if strings.TrimSpace(pattern) == "" {
			return "", workflowError("STALE_EVIDENCE", "RED exige --failure-pattern observado no defeito")
		}
		testPath, err := confinedPath(workspace.root, lastValue(flags, "--test-file"), "debug.test_file", true)
		if err != nil || !regularFile(testPath) {
			return "", workflowError("STALE_EVIDENCE", "RED exige --test-file com regressão real")
		}
		content, err := os.ReadFile(testPath)
		if err != nil {
			return "", err
		}
		relative, _ := filepath.Rel(workspace.root, testPath)
		value["regression_contract"] = map[string]any{"argv": stringSliceAny(spec.argv), "test_file": filepath.ToSlash(relative), "test_sha256": sha256Bytes(content), "failure_pattern": pattern}
	} else if event == "green" {
		contract := stateObject(value["regression_contract"])
		argv := stringsFromAny(contract["argv"])
		if strings.Join(argv, "\x00") != strings.Join(spec.argv, "\x00") {
			return "", workflowError("STALE_EVIDENCE", "GREEN deve executar a mesma regressão do RED")
		}
		testPath, err := confinedPath(workspace.root, stateString(contract["test_file"]), "debug.test_file", true)
		if err != nil {
			return "", err
		}
		content, err := os.ReadFile(testPath)
		if err != nil || sha256Bytes(content) != stateString(contract["test_sha256"]) {
			return "", workflowError("STALE_EVIDENCE", "teste mudou após RED; reproduza novamente sem enfraquecer aceite")
		}
	}
	result, runErr := executeVerification(verificationRequest{pack: pack, scope: "debug", unit: stateString(value["id"]) + "/" + event, seam: "debug-regression", packageDigest: stateString(pack.contract["digest"]), retryReason: lastValue(flags, "--retry-reason")}, spec)
	if result == nil {
		return "", runErr
	}
	proof := stateObject(result["proof"])
	if event == "red" {
		pattern := stateString(stateObject(value["regression_contract"])["failure_pattern"])
		output := stateString(proof["stdout_summary"]) + "\n" + stateString(proof["stderr_summary"])
		if stateString(proof["status"]) != "failed" || stateInt(proof["exit_code"]) != 1 || proof["timed_out"] == true || proof["spawn_error"] == true || debugInfrastructureFailure(output) || !strings.Contains(output, pattern) {
			return "", workflowError("RED_NOT_REPRODUCED", "RED exige exit 1 e assinatura do defeito; falha de infraestrutura não é reprodução")
		}
	} else if runErr != nil {
		return "", runErr
	}
	return stateString(result["proof_id"]), nil
}

func validateDebugProofs(workspace methodWorkspace, value map[string]any) error {
	pack := debugProofPackage(workspace, value)
	proofs, err := loadVerificationProofs(pack)
	if err != nil {
		return err
	}
	current, err := verificationSourceFingerprint(workspace.root)
	if err != nil {
		return err
	}
	byEvent := map[string]map[string]any{}
	for _, raw := range stateArray(value["events"]) {
		event := stateObject(raw)
		byEvent[stateString(event["event"])] = event
	}
	for _, event := range []string{"red", "green", "regression_checked"} {
		proof := proofs[stateString(byEvent[event]["proof_id"])]
		if proof == nil || stateString(proof["scope"]) != "debug" || stateString(proof["change"]) != stateString(value["id"]) || stateString(proof["package_digest"]) != stateString(pack.contract["digest"]) || stateString(proof["unit"]) != stateString(value["id"])+"/"+event {
			return workflowError("STALE_EVIDENCE", "debug exige provas próprias RED/GREEN/regressão")
		}
		if err := rejectLaterFailedProof(proofs, proof); err != nil {
			return err
		}
		if event != "red" && (stateString(proof["status"]) != "passed" || stateString(proof["source_fingerprint"]) != current || !verificationProofEnvironmentCurrent(workspace.root, proof)) {
			return workflowError("STALE_EVIDENCE", "prova GREEN/regressão obsoleta")
		}
	}
	return nil
}

// Common runner/load failures do not demonstrate the investigated behavior.
func debugInfrastructureFailure(output string) bool {
	lower := strings.ToLower(output)
	for _, marker := range []string{"modulenotfounderror:", "importerror:", "syntaxerror:", "cannot find module", "cannot find package", "command not found", "no such file or directory", "[build failed]", "failed to load", "failed to import test module", "error: could not", "no tests ran"} {
		if strings.Contains(lower, marker) {
			return true
		}
	}
	return false
}
