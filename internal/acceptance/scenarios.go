// Package acceptance validates the coverage of an approved product contract.
// It does not infer product quality from a command exit code or a file hash.
package acceptance

import (
	"fmt"
	"regexp"
	"strings"
)

var identifier = regexp.MustCompile(`^[A-Za-z][A-Za-z0-9_.:-]*$`)

type Scenario struct {
	Plan          string   `json:"plan,omitempty"`
	ID            string   `json:"id"`
	Requirements  []string `json:"requirements"`
	Journey       string   `json:"journey,omitempty"`
	Platform      string   `json:"platform"`
	Profile       string   `json:"profile"`
	State         string   `json:"state"`
	Expected      string   `json:"expected"`
	Risk          string   `json:"risk"`
	EvidenceKinds []string `json:"evidence_kinds"`
}

type Evidence struct {
	Kind   string `json:"kind"`
	Path   string `json:"path"`
	SHA256 string `json:"sha256"`
}

type Result struct {
	Plan        string     `json:"plan"`
	ID          string     `json:"id"`
	Result      string     `json:"result"`
	Fingerprint string     `json:"fingerprint"`
	Observed    string     `json:"observed"`
	Evidence    []Evidence `json:"evidence"`
}

func (s Scenario) Key() string { return s.Plan + "/" + s.ID }

func IsVisual(platform string) bool {
	switch platform {
	case "web", "android", "ios", "mobile", "desktop":
		return true
	}
	return false
}

// ValidateContract rejects gaps in the declared requirements before execution.
// Requirements not extracted from the source remain a semantic review concern.
func ValidateContract(scenarios []Scenario, requirements []string) error {
	if len(scenarios) == 0 {
		return fmt.Errorf("cenários de aceite obrigatórios ausentes")
	}
	wanted, covered, seen := map[string]bool{}, map[string]bool{}, map[string]bool{}
	for _, requirement := range requirements {
		wanted[requirement] = true
	}
	for _, scenario := range scenarios {
		if !identifier.MatchString(scenario.ID) || seen[scenario.Key()] {
			return fmt.Errorf("cenário inválido ou duplicado: %s", scenario.Key())
		}
		seen[scenario.Key()] = true
		if strings.TrimSpace(scenario.Risk) == "" || strings.TrimSpace(scenario.Profile) == "" || strings.TrimSpace(scenario.State) == "" || strings.TrimSpace(scenario.Expected) == "" {
			return fmt.Errorf("%s exige risco, perfil, estado e resultado esperado", scenario.Key())
		}
		switch scenario.Platform {
		case "web", "android", "ios", "mobile", "desktop", "api", "cli", "library", "data", "infra":
		default:
			return fmt.Errorf("%s exige plataforma conhecida", scenario.Key())
		}
		if len(scenario.Requirements) == 0 {
			return fmt.Errorf("%s não cobre requisito", scenario.Key())
		}
		local := map[string]bool{}
		for _, requirement := range scenario.Requirements {
			if !wanted[requirement] || local[requirement] {
				return fmt.Errorf("%s referencia requisito desconhecido ou duplicado: %s", scenario.Key(), requirement)
			}
			covered[requirement], local[requirement] = true, true
		}
		kinds := map[string]bool{}
		for _, kind := range scenario.EvidenceKinds {
			if (kind != "observation" && kind != "screenshot" && kind != "log") || kinds[kind] {
				return fmt.Errorf("%s declara tipo de evidência inválido ou duplicado", scenario.Key())
			}
			kinds[kind] = true
		}
		if !kinds["observation"] || (IsVisual(scenario.Platform) && !kinds["screenshot"]) {
			return fmt.Errorf("%s exige observação real e screenshot para interface visual", scenario.Key())
		}
	}
	for _, requirement := range requirements {
		if !covered[requirement] {
			return fmt.Errorf("requisito sem cenário: %s", requirement)
		}
	}
	return nil
}

// ValidateResults requires the exact planned set, current candidate and all
// evidence kinds. The caller owns reading and validating the evidence bytes.
func ValidateResults(required []Scenario, results []Result, fingerprint string, inspect func(Evidence) error) error {
	if fingerprint == "" || len(required) == 0 || inspect == nil {
		return fmt.Errorf("candidato ou contrato de homologação ausente")
	}
	wanted := make(map[string]Scenario, len(required))
	for _, scenario := range required {
		wanted[scenario.Key()] = scenario
	}
	seen := map[string]bool{}
	for _, result := range results {
		key := result.Plan + "/" + result.ID
		scenario, ok := wanted[key]
		if !ok || seen[key] {
			return fmt.Errorf("cenário não planejado ou duplicado: %s", key)
		}
		seen[key] = true
		if result.Result != "passed" || result.Fingerprint != fingerprint || strings.TrimSpace(result.Observed) == "" {
			return fmt.Errorf("%s não possui resultado aprovado no candidato atual", key)
		}
		kinds, files := map[string]bool{}, map[string]bool{}
		for _, evidence := range result.Evidence {
			if evidence.Kind != "observation" && evidence.Kind != "screenshot" && evidence.Kind != "log" {
				return fmt.Errorf("%s possui evidência de tipo desconhecido", key)
			}
			if files[evidence.Kind+"/"+evidence.Path] {
				return fmt.Errorf("%s repete evidência", key)
			}
			if err := inspect(evidence); err != nil {
				return fmt.Errorf("%s: %w", key, err)
			}
			files[evidence.Kind+"/"+evidence.Path], kinds[evidence.Kind] = true, true
		}
		for _, kind := range scenario.EvidenceKinds {
			if !kinds[kind] {
				return fmt.Errorf("%s sem evidência %s", key, kind)
			}
		}
	}
	for _, scenario := range required {
		if !seen[scenario.Key()] {
			return fmt.Errorf("cenário obrigatório não executado: %s", scenario.Key())
		}
	}
	return nil
}
