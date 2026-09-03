package gokernel

// BuildCommit is replaced at build time with:
// -ldflags "-X github.com/felipebianchini2006/bianchini-method/internal/gokernel.BuildCommit=<sha>"
var BuildCommit = "unknown"

const (
	Version         = "0.6.0"
	ContractVersion = "0.4"
)

var ImplementedSurfaces = []string{
	"validate-state",
	"model.init",
	"model.validate",
	"scope.seal",
	"scope.verify",
	"roadmap.sync",
	"roadmap.next-wave",
	"coherence.check",
	"coherence.approve",
	"impact.analyze",
	"plan.complete",
	"plan.reopen",
	"verify.task",
	"verify.plan",
	"verify.release",
	"verify.review",
	"verify.status",
	"context.pack",
	"context.verify",
	"adapter.render",
	"adapter.install",
	"learn.propose",
	"learn.list",
	"learn.approve",
	"learn.reject",
	"learn.deactivate",
	"debug.start",
	"debug.list",
	"debug.status",
	"debug.resume",
	"debug.checkpoint",
	"debug.finish",
	"migrate.check",
	"migrate.apply",
	"snapshot.create",
	"snapshot.verify",
	"planning-audit",
	"design-audit.seal",
	"design-audit.verify",
	"planning-check.record",
	"change-policy",
	"cycle-close",
	"policy",
	"workspace.create",
	"workspace.check",
	"workspace.locate",
	"workspace.resume",
	"workspace.finish",
	"task-brief",
	"spec-diff",
	"mutation-evidence.verify",
	"report",
	"review-package",
	"checkpoint",
	"proof-map",
	"telemetry.record",
	"telemetry.summary",
	"direct.classify",
	"direct.start",
	"direct.status",
	"direct.checkpoint",
	"direct.finish",
	"direct.reopen",
	"update-bm",
	"status",
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
		Engine:              "go",
		ImplementedSurfaces: surfaces,
		Official:            true,
		Preview:             false,
		Version:             Version,
	}
}
