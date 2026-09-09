package gokernel

import (
	"encoding/json"
	"os"
	"path/filepath"
	"sort"
	"strings"

	methodlayout "github.com/felipebianchini2006/bianchini-method/internal/workspace"
)

func matchingVerificationProofs(pack coherencePackage, executionKey string) ([]map[string]any, error) {
	proofs, err := loadVerificationProofs(pack)
	if err != nil {
		return nil, err
	}
	result := []map[string]any{}
	for _, proof := range proofs {
		if stateString(proof["execution_key"]) == executionKey {
			result = append(result, proof)
		}
	}
	sort.Slice(result, func(i, j int) bool { return stateInt(result[i]["attempt"]) < stateInt(result[j]["attempt"]) })
	return result, nil
}

func loadVerificationProofs(pack coherencePackage) (map[string]map[string]any, error) {
	directory := methodlayout.Proofs(pack.directory)
	entries, err := os.ReadDir(directory)
	if os.IsNotExist(err) {
		return map[string]map[string]any{}, nil
	}
	if err != nil {
		return nil, workflowError("STALE_EVIDENCE", "proof store ilegível")
	}
	result := map[string]map[string]any{}
	for _, entry := range entries {
		if entry.IsDir() || !strings.HasSuffix(entry.Name(), ".json") {
			return nil, workflowError("STALE_EVIDENCE", "proof store contém entrada inválida")
		}
		content, readErr := os.ReadFile(filepath.Join(directory, entry.Name()))
		if readErr != nil {
			return nil, workflowError("STALE_EVIDENCE", "proof ilegível: "+entry.Name())
		}
		proof, decodeErr := decodeStrictJSONObject(content)
		if decodeErr != nil {
			return nil, workflowError("STALE_EVIDENCE", "proof inválido: "+entry.Name())
		}
		identifier := stateString(proof["proof_id"])
		if !verificationProofID.MatchString(identifier) || entry.Name() != identifier+".json" || stateString(proof["record_digest"]) != verificationRecordDigest(proof) {
			return nil, workflowError("STALE_EVIDENCE", "proof adulterado: "+entry.Name())
		}
		result[identifier] = proof
	}
	return result, nil
}

func validateProofSet(pack coherencePackage, identifiers []string, scope, plan, task string, requireCurrent bool) ([]string, error) {
	ids := nonemptyUnique(identifiers)
	if len(ids) == 0 {
		return nil, workflowError("STALE_EVIDENCE", "conclusão exige proof_id gerado por bm verify")
	}
	proofs, err := loadVerificationProofs(pack)
	if err != nil {
		return nil, err
	}
	current := ""
	if requireCurrent {
		current, err = verificationSourceFingerprint(pack.workspace.root)
		if err != nil {
			return nil, err
		}
	}
	for _, identifier := range ids {
		proof := proofs[identifier]
		if proof == nil || stateString(proof["status"]) != "passed" || stateString(proof["scope"]) != scope || stateString(proof["change"]) != filepath.Base(pack.directory) || stateString(proof["package_digest"]) != stateString(pack.contract["digest"]) || scope != "release" && stateString(proof["plan"]) != plan {
			return nil, workflowError("STALE_EVIDENCE", "proof_id incompatível: "+identifier)
		}
		for _, newer := range proofs {
			if stateString(newer["scope"]) == scope && stateString(newer["unit"]) == stateString(proof["unit"]) && stateString(newer["source_fingerprint"]) == stateString(proof["source_fingerprint"]) && stateInt(newer["execution_sequence"]) > stateInt(proof["execution_sequence"]) && stateString(newer["status"]) != "passed" {
				return nil, workflowError("STALE_EVIDENCE", "execução posterior do gate falhou")
			}
		}
		if task != "" && stateString(proof["task"]) != task {
			return nil, workflowError("STALE_EVIDENCE", "proof_id pertence a outra tarefa: "+identifier)
		}
		if requireCurrent && stateString(proof["source_fingerprint"]) != current {
			return nil, workflowError("STALE_EVIDENCE", "proof_id não pertence ao estado atual do código: "+identifier)
		}
		if requireCurrent && !verificationProofEnvironmentCurrent(pack.workspace.root, proof) {
			return nil, workflowError("STALE_EVIDENCE", "proof_id não pertence ao ambiente ou evidência atual: "+identifier)
		}
	}
	if err := validateGateCoverage(pack, proofs, ids, scope, plan, task); err != nil {
		return nil, err
	}
	return ids, nil
}

