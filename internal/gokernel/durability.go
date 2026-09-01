package gokernel

import (
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

type directorySync func(string) error

func syncRenameDirectories(source, target string, syncDir directorySync) error {
	directories := []string{filepath.Dir(source)}
	if other := filepath.Dir(target); filepath.Clean(other) != filepath.Clean(directories[0]) {
		directories = append(directories, other)
	}
	for _, directory := range directories {
		if err := syncDir(directory); err != nil {
			return err
		}
	}
	return nil
}

func durableRename(source, target string) error {
	if err := replacePath(source, target); err != nil {
		return err
	}
	return syncRenameDirectories(source, target, syncDirectory)
}

func durableRemoveAll(path string) error {
	return removeAllDurably(path)
}

func durableRemoveFile(path string) error {
	return removeFileDurably(path)
}

func syncTreeDurably(root string) error {
	directories := []string{}
	err := filepath.WalkDir(root, func(path string, entry os.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		info, err := os.Lstat(path)
		if err != nil || info.Mode()&os.ModeSymlink != 0 {
			return fmt.Errorf("árvore não sincronizável: %s", path)
		}
		if info.IsDir() {
			directories = append(directories, path)
			return nil
		}
		if !info.Mode().IsRegular() {
			return fmt.Errorf("arquivo não sincronizável: %s", path)
		}
		file, err := openFileForSync(path)
		if err != nil {
			return err
		}
		syncErr := file.Sync()
		closeErr := file.Close()
		if syncErr != nil {
			return syncErr
		}
		return closeErr
	})
	if err != nil {
		return err
	}
	sort.Slice(directories, func(i, j int) bool {
		left := strings.Count(filepath.Clean(directories[i]), string(filepath.Separator))
		right := strings.Count(filepath.Clean(directories[j]), string(filepath.Separator))
		return left > right
	})
	for _, directory := range directories {
		if err := syncDirectory(directory); err != nil {
			return err
		}
	}
	return syncDirectory(filepath.Dir(root))
}
