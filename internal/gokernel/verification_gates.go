package gokernel

import (
	"fmt"
	"path/filepath"
	"strings"
)

type requiredVerification struct {
	plan, task, unit string
	spec             verificationSpec
}

func rejectLaterFailedProof(proofs map[string]map[string]any, proof map[string]any) error {
	for _, newer := range proofs {
		if stateString(newer["scope"]) == stateString(proof["scope"]) && stateString(newer["unit"]) == stateString(proof["unit"]) && stateString(newer["source_fingerprint"]) == stateString(proof["source_fingerprint"]) && stateInt(newer["execution_sequence"]) > stateInt(proof["execution_sequence"]) && stateString(newer["status"]) != "passed" {
			return workflowError("STALE_EVIDENCE", "execução posterior do gate falhou")
		}
	}
	return nil
}

// The approved contract, never the submitted subset, defines completion.
func requiredVerifications(pack coherencePackage, scope, planID, taskID string) ([]requiredVerification, error) {
	var gates []requiredVerification
	for _, plan := range pack.plans {
		if scope != "release" && plan.id != planID {
			continue
		}
		if scope == "task" {
			task := taskByID(plan, taskID)
			if task == nil {
				return nil, workflowError("GATE_COVERAGE", "tarefa desconhecida")
			}
			spec, err := taskVerificationSpec(task)
			if err != nil {
				return nil, err
			}
			unit := strings.SplitN(filepath.Base(pack.directory), "-", 2)[0] + "/" + planID + "/" + taskID
			gates = append(gates, requiredVerification{planID, taskID, unit, spec})
			continue
		}
		for i, raw := range normalizedPlanStrings(plan, "verifications") {
			spec, err := legacyVerificationSpec(raw, "gate do plano")
			if err != nil {
				return nil, err
			}
			gates = append(gates, requiredVerification{plan.id, "", fmt.Sprintf("%s/gate-%02d", plan.id, i+1), spec})
		}
	}
	if len(gates) == 0 {
		return nil, workflowError("GATE_COVERAGE", "estágio sem verificações obrigatórias")
	}
	return gates, nil
}

func proofMatchesGate(proof map[string]any, gate requiredVerification) bool {
	argv, ok := waveExactStringList(proof["argv"])
	return ok && strings.Join(argv, "\x00") == strings.Join(gate.spec.argv, "\x00") &&
		stateString(proof["plan"]) == gate.plan && stateString(proof["task"]) == gate.task &&
		stateString(proof["unit"]) == gate.unit && stateString(proof["kind"]) == gate.spec.kind &&
		stateString(proof["cwd"]) == gate.spec.cwd && stateInt(proof["timeout_seconds"]) == gate.spec.timeout
}

func validateGateCoverage(pack coherencePackage, proofs map[string]map[string]any, ids []string, scope, plan, task string) error {
	gates, err := requiredVerifications(pack, scope, plan, task)
	if err != nil {
		return err
	}
	covered := make([]bool, len(gates))
	for _, id := range ids {
		matched := false
		for i, gate := range gates {
			if proofMatchesGate(proofs[id], gate) {
				covered[i], matched = true, true
			}
		}
		if !matched {
			return workflowError("GATE_COVERAGE", "prova não corresponde ao comando e gate exigidos: "+id)
		}
	}
	for i, complete := range covered {
		if !complete {
			return workflowError("GATE_COVERAGE", "gate obrigatório sem prova válida: "+gates[i].unit)
		}
	}
	return nil
}
