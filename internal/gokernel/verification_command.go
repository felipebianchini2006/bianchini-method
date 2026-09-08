package gokernel

import (
	"fmt"
	"strings"
)

func taskByID(plan planContract, identifier string) map[string]any {
	var selected map[string]any
	for _, task := range planTasks(plan) {
		if stateString(task["id"]) == identifier {
			if selected != nil {
				return nil
			}
			selected = task
		}
	}
	return selected
}

func taskVerificationSpec(task map[string]any) (verificationSpec, error) {
	verify := stateObject(task["verify"])
	kind := stateString(verify["kind"])
	spec := verificationSpec{
		kind: kind, cwd: strings.TrimSpace(stateString(verify["cwd"])),
		timeout: stateInt(verify["timeout_seconds"]), proves: strings.TrimSpace(stateString(verify["proves"])),
		description: strings.TrimSpace(stateString(verify["run"])),
		cache:       stateString(verify["cache"]),
	}
	if spec.cwd == "" {
		spec.cwd = "."
	}
	if spec.timeout == 0 {
		spec.timeout = 300
	}
	if kind == "procedure" {
		return spec, nil
	}
	argv, err := stringValues(verify["argv"], "verify.argv")
	if err != nil {
		return verificationSpec{}, workflowError("MODEL_MISMATCH", err.Error())
	}
	if len(argv) > 0 {
		spec.argv = argv
		return spec, nil
	}
	return commandVerificationSpecWith(spec, spec.description)
}

func commandVerificationSpec(raw, proves string) (verificationSpec, error) {
	return commandVerificationSpecWith(verificationSpec{kind: "command", cwd: ".", timeout: 300, proves: proves, description: strings.TrimSpace(raw)}, raw)
}

func commandVerificationSpecWith(spec verificationSpec, raw string) (verificationSpec, error) {
	argv, err := splitVerificationCommand(raw)
	if err != nil {
		return verificationSpec{}, workflowError("MODEL_MISMATCH", "comando de verificação inválido: "+err.Error()+"; declare verify.argv")
	}
	spec.argv = argv
	return spec, nil
}

func splitVerificationCommand(raw string) ([]string, error) {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return nil, fmt.Errorf("comando vazio")
	}
	result, current := []string{}, strings.Builder{}
	quote := rune(0)
	escaped := false
	flush := func() {
		if current.Len() > 0 {
			result = append(result, current.String())
			current.Reset()
		}
	}
	for _, character := range raw {
		if escaped {
			current.WriteRune(character)
			escaped = false
			continue
		}
		if character == '\\' && quote != '\'' {
			escaped = true
			continue
		}
		if quote != 0 {
			if character == quote {
				quote = 0
			} else {
				current.WriteRune(character)
			}
			continue
		}
		if character == '\'' || character == '"' {
			quote = character
			continue
		}
		if strings.ContainsRune("|&;<>`", character) {
			return nil, fmt.Errorf("operador de shell %q não é permitido", character)
		}
		if character == ' ' || character == '\t' || character == '\n' {
			flush()
			continue
		}
		current.WriteRune(character)
	}
	if escaped || quote != 0 {
		return nil, fmt.Errorf("aspas ou escape incompletos")
	}
	flush()
	if len(result) == 0 {
		return nil, fmt.Errorf("comando vazio")
	}
	return result, nil
}

type verificationRequest struct {
	pack            coherencePackage
	scope           string
	plan            string
	task            string
	unit            string
	seam            string
	packageDigest   string
	packDigest      string
	retryReason     string
	evidence        string
	candidateDigest string
	candidate       map[string]any
}
