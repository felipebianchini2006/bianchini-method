package gokernel

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

func validateRelativePath(path, label string) error {
	if path == "" {
		return domainError("PATH_SAFETY", label+" vazio")
	}
	if strings.Contains(path, "\\") {
		return domainError("PATH_SAFETY", label+" contém barra invertida")
	}
	if filepath.IsAbs(path) {
		return domainError("PATH_SAFETY", label+" deve ser relativo")
	}
	for _, part := range strings.Split(filepath.ToSlash(path), "/") {
		if part == "" || part == "." || part == ".." {
			return domainError("PATH_SAFETY", label+" contém traversal")
		}
		if strings.EqualFold(part, ".planning") {
			return domainError("PATH_SAFETY", label+" usa namespace estrangeiro")
		}
	}
	if filepath.ToSlash(filepath.Clean(path)) != path {
		return domainError("PATH_SAFETY", label+" não está normalizado")
	}
	return nil
}

func rejectForeignNamespace(path, label string) error {
	if path == "" {
		return domainError("PATH_SAFETY", label+" vazio")
	}
	if strings.Contains(path, "\\") {
		return domainError("PATH_SAFETY", label+" contém barra invertida")
	}
	for _, part := range strings.Split(filepath.ToSlash(path), "/") {
		if strings.EqualFold(part, ".planning") {
			return domainError("PATH_SAFETY", label+" usa namespace estrangeiro")
		}
	}
	return nil
}

func safeRoot(root string) (string, error) {
	if err := rejectForeignNamespace(root, "root"); err != nil {
		return "", err
	}
	absolute, err := filepath.Abs(root)
	if err != nil {
		return "", domainError("PATH_SAFETY", "root inválido")
	}
	info, err := os.Lstat(absolute)
	if err != nil {
		return "", domainError("PATH_SAFETY", "root ausente")
	}
	if info.Mode()&os.ModeSymlink != 0 || !info.IsDir() {
		return "", domainError("PATH_SAFETY", "root deve ser diretório real")
	}
	return filepath.Clean(absolute), nil
}

func confinedPath(root, candidate, label string, mustExist bool) (string, error) {
	if err := rejectForeignNamespace(candidate, label); err != nil {
		return "", err
	}
	if strings.Contains(filepath.ToSlash(candidate), "/../") || strings.HasSuffix(candidate, "/..") {
		return "", domainError("PATH_SAFETY", label+" contém traversal")
	}
	joined := candidate
	if !filepath.IsAbs(candidate) {
		joined = filepath.Join(root, candidate)
	}
	absolute, err := filepath.Abs(joined)
	if err != nil {
		return "", domainError("PATH_SAFETY", label+" inválido")
	}
	absolute = filepath.Clean(absolute)
	relative, err := filepath.Rel(root, absolute)
	if err != nil || relative == ".." || strings.HasPrefix(relative, ".."+string(filepath.Separator)) || filepath.IsAbs(relative) {
		return "", domainError("PATH_SAFETY", label+" fora da raiz")
	}

	if !mustExist {
		if info, statErr := os.Lstat(absolute); statErr == nil {
			if info.Mode()&os.ModeSymlink != 0 {
				return "", domainError("PATH_SAFETY", label+" não aceita symlink")
			}
			if !info.Mode().IsRegular() {
				return "", domainError("PATH_SAFETY", label+" deve ser arquivo regular")
			}
		} else if !os.IsNotExist(statErr) {
			return "", domainError("PATH_SAFETY", label+" inválido")
		}
	}
	probe := absolute
	if !mustExist {
		probe = filepath.Dir(absolute)
	}
	for {
		info, statErr := os.Lstat(probe)
		if statErr == nil {
			if info.Mode()&os.ModeSymlink != 0 {
				return "", domainError("PATH_SAFETY", label+" não aceita symlink")
			}
		} else if !os.IsNotExist(statErr) || mustExist {
			return "", domainError("PATH_SAFETY", fmt.Sprintf("%s ausente", label))
		}
		if probe == root {
			break
		}
		parent := filepath.Dir(probe)
		if parent == probe || len(parent) < len(root) {
			return "", domainError("PATH_SAFETY", label+" fora da raiz")
		}
		probe = parent
	}
	if mustExist {
		info, statErr := os.Lstat(absolute)
		if statErr != nil || !info.Mode().IsRegular() || info.Mode()&os.ModeSymlink != 0 {
			return "", domainError("PATH_SAFETY", label+" deve ser arquivo regular")
		}
	}
	return absolute, nil
}

func safeStandaloneFile(path, label string) (string, error) {
	if err := rejectForeignNamespace(path, label); err != nil {
		return "", err
	}
	absolute, err := filepath.Abs(path)
	if err != nil {
		return "", domainError("PATH_SAFETY", label+" inválido")
	}
	info, err := os.Lstat(absolute)
	if err != nil || !info.Mode().IsRegular() {
		return "", domainError("PATH_SAFETY", label+" deve ser arquivo regular")
	}
	if info.Mode()&os.ModeSymlink != 0 {
		return "", domainError("PATH_SAFETY", label+" não aceita symlink")
	}
	return absolute, nil
}
