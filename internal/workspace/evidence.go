package workspace

import (
	"fmt"
	"path/filepath"
	"strings"
)

// Record paths are relative to a change, whether active or archived.
func Proofs(changeDir string) string      { return filepath.Join(changeDir, "results", "proofs") }
func Logs(changeDir string) string        { return filepath.Join(changeDir, "results", "logs") }
func Reviews(changeDir string) string     { return filepath.Join(changeDir, "results", "reviews") }
func Tasks(changeDir, plan string) string { return filepath.Join(changeDir, "results", "tasks", plan) }
func EvidenceIndex(planDocument string) string {
	return filepath.Join(filepath.Dir(planDocument), "evidence", "INDEX.md")
}

// ResolveLog accepts change-relative references and the root-relative references
// written by 1.1.0. It never rewrites a sealed record. The caller verifies the file.
func ResolveLog(changeDir, reference string) (string, error) {
	ref := filepath.ToSlash(reference)
	for _, area := range []string{"changes", "archive"} {
		prefix := ".bianchini/" + area + "/" + filepath.Base(changeDir) + "/"
		if strings.HasPrefix(ref, prefix) {
			ref = strings.TrimPrefix(ref, prefix)
			break
		}
	}
	if strings.Contains(ref, "\\") || strings.Contains(ref, ":") || filepath.IsAbs(ref) || filepath.ToSlash(filepath.Clean(ref)) != ref || !strings.HasPrefix(ref, "results/logs/") {
		return "", fmt.Errorf("referência de log inválida: %s", reference)
	}
	name := strings.TrimPrefix(ref, "results/logs/")
	if name == "" || strings.Contains(name, "/") || !strings.HasSuffix(name, ".log") {
		return "", fmt.Errorf("nome de log inválido")
	}
	return filepath.Join(Logs(changeDir), name), nil
}
