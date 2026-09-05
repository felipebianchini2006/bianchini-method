package gokernel

import (
	"encoding/json"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

// Compact specs reuse scope IDs. Explicit manifests remain authoritative for
// many-to-many mappings. Projection generation is part of planning sync.
func syncPlanningSpecs(workspace methodWorkspace, directory string, coherence map[string]any) error {
	if stateInt(coherence["spec_contract"]) != 1 {
		return nil
	}
	target := filepath.Join(directory, "specs", "expected")
	tree, err := inspectManagedSpecTree(workspace.root, target, false, false)
	if err != nil {
		return err
	}
	if len(tree.files) == 0 {
		return nil
	}
	path := filepath.Join(directory, "specs", "MANIFEST.json")
	content, err := os.ReadFile(path)
	if err != nil && !os.IsNotExist(err) {
		return err
	}
	manifest := map[string]any{}
	if len(content) > 0 {
		manifest, err = decodeStrictJSONObject(content)
		if err != nil {
			return err
		}
	}
	if len(stateArray(manifest["specs"])) == 0 {
		scope, err := os.ReadFile(filepath.Join(directory, "SCOPE.md"))
		if err != nil {
			return err
		}
		ids := map[string]bool{}
		for _, match := range managedScopeHeading.FindAllStringSubmatch(string(scope), -1) {
			ids[match[1]] = true
		}
		paths := make([]string, 0, len(tree.files))
		for path := range tree.files {
			paths = append(paths, path)
		}
		sort.Strings(paths)
		specs := []any{}
		for _, relative := range paths {
			requirements := []any{}
			keys := make([]string, 0, len(tree.requirements[relative]))
			for id := range tree.requirements[relative] {
				keys = append(keys, id)
			}
			sort.Strings(keys)
			for _, id := range keys {
				if !ids[id] {
					return workflowError("SPEC_MANIFEST_REQUIRED", "spec usa IDs diferentes do escopo; declare o mapeamento no MANIFEST.json")
				}
				requirements = append(requirements, map[string]any{"id": id, "scope": []any{id}})
			}
			id := strings.ReplaceAll(strings.TrimSuffix(relative, ".md"), "/", "_")
			specs = append(specs, map[string]any{"id": id, "path": relative, "requirements": requirements})
		}
		manifest = map[string]any{"schema_version": 1, "spec_contract": 1, "specs": specs, "risk_coverage": []any{}}
		encoded, _ := json.MarshalIndent(manifest, "", "  ")
		if err := workspace.atomicWrite(path, append(encoded, '\n')); err != nil {
			return err
		}
	}
	_, rendered, err := deriveManagedSpecDiff(workspace.root, workspace.currentSpec, target, path)
	if err != nil {
		return err
	}
	return workspace.atomicWrite(filepath.Join(directory, "specs", "diff.md"), rendered)
}
