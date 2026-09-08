package gokernel

import (
	"fmt"
	"strings"
)

func runStatus(args []string) (any, error) {
	flags, positionals, err := parseArguments(args, map[string]bool{"--format": true, "--repo": true}, map[string]bool{})
	if err != nil {
		return nil, err
	}
	if len(positionals) > 0 {
		return nil, unrecognizedArgumentsError(positionals)
	}
	format := lastValue(flags, "--format")
	if format == "" {
		format = "json"
	}
	if !oneOf(format, "json", "text") {
		return nil, argparseError(argparseInvalidChoice("--format", format, []string{"json", "text"}))
	}
	repo := lastValue(flags, "--repo")
	if repo == "" {
		repo = "."
	}
	root, err := repositoryRoot(repo)
	if err != nil {
		return nil, err
	}
	state, err := newMethodWorkspace(root).readState()
	if err != nil {
		return nil, err
	}
	if format == "json" {
		result := make(map[string]any, len(state)+1)
		for key, value := range state {
			result[key] = value
		}
		result["valid"] = true
		return result, nil
	}
	return renderStatus(state), nil
}

func renderStatus(state map[string]any) string {
	active := stateObject(state["active_work"])
	lines := []string{
		"# Status do projeto",
		"",
		"- Método: " + methodIdentity,
		"- Estado: " + statusText(state["status"], "desconhecido"),
		"- Trabalho ativo: " + statusText(active["id"], "nenhum"),
		"- Unidade atual: " + statusText(state["current_unit"], "nenhuma"),
		"- Próxima ação: " + statusText(state["next_action"], "não definida"),
	}
	return strings.Join(lines, "\n") + "\n"
}

func statusText(value any, fallback string) string {
	if value == nil {
		return fallback
	}
	text := strings.TrimSpace(fmt.Sprint(value))
	if text == "" {
		return fallback
	}
	return text
}
