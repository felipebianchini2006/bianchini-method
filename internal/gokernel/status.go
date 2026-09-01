package gokernel

import (
	"bytes"
	"os"
	"regexp"
	"unicode/utf8"
)

var methodVersionOne = regexp.MustCompile(`(?m)^method_version:\s*1\s*$`)

func runStatus(args []string) (any, error) {
	if len(args) == 0 {
		return nil, argparseError("the following arguments are required: state")
	}
	state := args[0]
	format := "text"
	for index := 1; index < len(args); index++ {
		switch args[index] {
		case "--format":
			if index+1 >= len(args) {
				return nil, argparseError("argument --format: expected one argument")
			}
			index++
			format = args[index]
		default:
			return nil, argparseError("unrecognized arguments: " + args[index])
		}
	}
	if format != "json" && format != "text" {
		return nil, argparseError("argument --format: invalid choice: '" + format + "'")
	}
	path, err := safeStandaloneFile(state, "status")
	if err != nil {
		return nil, err
	}
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, domainError("STATUS_ERROR", "falha ao ler estado")
	}
	if len(data) == 0 || !utf8.Valid(data) || bytes.IndexByte(data, 0) >= 0 {
		return nil, domainError("STATUS_ERROR", "estado deve ser UTF-8 textual")
	}
	if !methodVersionOne.Match(data) {
		return nil, domainError("NOT_IMPLEMENTED", "status não legado não está disponível no backend go-preview")
	}
	if format == "json" {
		return map[string]any{
			"implicit_legacy": false,
			"method_mode":     "legacy-superpowers",
			"method_version":  1,
			"mode":            "legacy-superpowers",
			"status":          "legacy",
		}, nil
	}
	return "# Status do projeto\n\n- Método: v1 legado (Superpowers)\n- Marcador implícito: não\n", nil
}
