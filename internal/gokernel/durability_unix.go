//go:build !windows

package gokernel

import (
	"os"
	"path/filepath"
)

func replacePath(source, target string) error {
	return os.Rename(source, target)
}

func removeAllDurably(path string) error {
	if err := os.RemoveAll(path); err != nil {
		return err
	}
	return syncDirectory(filepath.Dir(path))
}

func removeFileDurably(path string) error {
	err := os.Remove(path)
	if os.IsNotExist(err) {
		return syncDirectory(filepath.Dir(path))
	}
	if err != nil {
		return err
	}
	return syncDirectory(filepath.Dir(path))
}

func syncDirectory(path string) error {
	directory, err := os.Open(path)
	if err != nil {
		return err
	}
	defer directory.Close()
	return directory.Sync()
}
