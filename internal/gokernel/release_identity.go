package gokernel

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"
)

// Identity comes from the delivery itself. Declared checksums are expectations.
func releaseArtifactIdentity(root, kind, build, expected string) (string, error) {
	var actual string
	switch kind {
	case "file":
		path, err := confinedPath(root, build, "release.build", true)
		if err != nil {
			return "", workflowError("ARTIFACT_INVALID", "arquivo fora do repositório ou ausente")
		}
		if !regularFile(path) {
			return "", workflowError("ARTIFACT_INVALID", "artefato deve ser arquivo regular existente")
		}
		content, err := os.ReadFile(path)
		if err != nil {
			return "", workflowError("ARTIFACT_INVALID", "artefato ilegível")
		}
		actual = sha256Bytes(content)
	case "container":
		ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
		defer cancel()
		output, err := exec.CommandContext(ctx, "docker", "image", "inspect", "--format", "{{.Id}}", build).Output()
		if err != nil {
			return "", workflowError("ARTIFACT_INVALID", "imagem não pôde ser inspecionada")
		}
		actual = strings.TrimPrefix(strings.TrimSpace(string(output)), "sha256:")
	case "deployment":
		// The target's health/version endpoint must report the running content hash.
		client := &http.Client{Timeout: 30 * time.Second, CheckRedirect: func(_ *http.Request, _ []*http.Request) error { return http.ErrUseLastResponse }}
		response, err := client.Get(build)
		if err != nil {
			return "", workflowError("ARTIFACT_INVALID", "alvo de deployment indisponível")
		}
		defer response.Body.Close()
		if response.StatusCode != http.StatusOK {
			return "", workflowError("ARTIFACT_INVALID", "smoke do alvo falhou")
		}
		var identity struct {
			Version string `json:"version"`
		}
		if err := json.NewDecoder(io.LimitReader(response.Body, 65536)).Decode(&identity); err != nil {
			return "", workflowError("ARTIFACT_INVALID", "alvo deve retornar JSON com version igual ao SHA-256 em execução")
		}
		actual = strings.TrimPrefix(identity.Version, "sha256:")
	default:
		return "", workflowError("ARTIFACT_INVALID", "artifact-kind exige file, container ou deployment")
	}
	if !waveDigest.MatchString(actual) || expected != "" && expected != actual {
		return "", workflowError("ARTIFACT_MISMATCH", "identidade observada difere do checksum declarado")
	}
	return actual, nil
}

func validateHomologationGates(root string, homologation map[string]any, proofIDs []string) error {
	findings, ok := homologation["findings"].([]any)
	if !ok {
		return workflowError("HOMOLOGATION_REQUIRED", "findings deve ser lista explícita")
	}
	for _, raw := range findings {
		finding := stateObject(raw)
		status, severity := stateString(finding["status"]), strings.ToLower(stateString(finding["severity"]))
		if !oneOf(status, "open", "resolved", "accepted") || !oneOf(severity, "critical", "high", "medium", "low", "info") {
			return workflowError("HOMOLOGATION_REQUIRED", "finding inválido")
		}
		if (oneOf(severity, "critical", "high") || finding["blocking"] == true) && status != "resolved" {
			return workflowError("HOMOLOGATION_BLOCKED", "finding bloqueante não resolvido")
		}
		if status == "resolved" {
			path, err := confinedPath(root, stateString(finding["resolution_evidence"]), "finding.resolution_evidence", true)
			if err != nil || !regularFile(path) {
				return workflowError("HOMOLOGATION_BLOCKED", "resolução exige arquivo real")
			}
			content, err := os.ReadFile(path)
			if err != nil || len(content) == 0 || sha256Bytes(content) != stateString(finding["resolution_sha256"]) {
				return workflowError("HOMOLOGATION_BLOCKED", "evidência de resolução ausente ou alterada")
			}
		}
	}
	covered := map[string]bool{}
	for _, raw := range stateArray(homologation["gates"]) {
		gate := stateObject(raw)
		id := stateString(gate["proof_id"])
		if stateString(gate["result"]) != "passed" || !containsString(proofIDs, id) || covered[id] {
			return workflowError("HOMOLOGATION_REQUIRED", "gate obrigatório exige resultado passed e prova do RC; N/A não dispensa obrigação")
		}
		covered[id] = true
	}
	if len(covered) != len(proofIDs) {
		return workflowError("GATE_COVERAGE", "homologação não cobre todos os gates do RC")
	}
	return nil
}

func validateCandidateArtifact(pack coherencePackage, candidate map[string]any) error {
	_, err := releaseArtifactIdentity(pack.workspace.root, stateString(candidate["kind"]), stateString(candidate["build"]), stateString(candidate["checksum"]))
	return err
}

func canonicalArtifactBuild(root, kind, build string) string {
	if kind == "file" && filepath.IsAbs(build) {
		relative, err := filepath.Rel(root, build)
		if err == nil {
			return filepath.ToSlash(relative)
		}
	}
	return build
}
