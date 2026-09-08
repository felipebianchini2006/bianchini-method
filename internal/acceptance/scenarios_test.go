package acceptance

import (
	"errors"
	"testing"
)

func webScenario() Scenario {
	return Scenario{Plan: "P01", ID: "login", Requirements: []string{"REQ-001"}, Risk: "contract regression", Platform: "web", Profile: "customer", State: "success", Expected: "authenticated dashboard", EvidenceKinds: []string{"observation", "screenshot"}}
}

func TestContractRequiresRequirementAndVisualCoverage(t *testing.T) {
	s := webScenario()
	if err := ValidateContract([]Scenario{s}, []string{"REQ-001"}); err != nil {
		t.Fatal(err)
	}
	for _, mutate := range []func(*Scenario){
		func(s *Scenario) { s.Requirements = []string{"REQ-002"} },
		func(s *Scenario) { s.Profile = "" },
		func(s *Scenario) { s.Risk = "" },
		func(s *Scenario) { s.EvidenceKinds = []string{"observation"} },
		func(s *Scenario) { s.EvidenceKinds = []string{"screenshot"} },
	} {
		bad := webScenario()
		mutate(&bad)
		if err := ValidateContract([]Scenario{bad}, []string{"REQ-001"}); err == nil {
			t.Fatal("incomplete contract accepted")
		}
	}
	if err := ValidateContract([]Scenario{s}, []string{"REQ-001", "REQ-002"}); err == nil {
		t.Fatal("missing requirement accepted")
	}
}

func TestResultsRequireEveryScenarioCurrentCandidateAndEvidence(t *testing.T) {
	s := webScenario()
	valid := Result{Plan: "P01", ID: "login", Result: "passed", Fingerprint: "candidate", Observed: "customer reached dashboard", Evidence: []Evidence{{Kind: "observation", Path: "steps.md", SHA256: "a"}, {Kind: "screenshot", Path: "screen.png", SHA256: "b"}}}
	inspect := func(Evidence) error { return nil }
	if err := ValidateResults([]Scenario{s}, []Result{valid}, "candidate", inspect); err != nil {
		t.Fatal(err)
	}
	for _, mutate := range []func(*Result){
		func(r *Result) { r.Result = "not_run" },
		func(r *Result) { r.Fingerprint = "old" },
		func(r *Result) { r.Evidence = r.Evidence[:1] },
		func(r *Result) { r.ID = "another" },
		func(r *Result) { r.Observed = "" },
	} {
		bad := valid
		mutate(&bad)
		if err := ValidateResults([]Scenario{s}, []Result{bad}, "candidate", inspect); err == nil {
			t.Fatal("incomplete execution accepted")
		}
	}
	if err := ValidateResults([]Scenario{s}, nil, "candidate", inspect); err == nil {
		t.Fatal("omission accepted")
	}
	if err := ValidateResults([]Scenario{s}, []Result{valid, valid}, "candidate", inspect); err == nil {
		t.Fatal("duplicate accepted")
	}
	if err := ValidateResults([]Scenario{s}, []Result{valid}, "candidate", func(Evidence) error { return errors.New("changed bytes") }); err == nil {
		t.Fatal("altered evidence accepted")
	}
}
