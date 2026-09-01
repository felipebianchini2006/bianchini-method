package gokernel

import (
	"bytes"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"unicode/utf8"
)

const (
	adapterStartMarker = "<!-- bianchini-method:host-adapter:start -->"
	adapterEndMarker   = "<!-- bianchini-method:host-adapter:end -->"
)

type adapterDefinition struct {
	target       string
	capabilities []string
	rules        []string
}

var adapterCommonRules = []string{
	"Consuma somente o context pack validado para a unidade; não releia o contrato completo quando o pack estiver válido.",
	"Exija a mesma `pack_identity`, o mesmo `pack_digest` e o mesmo `package_digest` usados pelo CLI antes de executar ou revisar a unidade.",
	"Trate o CLI `bm` como autoridade para schema, digest, DAG, impacto, evidência e gates.",
	"Peça a próxima onda ao CLI; o host agenda agentes, modelos e paralelismo sem gravar decisões de host no kernel.",
	"Preserve o fluxo público e nunca acesse o namespace estrangeiro `.planning/`.",
}

var adapterDefinitions = map[string]adapterDefinition{
	"generic": {
		target: "AGENTS.md", capabilities: []string{"AGENTS.md", "Agent Skills"},
		rules: []string{
			"Descubra e carregue as Agent Skills declaradas pelo projeto antes de executar uma unidade.",
			"Execute cada unidade com o pack recebido e devolva evidência ao CLI sem reimplementar gates.",
		},
	},
	"codex": {
		target: "AGENTS.md", capabilities: []string{"AGENTS.md", "Agent Skills", "subagents", "commentary updates"},
		rules: []string{
			"Faça o menor diff compatível que satisfaça a unidade e seus testes.",
			"Não crie abstrações especulativas; extraia apenas quando houver variação real comprovada.",
			"Use subagentes apenas para frentes independentes, com ownership fechado e integração pelo executor principal.",
		},
	},
	"claude-compatible": {
		target: "CLAUDE.md", capabilities: []string{"CLAUDE.md", "Agent Skills", "subagents"},
		rules: []string{
			"Carregue as instruções compatíveis de `CLAUDE.md` e as Agent Skills declaradas pelo projeto.",
			"Use subagentes e hooks do host somente para executar a onda recebida, sem decidir gates no prompt.",
		},
	},
}

func runAdapter(args []string) (any, error) {
	if len(args) == 0 {
		return nil, argparseError("the following arguments are required: action")
	}
	action := args[0]
	if !oneOf(action, "render", "install") {
		return nil, argparseError(fmt.Sprintf("argument action: invalid choice: '%s'", action))
	}
	flags, err := parseFlags(args[1:], map[string]bool{"--host": true, "--repo": true}, map[string]bool{"--overwrite": true})
	if err != nil {
		return nil, err
	}
	host := lastValue(flags, "--host")
	if host == "" {
		return nil, argparseError("the following arguments are required: --host")
	}
	if _, ok := adapterDefinitions[host]; !ok {
		return nil, argparseError("argument --host: invalid choice: '" + host + "'")
	}
	content := renderAdapter(host)
	if action == "render" {
		return map[string]any{"host": host, "content": content, "digest": sha256Bytes([]byte(content))}, nil
	}
	repo := lastValue(flags, "--repo")
	if repo == "" {
		repo, err = os.Getwd()
		if err != nil {
			return nil, adapterError("HOST_ADAPTER_PATH_INVALID", "raiz do repositório ausente")
		}
	}
	return installAdapter(repo, host, flags.booleans["--overwrite"])
}

func renderAdapter(host string) string {
	definition := adapterDefinitions[host]
	capabilities := make([]string, len(definition.capabilities))
	for index, capability := range definition.capabilities {
		capabilities[index] = "`" + capability + "`"
	}
	lines := []string{
		adapterStartMarker,
		"## Bianchini Method — adapter de host",
		"",
		"- Host: `" + host + "`",
		"- Arquivo: `" + definition.target + "`",
		"- Capabilities: " + strings.Join(capabilities, ", "),
		"",
		"### Contrato comum",
		"",
	}
	for _, rule := range adapterCommonRules {
		lines = append(lines, "- "+rule)
	}
	lines = append(lines, "", "### Política do host", "")
	for _, rule := range definition.rules {
		lines = append(lines, "- "+rule)
	}
	lines = append(lines, adapterEndMarker, "")
	return strings.Join(lines, "\n")
}

