package gokernel

import (
	"github.com/felipebianchini2006/bianchini-method/internal/acceptance"
	"path/filepath"
	"strings"
)

func validateReleaseClosure(pack coherencePackage, coherence map[string]any) (map[string]any, error) {
	for _, plan := range pack.plans {
		if err := unresolvedVerificationReviews(pack, "plan", plan.id, "", nil); err != nil {
			return nil, err
		}
		for _, task := range planTasks(plan) {
			if err := unresolvedVerificationReviews(pack, "task", plan.id, stateString(task["id"]), nil); err != nil {
				return nil, err
			}
		}
	}
	releasePath := filepath.Join(pack.directory, "results", "RELEASE.md")
	release, err := readStructuredFrontmatter(releasePath)
	if err != nil {
		return nil, workflowError("RELEASE_REQUIRED", "fechamento exige bm verify release")
	}
	if stateInt(release["schema_version"]) != 1 || stateString(release["change"]) != filepath.Base(pack.directory) || stateString(release["status"]) != "reviewed" || !oneOf(stateString(release["delivery"]), "ready", "not_applicable") || stateString(release["package_digest"]) != stateString(coherence["digest"]) {
		return nil, workflowError("RELEASE_REQUIRED", "RELEASE.md está incompleto ou obsoleto")
	}
	currentFingerprint, err := verificationSourceFingerprint(pack.workspace.root)
	if err != nil {
		return nil, err
	}
	if stateString(release["source_fingerprint"]) != currentFingerprint {
		return nil, workflowError("STALE_EVIDENCE", "release não pertence ao estado atual do código")
	}
	proofIDs, ok := waveExactStringList(release["proof_ids"])
	if !ok {
		return nil, workflowError("RELEASE_REQUIRED", "RELEASE.md não declara proofs válidos")
	}
	if _, err := validateProofSet(pack, proofIDs, "release", "", "", true); err != nil {
		return nil, err
	}
	reviewID := stateString(release["review_id"])
	if err := validateVerificationReview(pack, reviewID, "release", "", "", proofIDs, true); err != nil {
		return nil, err
	}
	candidate, ok := release["candidate"].(map[string]any)
	if !ok || stateString(candidate["id"]) == "" || stateString(candidate["revision"]) == "" || stateString(candidate["build"]) == "" || stateString(candidate["checksum"]) == "" || stateString(candidate["package_digest"]) != stateString(coherence["digest"]) {
		return nil, workflowError("RELEASE_REQUIRED", "fingerprint do RC está incompleto")
	}
	fingerprintMaterial := cloneMap(candidate)
	delete(fingerprintMaterial, "id")
	fingerprint := waveStableDigest(fingerprintMaterial)
	if stateString(release["fingerprint"]) != fingerprint || stateString(candidate["id"]) != "RC-"+fingerprint[:12] {
		return nil, workflowError("RELEASE_REQUIRED", "fingerprint do RC diverge")
	}
	if err := validateCandidateArtifact(pack, candidate); err != nil {
		return nil, err
	}
	storedProofs, err := loadVerificationProofs(pack)
	if err != nil {
		return nil, err
	}
	for _, id := range proofIDs {
		if stateString(storedProofs[id]["candidate_fingerprint"]) != fingerprint {
			return nil, workflowError("STALE_EVIDENCE", "prova pertence a outro candidato")
		}
	}
	if err := verificationOnlyMethodChangesSince(pack.workspace.root, stateString(candidate["revision"])); err != nil {
		return nil, err
	}
	homologation, err := readStructuredFrontmatter(homologationDocumentPath(pack, candidate))
	if err != nil {
		return nil, workflowError("HOMOLOGATION_REQUIRED", "fechamento exige HOMOLOGATION.md antes do archive")
	}
	blockers, blockersOK := homologation["blockers"].([]any)
	gates, gatesOK := homologation["gates"].([]any)
	rc := homologation["rc"]
	if stateInt(homologation["schema_version"]) != 1 || stateString(homologation["change"]) != filepath.Base(pack.directory) || stateString(homologation["status"]) != "accepted" || stateString(homologation["fingerprint"]) != fingerprint || !mapsEqual(stateObject(rc), candidate) || !blockersOK || len(blockers) > 0 || !gatesOK || len(gates) == 0 {
		return nil, workflowError("HOMOLOGATION_REQUIRED", "homologação aceita do RC exato está ausente ou incompleta")
	}
	if err := validateHomologationGates(pack.workspace.root, filepath.Join(filepath.Dir(homologationDocumentPath(pack, candidate)), "evidence"), homologation, proofIDs); err != nil {
		return nil, err
	}
	if err := validateHomologationScenarios(pack, release, homologation); err != nil {
		return nil, err
	}
	manualRequirements := stateArray(release["manual_requirements"])
	if len(manualRequirements) > 0 {
		manualProofs := stateArray(homologation["manual_proofs"])
		if !manualProofCoverage(pack.workspace.root, filepath.Join(filepath.Dir(homologationDocumentPath(pack, candidate)), "evidence"), manualRequirements, manualProofs) {
			return nil, workflowError("HOMOLOGATION_REQUIRED", "homologação não comprova todos os procedimentos manuais")
		}
	}
	return release, nil
}

func manualProofCoverage(root, evidenceRoot string, requirements, proofs []any) bool {
	covered := map[string]bool{}
	for _, raw := range proofs {
		proof := stateObject(raw)
		planID, taskID := stateString(proof["plan"]), stateString(proof["task"])
		evidence, expectedDigest := stateString(proof["evidence"]), stateString(proof["evidence_sha256"])
		if planID == "" || taskID == "" || evidence == "" || !waveDigest.MatchString(expectedDigest) {
			continue
		}
		if err := inspectHomologationEvidence(root, evidenceRoot, acceptance.Evidence{Kind: "observation", Path: evidence, SHA256: expectedDigest}); err != nil {
			continue
		}
		covered[planID+"/"+taskID] = true
	}
	for _, raw := range requirements {
		requirement := stateObject(raw)
		if !covered[stateString(requirement["plan"])+"/"+stateString(requirement["task"])] {
			return false
		}
	}
	return true
}

func verificationOnlyMethodChangesSince(root, revision string) error {
	if _, err := workflowGit(root, "merge-base", "--is-ancestor", revision, "HEAD"); err != nil {
		return workflowError("STALE_EVIDENCE", "revisão do RC não é ancestral do HEAD atual")
	}
	changed, err := workflowGit(root, "diff", "--name-only", revision, "HEAD", "--")
	if err != nil {
		return workflowError("STALE_EVIDENCE", "não foi possível validar a revisão do RC")
	}
	for _, path := range nonEmptyLines(changed) {
		path = filepath.ToSlash(path)
		if path != ".bianchini" && !strings.HasPrefix(path, ".bianchini/") {
			return workflowError("STALE_EVIDENCE", "código mudou depois da criação do RC: "+path)
		}
	}
	return nil
}

func verificationProductClean(root string) error {
	for _, args := range [][]string{{"diff", "--name-only", "HEAD", "--", ".", ":(exclude).bianchini"}, {"ls-files", "--others", "--exclude-standard", "--", ".", ":(exclude).bianchini"}} {
		output, err := workflowGit(root, args...)
		if err != nil {
			return workflowError("DIRTY_WORKSPACE", "não foi possível verificar código do candidato")
		}
		if strings.TrimSpace(output) != "" {
			return workflowError("DIRTY_WORKSPACE", "RC exige código commitado; mudanças pendentes: "+output)
		}
	}
	return nil
}
