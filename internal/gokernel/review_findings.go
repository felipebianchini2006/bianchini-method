package gokernel

import (
	"os"
	"path/filepath"
	"strings"
)

func structuredReviewFindings(root string, values []string) ([]any, error) {
	findings := []any{}
	for _, raw := range values {
		finding, err := decodeStrictJSONObject([]byte(raw))
		if err != nil {
			return nil, workflowError("REVIEW_BLOCKED", "finding exige JSON com target, observed, requirement, severity, evidence e expected_fix")
		}
		for _, field := range []string{"target", "observed", "requirement", "severity", "evidence", "expected_fix"} {
			if strings.TrimSpace(stateString(finding[field])) == "" {
				return nil, workflowError("REVIEW_BLOCKED", "finding sem "+field)
			}
		}
		if !oneOf(stateString(finding["severity"]), "critical", "high", "medium", "low") {
			return nil, workflowError("REVIEW_BLOCKED", "severidade inválida")
		}
		path, err := confinedPath(root, stateString(finding["evidence"]), "finding.evidence", true)
		if err != nil || !regularFile(path) {
			return nil, workflowError("REVIEW_BLOCKED", "finding exige arquivo de evidência verificável")
		}
		content, err := os.ReadFile(path)
		if err != nil || len(content) == 0 {
			return nil, workflowError("REVIEW_BLOCKED", "evidência vazia")
		}
		if expected := stateString(finding["evidence_sha256"]); expected != "" && expected != sha256Bytes(content) {
			return nil, workflowError("REVIEW_BLOCKED", "evidência divergente")
		}
		finding["evidence_sha256"] = sha256Bytes(content)
		finding["status"] = "open"
		findings = append(findings, finding)
	}
	return findings, nil
}

// An explicit resolution with current passing proofs retires a material review.
func unresolvedVerificationReviews(pack coherencePackage, scope, plan, task string, resolutions []string) error {
	entries, err := os.ReadDir(filepath.Join(pack.directory, "results", "reviews"))
	if os.IsNotExist(err) {
		return nil
	}
	if err != nil {
		return err
	}
	open := map[string]bool{}
	resolved := map[string]bool{}
	for _, entry := range entries {
		content, err := os.ReadFile(filepath.Join(pack.directory, "results", "reviews", entry.Name()))
		if err != nil {
			return err
		}
		review, err := decodeStrictJSONObject(content)
		if err != nil || stateString(review["record_digest"]) != verificationRecordDigest(review) {
			return workflowError("REVIEW_BLOCKED", "registro de revisão inválido")
		}
		if stateString(review["scope"]) != scope || stateString(review["plan"]) != plan || stateString(review["task"]) != task {
			continue
		}
		if stateString(review["verdict"]) == "changes_requested" {
			open[stateString(review["review_id"])] = true
		}
		if stateString(review["verdict"]) == "approved" {
			for _, id := range stringsFromAny(review["resolves_reviews"]) {
				resolved[id] = true
			}
		}
	}
	for _, id := range resolutions {
		if !open[id] {
			return workflowError("REVIEW_BLOCKED", "resolução referencia revisão desconhecida")
		}
		resolved[id] = true
	}
	for id := range open {
		if !resolved[id] {
			return workflowError("REVIEW_BLOCKED", "finding material pendente: "+id+"; resolva com provas atuais e --resolves-review")
		}
	}
	return nil
}
