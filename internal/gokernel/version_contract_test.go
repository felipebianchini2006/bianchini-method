package gokernel

import (
	"encoding/json"
	"os"
	"path/filepath"
	"reflect"
	"testing"
)

func TestImplementedSurfacesMatchCanonicalRegistryExactly(t *testing.T) {
	content, err := os.ReadFile(filepath.Join("..", "..", "contracts", "cli-surfaces.json"))
	if err != nil {
		t.Fatal(err)
	}
	var contract struct {
		Surfaces []struct {
			ID string `json:"id"`
		} `json:"surfaces"`
	}
	if err := json.Unmarshal(content, &contract); err != nil {
		t.Fatal(err)
	}
	want := make([]string, 0, len(contract.Surfaces))
	for _, surface := range contract.Surfaces {
		want = append(want, surface.ID)
	}
	if !reflect.DeepEqual(ImplementedSurfaces, want) {
		t.Fatalf("implemented surfaces differ from canonical registry\nwant: %#v\n got: %#v", want, ImplementedSurfaces)
	}
}
