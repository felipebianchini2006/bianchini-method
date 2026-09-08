package gokernel

import (
	"bytes"
	"encoding/json"
	"fmt"
	"image"
	_ "image/gif"
	_ "image/jpeg"
	_ "image/png"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"github.com/felipebianchini2006/bianchini-method/internal/acceptance"
	methodlayout "github.com/felipebianchini2006/bianchini-method/internal/workspace"
)

func planAcceptanceScenarios(plan planContract) ([]acceptance.Scenario, error) {
	raw, ok := plan.value["scenarios"].([]any)
	if !ok || len(raw) == 0 {
		return nil, workflowError("SCENARIO_COVERAGE", plan.id+" exige cenários de aceite antes da verificação do release")
	}
	content, err := json.Marshal(raw)
	if err != nil {
		return nil, err
	}
	var scenarios []acceptance.Scenario
	decoder := json.NewDecoder(bytes.NewReader(content))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&scenarios); err != nil {
		return nil, workflowError("SCENARIO_COVERAGE", plan.id+": "+err.Error())
	}
	for i := range scenarios {
		if scenarios[i].Plan != "" && scenarios[i].Plan != plan.id {
			return nil, workflowError("SCENARIO_COVERAGE", "cenário pertence a outro plano")
		}
		scenarios[i].Plan = plan.id
	}
	if err := acceptance.ValidateContract(scenarios, normalizedPlanStrings(plan, "requirements")); err != nil {
		return nil, workflowError("SCENARIO_COVERAGE", plan.id+": "+err.Error())
	}
	return scenarios, nil
}

func requiredAcceptanceScenarios(pack coherencePackage) ([]acceptance.Scenario, error) {
	var scenarios []acceptance.Scenario
	for _, plan := range pack.plans {
		planned, err := planAcceptanceScenarios(plan)
		if err != nil {
			return nil, err
		}
		scenarios = append(scenarios, planned...)
	}
	journeys := pack.expected.sections["journeys"]
	for _, scenario := range scenarios {
		if scenario.Journey != "" && journeys[scenario.Journey] == nil {
			return nil, workflowError("SCENARIO_COVERAGE", "jornada desconhecida: "+scenario.Journey)
		}
	}
	journeyIDs := make([]string, 0, len(journeys))
	for id := range journeys {
		journeyIDs = append(journeyIDs, id)
	}
	sort.Strings(journeyIDs)
	for _, id := range journeyIDs {
		journey := journeys[id]
		covered := false
		profiles, platforms, states := map[string]bool{}, map[string]bool{}, map[string]bool{}
		for _, scenario := range scenarios {
			if scenario.Journey != id {
				continue
			}
			covered = true
			profiles[scenario.Profile], platforms[scenario.Platform], states[scenario.State] = true, true, true
		}
		if !covered {
			return nil, workflowError("SCENARIO_COVERAGE", "jornada sem cenário: "+id)
		}
		for _, dimension := range []struct {
			name    string
			covered map[string]bool
		}{{"profiles", profiles}, {"platforms", platforms}, {"states", states}} {
			if raw, exists := journey[dimension.name]; exists {
				values, ok := waveExactStringList(raw)
				if !ok || len(values) == 0 {
					return nil, workflowError("SCENARIO_COVERAGE", id+"."+dimension.name+" exige lista não vazia")
				}
				for _, value := range values {
					if !dimension.covered[value] {
						return nil, workflowError("SCENARIO_COVERAGE", id+" sem cenário para "+dimension.name+"="+value)
					}
				}
			}
		}
	}
	return scenarios, nil
}

func homologationDocumentPath(pack coherencePackage, candidate map[string]any) string {
	return methodlayout.New(pack.workspace.root).ReleaseCandidateDocument(filepath.Base(pack.directory), stateString(candidate["id"]))
}

func scenarioValues(scenarios []acceptance.Scenario) []any {
	content, _ := json.Marshal(scenarios)
	var values []any
	_ = json.Unmarshal(content, &values)
	return values
}

