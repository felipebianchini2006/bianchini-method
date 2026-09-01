package gokernel

// BuildCommit is replaced at build time with:
// -ldflags "-X github.com/felipebianchini2006/bianchini-method/internal/gokernel.BuildCommit=<sha>"
var BuildCommit = "unknown"

const (
	Version         = "0.4.7-preview"
	ContractVersion = "0.4"
)

var ImplementedSurfaces = []string{
	"validate-state",
	"model:init",
	"model:validate",
	"scope:seal",
	"scope:verify",
	"roadmap:sync",
	"roadmap:next-wave",
	"change-policy",
	"policy",
	"adapter:render",
	"adapter:install",
	"snapshot:create",
	"snapshot:verify",
	"planning-audit",
	"design-audit:seal",
	"design-audit:verify",
	"planning-check:record",
	"direct:classify",
	"direct:start",
	"direct:status",
	"direct:checkpoint",
	"direct:finish",
	"direct:reopen",
	"debug:start",
	"debug:list",
	"debug:status",
	"debug:resume",
	"debug:checkpoint",
	"debug:finish",
	"learn:propose",
	"learn:list",
	"learn:approve",
	"learn:reject",
	"learn:deactivate",
	"migrate:check",
	"migrate:apply",
	"spec-diff:file",
	"status:legacy",
	"workspace:create-parser",
}

type VersionMetadata struct {
	BuildCommit         string   `json:"build_commit"`
	ContractVersion     string   `json:"contract_version"`
	Engine              string   `json:"engine"`
	ImplementedSurfaces []string `json:"implemented_surfaces"`
	Official            bool     `json:"official"`
	Preview             bool     `json:"preview"`
	Version             string   `json:"version"`
}

func versionMetadata() VersionMetadata {
	surfaces := append([]string(nil), ImplementedSurfaces...)
	return VersionMetadata{
		BuildCommit:         BuildCommit,
		ContractVersion:     ContractVersion,
		Engine:              "go-preview",
		ImplementedSurfaces: surfaces,
		Official:            false,
		Preview:             true,
		Version:             Version,
	}
}
