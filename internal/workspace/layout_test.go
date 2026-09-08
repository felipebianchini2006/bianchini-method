package workspace

import (
	"path/filepath"
	"testing"
)

func TestLayoutResolvesPlanAndReleaseCandidate(t *testing.T) {
	layout := New(filepath.Join("repo", "."))
	if got, want := layout.PlanDocument("C001-change", "P01-core"), filepath.Join("repo", ".bianchini", "changes", "C001-change", "plans", "P01-core", "PLAN.md"); got != want {
		t.Fatalf("PlanDocument() = %q, want %q", got, want)
	}
	if got, want := layout.PlanResult("C001-change", "P01-core"), filepath.Join("repo", ".bianchini", "changes", "C001-change", "plans", "P01-core", "RESULT.md"); got != want {
		t.Fatalf("PlanResult() = %q, want %q", got, want)
	}
	if got, want := layout.ReleaseCandidateDocument("C001-change", "RC-abc"), filepath.Join("repo", ".bianchini", "changes", "C001-change", "homologation", "RC-abc", "HOMOLOGATION.md"); got != want {
		t.Fatalf("ReleaseCandidateDocument() = %q, want %q", got, want)
	}
}
