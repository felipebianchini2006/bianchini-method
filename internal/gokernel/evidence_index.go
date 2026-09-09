package gokernel

import (
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"

	methodlayout "github.com/felipebianchini2006/bianchini-method/internal/workspace"
)

func verificationLogPath(pack coherencePackage, proof map[string]any) (string, error) {
	path, err := methodlayout.ResolveLog(pack.directory, stateString(proof["log_path"]))
	if err != nil {
		return "", err
	}
	relative, err := filepath.Rel(pack.workspace.root, path)
	if err != nil {
		return "", err
	}
	path, err = confinedPath(pack.workspace.root, relative, "proof.log", true)
	if err != nil {
		return "", err
	}
	info, err := os.Lstat(path)
	if err != nil || !info.Mode().IsRegular() || info.Size() > 1024*1024 {
		return "", fmt.Errorf("log ausente, inválido ou acima de 1 MiB")
	}
	content, err := os.ReadFile(path)
	if err != nil || sha256Bytes(content) != stateString(proof["log_sha256"]) {
		return "", fmt.Errorf("log alterado")
	}
	return filepath.ToSlash(relative), nil
}

// A derived navigation index; the records remain the sole source of evidence.
func writePlanEvidenceIndex(pack coherencePackage, planID string) error {
	if planID == "" {
		return nil
	}
	planPath, found := planFileForID(filepath.Join(pack.directory, "plans"), planID)
	if !found {
		return workflowError("MODEL_MISMATCH", "plano ausente: "+planID)
	}
	indexPath := methodlayout.EvidenceIndex(planPath)
	proofs, err := loadVerificationProofs(pack)
	if err != nil {
		return err
	}
	var lines []string
	link := func(label, path string) string {
		relative, _ := filepath.Rel(filepath.Dir(indexPath), path)
		return fmt.Sprintf("[%s](%s)", label, filepath.ToSlash(relative))
	}
	for id, proof := range proofs {
		if stateString(proof["plan"]) != planID {
			continue
		}
		log, err := verificationLogPath(pack, proof)
		if err != nil {
			return err
		}
		lines = append(lines, "- "+link(id, filepath.Join(methodlayout.Proofs(pack.directory), id+".json"))+" · "+stateString(proof["status"])+" · "+link("log", filepath.Join(pack.workspace.root, filepath.FromSlash(log))))
	}
	entries, err := os.ReadDir(methodlayout.Reviews(pack.directory))
	if err != nil && !os.IsNotExist(err) {
		return err
	}
	for _, entry := range entries {
		path := filepath.Join(methodlayout.Reviews(pack.directory), entry.Name())
		content, err := os.ReadFile(path)
		if err != nil {
			return err
		}
		review, err := decodeStrictJSONObject(content)
		if err != nil || stateString(review["record_digest"]) != verificationRecordDigest(review) {
			return workflowError("STALE_EVIDENCE", "review inválido no índice")
		}
		if stateString(review["plan"]) == planID {
			lines = append(lines, "- "+link(stateString(review["review_id"]), path)+" · "+stateString(review["verdict"]))
		}
	}
	tasks, err := filepath.Glob(filepath.Join(methodlayout.Tasks(pack.directory, planID), "*.md"))
	if err != nil {
		return err
	}
	for _, path := range tasks {
		lines = append(lines, "- "+link(filepath.Base(path), path))
	}
	sort.Strings(lines)
	body := "# Evidências " + planID + "\n\nÍndice derivado. Registros oficiais em `results/`; links relativos preservados após arquivamento.\n\n" + strings.Join(lines, "\n") + "\n"
	return pack.workspace.atomicWrite(indexPath, []byte(body))
}
