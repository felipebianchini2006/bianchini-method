package gokernel

import (
	"fmt"
	"path/filepath"
	"strings"
)

func workflowProofPackage(workspace methodWorkspace, directory, digest string) coherencePackage {
	return coherencePackage{workspace: workspace, directory: directory, contract: map[string]any{"digest": digest}}
}

func quickVerificationGates(brief map[string]any) ([]requiredVerification, error) {
	var gates []requiredVerification
	for i, raw := range stringsFromAny(brief["verification"]) {
		spec, err := legacyVerificationSpec(raw, "aceite do quick")
		if err != nil {
			return nil, err
		}
		gates = append(gates, requiredVerification{"", "", fmt.Sprintf("%s/gate-%02d", stateString(brief["id"]), i+1), spec})
	}
	return gates, nil
}

func verifyQuickCommands(workspace methodWorkspace, directory string, brief map[string]any, commands []string, retry string) ([]string, error) {
	gates, err := quickVerificationGates(brief)
	if err != nil {
		return nil, err
	}
	pack := workflowProofPackage(workspace, directory, stateString(brief["digest"]))
	var ids []string
	for _, raw := range commands {
		spec, err := legacyVerificationSpec(raw, "aceite do quick")
		if err != nil {
			return nil, err
		}
		matched := false
		for _, gate := range gates {
			if strings.Join(spec.argv, "\x00") != strings.Join(gate.spec.argv, "\x00") {
				continue
			}
			proof, err := executeVerification(verificationRequest{pack: pack, scope: "quick", unit: gate.unit, seam: "quick-acceptance", packageDigest: stateString(brief["digest"]), retryReason: retry}, spec)
			if err != nil {
				return nil, err
			}
			ids = append(ids, stateString(proof["proof_id"]))
			matched = true
		}
		if !matched {
			return nil, workflowError("GATE_COVERAGE", "comando não pertence ao aceite do quick")
		}
	}
	return ids, nil
}

func validateQuickProofs(workspace methodWorkspace, directory string, brief map[string]any, events []any) ([]string, error) {
	gates, err := quickVerificationGates(brief)
	if err != nil {
		return nil, err
	}
	pack := workflowProofPackage(workspace, directory, stateString(brief["digest"]))
	proofs, err := loadVerificationProofs(pack)
	if err != nil {
		return nil, err
	}
	current, err := verificationSourceFingerprint(workspace.root)
	if err != nil {
		return nil, err
	}
	selected := map[string]string{}
	for _, raw := range events {
		for _, id := range stringsFromAny(stateObject(raw)["proof_ids"]) {
			proof := proofs[id]
			if proof == nil {
				return nil, workflowError("STALE_EVIDENCE", "prova não pertence ao quick")
			}
			selected[stateString(proof["unit"])] = id
		}
	}
	var ids []string
	for _, gate := range gates {
		id := selected[gate.unit]
		proof := proofs[id]
		if proof == nil || !proofMatchesGate(proof, gate) || stateString(proof["scope"]) != "quick" || stateString(proof["change"]) != filepath.Base(directory) || stateString(proof["package_digest"]) != stateString(brief["digest"]) || stateString(proof["source_fingerprint"]) != current || stateString(proof["status"]) != "passed" || !verificationProofEnvironmentCurrent(workspace.root, proof) {
			return nil, workflowError("STALE_EVIDENCE", "gate do quick sem prova atual: "+gate.unit)
		}
		if err := rejectLaterFailedProof(proofs, proof); err != nil {
			return nil, err
		}
		ids = append(ids, id)
	}
	return ids, nil
}
