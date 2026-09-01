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
	"change-policy",
	"policy",
	"adapter:render",
	"adapter:install",
	"direct:classify",
	"direct:reopen",
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