func createHomologationDraft(pack coherencePackage, candidate map[string]any, fingerprint string, required []acceptance.Scenario, proofs []string) error {
	path := homologationDocumentPath(pack, candidate)
	if _, err := os.Lstat(path); err == nil {
		return nil
	} else if !os.IsNotExist(err) {
		return err
	}
	scenarios := make([]acceptance.Result, len(required))
	for i, scenario := range required {
		scenarios[i] = acceptance.Result{Plan: scenario.Plan, ID: scenario.ID, Result: "not_run", Fingerprint: fingerprint, Evidence: []acceptance.Evidence{}}
	}
	gates := make([]any, len(proofs))
	for i, proof := range proofs {
		gates[i] = map[string]any{"proof_id": proof, "result": "passed"}
	}
	value := map[string]any{"schema_version": 1, "change": filepath.Base(pack.directory), "rc": candidate, "fingerprint": fingerprint, "status": "running", "gates": gates, "blockers": []any{}, "findings": []any{}, "manual_proofs": []any{}, "scenarios": scenarios}
	document, err := frontmatterDocument(value, "# Homologação\n\nExecutar os cenários obrigatórios de RELEASE.md na superfície real. Registrar observações e evidências do candidato antes de aceitar. O relatório não comprova ausência absoluta de defeitos.", false)
	if err != nil {
		return err
	}
	return pack.workspace.atomicWrite(path, document)
}

func validateHomologationScenarios(pack coherencePackage, release, homologation map[string]any) error {
	required, err := requiredAcceptanceScenarios(pack)
	if err != nil {
		return err
	}
	if waveStableDigest(release["scenario_requirements"]) != waveStableDigest(scenarioValues(required)) {
		return workflowError("SCENARIO_COVERAGE", "cenários do release divergem do pacote aprovado")
	}
	content, err := json.Marshal(homologation["scenarios"])
	if err != nil {
		return err
	}
	var results []acceptance.Result
	decoder := json.NewDecoder(bytes.NewReader(content))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&results); err != nil {
		return workflowError("SCENARIO_COVERAGE", err.Error())
	}
	candidate := stateObject(release["candidate"])
	evidenceRoot := filepath.Join(filepath.Dir(homologationDocumentPath(pack, candidate)), "evidence")
	inspect := func(evidence acceptance.Evidence) error {
		return inspectHomologationEvidence(pack.workspace.root, evidenceRoot, evidence)
	}
	if err := acceptance.ValidateResults(required, results, stateString(release["fingerprint"]), inspect); err != nil {
		return workflowError("SCENARIO_COVERAGE", err.Error())
	}
	return nil
}

func inspectHomologationEvidence(root, evidenceRoot string, evidence acceptance.Evidence) error {
	path, err := confinedPath(root, evidence.Path, "homologation.evidence", true)
	if err != nil {
		return err
	}
	relative, err := filepath.Rel(evidenceRoot, path)
	if err != nil || relative == ".." || strings.HasPrefix(relative, ".."+string(filepath.Separator)) || filepath.IsAbs(relative) {
		return fmt.Errorf("evidência deve pertencer ao diretório evidence do candidato")
	}
	info, err := os.Lstat(path)
	if err != nil || !info.Mode().IsRegular() || info.Size() == 0 || info.Size() > 32*1024*1024 {
		return fmt.Errorf("evidência ausente, vazia ou acima de 32 MiB")
	}
	content, err := os.ReadFile(path)
	if err != nil || !waveDigest.MatchString(evidence.SHA256) || sha256Bytes(content) != evidence.SHA256 {
		return fmt.Errorf("evidência alterada ou digest inválido")
	}
	if evidence.Kind == "screenshot" {
		config, _, err := image.DecodeConfig(bytes.NewReader(content))
		if err != nil || config.Width < 2 || config.Height < 2 {
			return fmt.Errorf("screenshot não contém imagem válida")
		}
	}
	return nil
}