func installAdapter(repo, host string, overwrite bool) (map[string]any, error) {
	root, err := safeRoot(repo)
	if err != nil {
		return nil, adapterError("HOST_ADAPTER_PATH_INVALID", strings.TrimPrefix(err.Error(), "PATH_SAFETY: "))
	}
	definition := adapterDefinitions[host]
	target := filepath.Join(root, definition.target)
	info, statErr := os.Lstat(target)
	if statErr == nil {
		if info.Mode()&os.ModeSymlink != 0 {
			return nil, adapterError("HOST_ADAPTER_SYMLINK", "target não pode ser symlink: "+definition.target)
		}
		if !info.Mode().IsRegular() {
			return nil, adapterError("HOST_ADAPTER_PATH_INVALID", "target não é arquivo: "+definition.target)
		}
	} else if !os.IsNotExist(statErr) {
		return nil, adapterError("HOST_ADAPTER_PATH_INVALID", "target inválido: "+definition.target)
	}
	existing := []byte{}
	if statErr == nil {
		existing, err = os.ReadFile(target)
		if err != nil {
			return nil, adapterError("HOST_ADAPTER_CONTENT_INVALID", definition.target+" não pôde ser lido")
		}
		if !validUTF8Text(existing) {
			return nil, adapterError("HOST_ADAPTER_CONTENT_INVALID", definition.target+" não é UTF-8")
		}
	}
	block := []byte(renderAdapter(host))
	start, end, found, err := managedAdapterBounds(existing)
	if err != nil {
		return nil, err
	}
	var desired []byte
	if !found {
		desired = appendAdapterBlock(existing, block)
	} else if bytes.Equal(existing[start:end], block) {
		desired = existing
	} else if !overwrite {
		return nil, adapterError("HOST_ADAPTER_OVERWRITE_REQUIRED", definition.target+" já possui adapter gerenciado divergente")
	} else {
		desired = make([]byte, 0, len(existing)-end+start+len(block))
		desired = append(desired, existing[:start]...)
		desired = append(desired, block...)
		desired = append(desired, existing[end:]...)
	}
	changed := !bytes.Equal(desired, existing)
	if changed {
		if err := atomicWrite(target, desired); err != nil {
			return nil, adapterError("HOST_ADAPTER_WRITE_FAILED", "falha ao gravar "+definition.target)
		}
	}
	status := "unchanged"
	if changed {
		status = "installed"
	}
	return map[string]any{
		"schema_version": 1, "status": status, "host": host,
		"target": definition.target, "changed": changed, "digest": sha256Bytes(block),
	}, nil
}

func managedAdapterBounds(content []byte) (int, int, bool, error) {
	startMarker := []byte(adapterStartMarker)
	endMarker := []byte(adapterEndMarker)
	startCount := bytes.Count(content, startMarker)
	endCount := bytes.Count(content, endMarker)
	if startCount == 0 && endCount == 0 {
		return 0, 0, false, nil
	}
	if startCount != 1 || endCount != 1 {
		return 0, 0, false, adapterError("HOST_ADAPTER_MARKERS_INVALID", "marcadores ausentes ou duplicados")
	}
	start := bytes.Index(content, startMarker)
	endStart := bytes.Index(content, endMarker)
	if endStart < start {
		return 0, 0, false, adapterError("HOST_ADAPTER_MARKERS_INVALID", "marcadores fora de ordem")
	}
	end := endStart + len(endMarker)
	if bytes.HasPrefix(content[end:], []byte("\r\n")) {
		end += 2
	} else if bytes.HasPrefix(content[end:], []byte("\n")) {
		end++
	}
	return start, end, true, nil
}

func appendAdapterBlock(existing, block []byte) []byte {
	if len(existing) == 0 {
		return append([]byte(nil), block...)
	}
	separator := []byte("\n\n")
	if bytes.HasSuffix(existing, []byte("\n\n")) {
		separator = nil
	} else if bytes.HasSuffix(existing, []byte("\n")) {
		separator = []byte("\n")
	}
	result := make([]byte, 0, len(existing)+len(separator)+len(block))
	result = append(result, existing...)
	result = append(result, separator...)
	result = append(result, block...)
	return result
}

func adapterError(code, message string) error {
	return &commandError{message: code + ": " + message, exitCode: 3}
}

func validUTF8Text(content []byte) bool {
	return utf8.Valid(content) && bytes.IndexByte(content, 0) < 0
}
