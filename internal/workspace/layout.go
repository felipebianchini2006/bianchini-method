// Package workspace defines the single physical layout used by the Bianchini method.
package workspace

import "path/filepath"

// Layout resolves method documents below one repository root.
type Layout struct {
	Root string
}

func New(root string) Layout { return Layout{Root: filepath.Clean(root)} }

func (l Layout) Dir() string                 { return filepath.Join(l.Root, ".bianchini") }
func (l Layout) State() string               { return filepath.Join(l.Dir(), "STATE.md") }
func (l Layout) Runtime() string             { return filepath.Join(l.Dir(), ".runtime") }
func (l Layout) Current() string             { return filepath.Join(l.Dir(), "current") }
func (l Layout) CurrentArchitecture() string { return filepath.Join(l.Current(), "ARCHITECTURE.md") }
func (l Layout) CurrentModel() string        { return filepath.Join(l.Current(), "SYSTEM_MODEL.md") }
func (l Layout) CurrentSpecs() string        { return filepath.Join(l.Current(), "specs") }
func (l Layout) Changes() string             { return filepath.Join(l.Dir(), "changes") }
func (l Layout) Change(change string) string { return filepath.Join(l.Changes(), change) }
func (l Layout) Archive() string             { return filepath.Join(l.Dir(), "archive") }
func (l Layout) ArchivedChange(change string) string {
	return filepath.Join(l.Archive(), change)
}

func (l Layout) ChangeScope(change string) string { return filepath.Join(l.Change(change), "SCOPE.md") }
func (l Layout) ChangeResearch(change string) string {
	return filepath.Join(l.Change(change), "RESEARCH.md")
}
func (l Layout) ChangeArchitecture(change string) string {
	return filepath.Join(l.Change(change), "ARCHITECTURE.md")
}
func (l Layout) ChangeModel(change string) string {
	return filepath.Join(l.Change(change), "SYSTEM_MODEL.md")
}
func (l Layout) ChangeRoadmap(change string) string {
	return filepath.Join(l.Change(change), "ROADMAP.md")
}
func (l Layout) ChangeSpecs(change string) string { return filepath.Join(l.Change(change), "specs") }
func (l Layout) ChangeResults(change string) string {
	return filepath.Join(l.Change(change), "results")
}
func (l Layout) ChangeReleaseMetadata(change string) string {
	return filepath.Join(l.ChangeResults(change), "RELEASE.md")
}

func (l Layout) Plans(change string) string { return filepath.Join(l.Change(change), "plans") }
func (l Layout) Plan(change, slug string) string {
	return filepath.Join(l.Plans(change), slug)
}
func (l Layout) PlanDocument(change, slug string) string {
	return filepath.Join(l.Plan(change, slug), "PLAN.md")
}
func (l Layout) PlanResult(change, slug string) string {
	return filepath.Join(l.Plan(change, slug), "RESULT.md")
}
func (l Layout) PlanEvidence(change, slug string) string {
	return filepath.Join(l.Plan(change, slug), "evidence")
}

func (l Layout) ChangeHomologation(change string) string {
	return filepath.Join(l.Change(change), "homologation")
}
func (l Layout) ReleaseCandidate(change, release string) string {
	return filepath.Join(l.ChangeHomologation(change), release)
}
func (l Layout) ReleaseCandidateDocument(change, release string) string {
	return filepath.Join(l.ReleaseCandidate(change, release), "HOMOLOGATION.md")
}
func (l Layout) ReleaseCandidateEvidence(change, release string) string {
	return filepath.Join(l.ReleaseCandidate(change, release), "evidence")
}
func (l Layout) ReleaseCandidateDelivery(change, release string) string {
	return filepath.Join(l.ReleaseCandidate(change, release), "delivery")
}
