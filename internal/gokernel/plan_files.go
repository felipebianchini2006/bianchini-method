package gokernel

import (
	"os"
	"path/filepath"
	"regexp"
	"sort"
)

var planDirectoryPattern = regexp.MustCompile(`^(P[0-9]{2,})(?:-[a-z0-9]+(?:-[a-z0-9]+)*)?$`)

func planFileID(path string) (string, bool) {
	base := filepath.Base(path)
	if base == "PLAN.md" {
		base = filepath.Base(filepath.Dir(path))
	}
	match := planDirectoryPattern.FindStringSubmatch(base)
	if match == nil {
		return "", false
	}
	return match[1], true
}

func planFileForID(directory, identifier string) (string, bool) {
	paths, err := filepath.Glob(filepath.Join(directory, identifier+"*"))
	if err != nil {
		return "", false
	}
	matches := make([]string, 0, 1)
	for _, directory := range paths {
		info, statErr := os.Lstat(directory)
		if statErr != nil || !info.IsDir() || info.Mode()&os.ModeSymlink != 0 {
			continue
		}
		if observed, valid := planFileID(directory); valid && observed == identifier {
			path := filepath.Join(directory, "PLAN.md")
			if planInfo, planErr := os.Lstat(path); planErr == nil && planInfo.Mode().IsRegular() && planInfo.Mode()&os.ModeSymlink == 0 {
				matches = append(matches, path)
			}
		}
	}
	if len(matches) != 1 {
		return "", false
	}
	return matches[0], true
}

func planFiles(directory string) ([]string, error) {
	children, err := os.ReadDir(directory)
	if err != nil {
		return nil, err
	}
	paths := make([]string, 0, len(children))
	for _, child := range children {
		if !child.IsDir() {
			continue
		}
		path := filepath.Join(directory, child.Name(), "PLAN.md")
		if _, valid := planFileID(path); !valid {
			continue
		}
		info, statErr := os.Lstat(path)
		if statErr == nil && info.Mode().IsRegular() && info.Mode()&os.ModeSymlink == 0 {
			paths = append(paths, path)
		}
	}
	sort.Strings(paths)
	return paths, nil
}

func planSlug(path string) string {
	if filepath.Base(path) == "PLAN.md" {
		return filepath.Base(filepath.Dir(path))
	}
	return filepath.Base(path)
}
