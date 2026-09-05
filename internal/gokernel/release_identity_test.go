package gokernel

import (
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestDeploymentIdentityObservesRunningTarget(t *testing.T) {
	version := strings.Repeat("a", 64)
	healthy := true
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/health" || !healthy {
			w.WriteHeader(http.StatusServiceUnavailable)
			return
		}
		fmt.Fprintf(w, `{"version":%q}`, version)
	}))
	defer server.Close()
	target := server.URL + "/health"
	if got, err := releaseArtifactIdentity(t.TempDir(), "deployment", target, version); err != nil || got != version {
		t.Fatalf("valid target: %s %v", got, err)
	}
	previous := version
	version = strings.Repeat("b", 64)
	if _, err := releaseArtifactIdentity(t.TempDir(), "deployment", target, previous); err == nil {
		t.Fatal("changed deployment accepted")
	}
	healthy = false
	if _, err := releaseArtifactIdentity(t.TempDir(), "deployment", target, version); err == nil {
		t.Fatal("unhealthy target accepted")
	}
}

func TestHomologationRejectsFictitiousResolution(t *testing.T) {
	h := map[string]any{"findings": []any{map[string]any{"severity": "critical", "status": "resolved", "resolution_evidence": "does-not-exist", "resolution_sha256": strings.Repeat("a", 64)}}, "gates": []any{map[string]any{"proof_id": "p1", "result": "passed"}}}
	if err := validateHomologationGates(t.TempDir(), h, []string{"p1"}); err == nil {
		t.Fatal("fictitious resolution accepted")
	}
}
