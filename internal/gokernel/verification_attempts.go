package gokernel

import "sort"

func verificationAttemptPolicy(request verificationRequest, source string) (map[string]any, int, error) {
	proofs, err := loadVerificationProofs(request.pack)
	if err != nil {
		return nil, 0, err
	}
	profile := "standard"
	for _, plan := range request.pack.plans {
		if plan.id == request.plan {
			switch stateString(plan.value["execution"]) {
			case "grouped":
				profile = "lean"
			case "strict":
				profile = "full"
			}
		}
	}
	policy := policyResult(profile, "medium", "behavioral", "none", false, 0, request.seam, 0, nil, 0)
	limit := stateInt(policy["max_fix_rounds"])
	sequence := 0
	prior := []map[string]any{}
	for _, proof := range proofs {
		sequence = maxInt(sequence, stateInt(proof["execution_sequence"]))
		if stateString(proof["risk_seam"]) == request.seam {
			prior = append(prior, proof)
		}
	}
	sort.Slice(prior, func(i, j int) bool {
		return stateInt(prior[i]["execution_sequence"]) < stateInt(prior[j]["execution_sequence"])
	})
	round := 0
	// A passing unrelated gate must not erase failures of the same risk seam.
	// Identity excludes the display unit so renaming cannot reset the budget.
	pending := map[string]bool{}
	for _, proof := range prior {
		round = maxInt(round, stateInt(proof["fix_round"]))
		key := waveStableDigest(map[string]any{"argv": proof["argv"], "cwd": proof["cwd"], "kind": proof["kind"]})
		if stateString(proof["status"]) == "failed" {
			pending[key] = true
		} else if stateString(proof["status"]) == "passed" {
			delete(pending, key)
		}
	}
	if len(pending) > 0 && stateString(prior[len(prior)-1]["source_fingerprint"]) != source {
		if round >= limit {
			return nil, 0, workflowError("FIX_LIMIT_REACHED", "limite persistido do problema atingido; registre diagnóstico e replaneje, sem reiniciar contagem")
		}
		round++
	}
	return map[string]any{"profile": profile, "max_fix_rounds": limit, "fix_round": round, "risk_seam": request.seam}, sequence + 1, nil
}
