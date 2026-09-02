package gokernel

import (
	"path/filepath"
	"regexp"
)

var planFilenamePattern = regexp.MustCompile(`^(P[0-9]{2,})(?:-[a-z0-9]+(?:-[a-z0-9]+)*)?\.md$`)

func planFileID(path string) (string, bool) {
	match := planFilenamePattern.FindStringSubmatch(filepath.Base(path))
	if match == nil {
		return "", false
	}
	return match[1], true
}

func planFileForID(directory, identifier string) (string, bool) {
	paths, err := filepath.Glob(filepath.Join(directory, identifier+"*.md"))
	if err != nil {
		return "", false
	}
	matches := make([]string, 0, 1)
	for _, path := range paths {
		if observed, valid := planFileID(path); valid && observed == identifier {
			matches = append(matches, path)
		}
	}
	if len(matches) != 1 {
		return "", false
	}
	return matches[0], true
}