func verificationProofEnvironmentCurrent(root string, proof map[string]any) bool {
	if stateString(proof["kind"]) == "procedure" {
		path, err := confinedPath(root, stateString(proof["evidence_path"]), "proof.evidence", true)
		if err != nil {
			return false
		}
		content, err := os.ReadFile(path)
		return err == nil && len(content) > 0 && sha256Bytes(content) == stateString(proof["evidence_sha256"])
	}
	argv, ok := waveExactStringList(proof["argv"])
	return ok && len(argv) > 0 && stateString(proof["environment_fingerprint"]) == verificationEnvironmentFingerprint(argv)
}

func validateProofContext(pack coherencePackage, identifiers []string, contextDigest string) error {
	proofs, err := loadVerificationProofs(pack)
	if err != nil {
		return err
	}
	for _, identifier := range identifiers {
		if stateString(proofs[identifier]["context_pack_digest"]) != contextDigest {
			return workflowError("STALE_EVIDENCE", "proof_id não pertence ao context pack usado: "+identifier)
		}
	}
	return nil
}

func recordVerificationReview(pack coherencePackage, flags parsedFlags) (map[string]any, error) {
	scope, reviewer, verdict := lastValue(flags, "--scope"), strings.TrimSpace(lastValue(flags, "--reviewer")), lastValue(flags, "--verdict")
	planID, taskID := lastValue(flags, "--plan"), lastValue(flags, "--task")
	if !oneOf(scope, "task", "plan", "release") || reviewer == "" || !oneOf(verdict, "approved", "changes_requested") {
		return nil, userError("verify review exige --scope task|plan|release, --reviewer e --verdict approved|changes_requested")
	}
	if (scope != "release" && planID == "") || (scope == "task" && taskID == "") {
		return nil, userError("verify review exige identidade completa do escopo")
	}
	proofIDs := nonemptyUnique(flags.values["--proof"])
	findings, err := structuredReviewFindings(pack.workspace.root, flags.values["--finding"])
	if err != nil {
		return nil, err
	}
	if verdict == "approved" {
		if len(findings) > 0 {
			return nil, workflowError("REVIEW_BLOCKED", "approved não aceita finding aberto")
		}
		if err := validateReviewProofs(pack, proofIDs, scope, planID, taskID, verdict); err != nil {
			return nil, err
		}
		if err := unresolvedVerificationReviews(pack, scope, planID, taskID, flags.values["--resolves-review"]); err != nil {
			return nil, err
		}
	} else {
		if len(findings) == 0 {
			return nil, workflowError("REVIEW_BLOCKED", "changes_requested exige finding estruturado")
		}
		if len(proofIDs) > 0 {
			if err := validateReviewProofs(pack, proofIDs, scope, planID, taskID, verdict); err != nil {
				return nil, err
			}
		}
	}
	fingerprint, err := verificationSourceFingerprint(pack.workspace.root)
	if err != nil {
		return nil, err
	}
	payload := map[string]any{
		"schema_version": 1, "change": filepath.Base(pack.directory), "scope": scope,
		"plan": nullableString(planID), "task": nullableString(taskID), "reviewer": reviewer,
		"verdict": verdict, "proof_ids": stringSliceAny(proofIDs), "findings": findings, "resolves_reviews": stringSliceAny(flags.values["--resolves-review"]),
		"source_fingerprint": fingerprint, "reviewed_at": utcNow(),
	}
	idMaterial := cloneMap(payload)
	delete(idMaterial, "reviewed_at")
	reviewID := "review-" + waveStableDigest(idMaterial)[:32]
	payload["review_id"] = reviewID
	payload["record_digest"] = verificationRecordDigest(payload)
	path := filepath.Join(methodlayout.Reviews(pack.directory), reviewID+".json")
	encoded, _ := json.MarshalIndent(payload, "", "  ")
	if err := pack.workspace.atomicWrite(path, append(encoded, '\n')); err != nil {
		return nil, err
	}
	if err := writePlanEvidenceIndex(pack, planID); err != nil {
		return nil, err
	}
	if scope == "release" && verdict == "approved" {
		if err := attachReleaseReview(pack, reviewID, proofIDs); err != nil {
			return nil, err
		}
	}
	return map[string]any{"review_id": reviewID, "verdict": verdict, "scope": scope, "proof_ids": proofIDs}, nil
}

