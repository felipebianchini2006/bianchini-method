package gokernel

import (
	_ "embed"
	"encoding/json"
	"strings"
)

//go:embed assets/cli-help.json
var staticCLIHelpAsset []byte

var staticCLIHelpByPath, staticCLIValueFlags, staticCLICommandChoices = loadStaticCLIHelp()

func loadStaticCLIHelp() (map[string]string, map[string]map[string]bool, []string) {
	var document struct {
		SchemaVersion  int                 `json:"schema_version"`
		CommandChoices []string            `json:"command_choices"`
		Help           map[string]string   `json:"help"`
		ValueFlags     map[string][]string `json:"value_flags"`
	}
	if err := json.Unmarshal(staticCLIHelpAsset, &document); err != nil {
		panic("invalid embedded CLI help: " + err.Error())
	}
	if document.SchemaVersion != 1 || len(document.CommandChoices) == 0 || document.Help == nil || document.ValueFlags == nil {
		panic("invalid embedded CLI help schema")
	}
	valueFlags := make(map[string]map[string]bool, len(document.ValueFlags))
	for command, names := range document.ValueFlags {
		valueFlags[command] = flagSet(names...)
	}
	return document.Help, valueFlags, document.CommandChoices
}

// staticCLIHelp returns terminal help only for canonical command paths. Run
// calls it before normal dispatch, so no Python process is needed at runtime.
func staticCLIHelp(args []string) (string, bool) {
	helpIndex := -1
	for index, arg := range args {
		if arg == "--help" || arg == "-h" {
			helpIndex = index
			break
		}
	}
	if helpIndex < 0 {
		return "", false
	}
	if helpIndex == 0 {
		text, ok := staticCLIHelpByPath[""]
		return text, ok
	}
	command := args[0]
	valueFlags, commandExists := staticCLIValueFlags[command]
	if !commandExists {
		if strings.HasPrefix(command, "-") {
			text, ok := staticCLIHelpByPath[""]
			return text, ok
		}
		return "", false
	}
	for index := 1; index < helpIndex; index++ {
		if args[index] == "--" {
			return "", false
		}
		requested, _, equals := strings.Cut(args[index], "=")
		name, kind, matches := resolveFlag(requested, valueFlags, flagSet("--help", "-h"))
		if len(matches) > 1 || kind != "value" || equals {
			continue
		}
		if index+1 == helpIndex {
			return "", false
		}
		if name != "" {
			index++
		}
	}
	text, ok := staticCLIHelpByPath[command]
	return text, ok
}