func validateReviewProofs(pack coherencePackage, identifiers []string, scope, plan, task, verdict string) error {
	if verdict == "approved" {
		_, err := validateProofSet(pack, identifiers, scope, plan, task, true)
		return err
	}
	proofs, err := loadVerificationProofs(pack)
	if err != nil {
		return err
	}
	current, err := verificationSourceFingerprint(pack.workspace.root)
	if err != nil {
		return err
	}
	for _, identifier := range identifiers {
		proof := proofs[identifier]
		if proof == nil || stateString(proof["scope"]) != scope || stateString(proof["change"]) != filepath.Base(pack.directory) || stateString(proof["package_digest"]) != stateString(pack.contract["digest"]) || (scope != "release" && stateString(proof["plan"]) != plan) || (task != "" && stateString(proof["task"]) != task) || stateString(proof["source_fingerprint"]) != current || !verificationProofEnvironmentCurrent(pack.workspace.root, proof) {
			return workflowError("STALE_EVIDENCE", "proof_id incompatível: "+identifier)
		}
	}
	return nil
}

func attachReleaseReview(pack coherencePackage, reviewID string, proofIDs []string) error {
	path := filepath.Join(pack.directory, "results", "RELEASE.md")
	release, err := readStructuredFrontmatter(path)
	if err != nil {
		return workflowError("REVIEW_REQUIRED", "verify release deve executar antes da revisão final")
	}
	releaseProofs, ok := waveExactStringList(release["proof_ids"])
	if !ok || !sameStrings(releaseProofs, proofIDs) {
		return workflowError("REVIEW_REQUIRED", "revisão final não cobre exatamente o release atual")
	}
	release["review_id"], release["status"], release["reviewed_at"] = reviewID, "reviewed", utcNow()
	document, _ := frontmatterDocument(release, "# Release candidate\n\nBaseline automatizada e revisão final aprovadas.", false)
	return pack.workspace.atomicWrite(path, document)
}

func validateVerificationReview(pack coherencePackage, identifier, scope, plan, task string, proofIDs []string, requireCurrent bool) error {
	if err := unresolvedVerificationReviews(pack, scope, plan, task, nil); err != nil {
		return err
	}
	if !verificationReviewID.MatchString(identifier) {
		return workflowError("REVIEW_REQUIRED", "conclusão exige review_id gerado por bm verify review")
	}
	path := filepath.Join(methodlayout.Reviews(pack.directory), identifier+".json")
	content, err := os.ReadFile(path)
	if err != nil {
		return workflowError("REVIEW_REQUIRED", "review_id não encontrado: "+identifier)
	}
	review, err := decodeStrictJSONObject(content)
	if err != nil || stateString(review["review_id"]) != identifier || stateString(review["record_digest"]) != verificationRecordDigest(review) {
		return workflowError("REVIEW_REQUIRED", "review adulterado: "+identifier)
	}
	if stateString(review["verdict"]) != "approved" || stateString(review["scope"]) != scope || stateString(review["change"]) != filepath.Base(pack.directory) || stateString(review["plan"]) != plan || stateString(review["task"]) != task {
		return workflowError("REVIEW_REQUIRED", "review incompatível: "+identifier)
	}
	reviewProofs, ok := waveExactStringList(review["proof_ids"])
	if !ok || !sameStrings(reviewProofs, proofIDs) {
		return workflowError("REVIEW_REQUIRED", "review não cobre exatamente os proofs informados")
	}
	if requireCurrent {
		fingerprint, fingerprintErr := verificationSourceFingerprint(pack.workspace.root)
		if fingerprintErr != nil {
			return fingerprintErr
		}
		if stateString(review["source_fingerprint"]) != fingerprint {
			return workflowError("STALE_EVIDENCE", "review não pertence ao estado atual do código")
		}
	}
	return nil
}
