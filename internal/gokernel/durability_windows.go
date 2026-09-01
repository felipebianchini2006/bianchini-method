//go:build windows

package gokernel

import (
	"fmt"
	"os"
	"path/filepath"
	"syscall"
	"unsafe"
)

const (
	windowsMoveFileReplaceExisting = 0x1
	windowsMoveFileWriteThrough    = 0x8
)

var (
	durabilityKernel32  = syscall.NewLazyDLL("kernel32.dll")
	durabilityMoveFileW = durabilityKernel32.NewProc("MoveFileExW")
)

func windowsMoveFlags(replace bool) uint32 {
	flags := uint32(windowsMoveFileWriteThrough)
	if replace {
		flags |= windowsMoveFileReplaceExisting
	}
	return flags
}

func windowsMovePath(source, target string, replace bool) error {
	from, err := syscall.UTF16PtrFromString(source)
	if err != nil {
		return err
	}
	to, err := syscall.UTF16PtrFromString(target)
	if err != nil {
		return err
	}
	result, _, callErr := durabilityMoveFileW.Call(
		uintptr(unsafe.Pointer(from)),
		uintptr(unsafe.Pointer(to)),
		uintptr(windowsMoveFlags(replace)),
	)
	if result == 0 {
		if callErr != syscall.Errno(0) {
			return callErr
		}
		return syscall.EINVAL
	}
	return nil
}

func replacePath(source, target string) error {
	return windowsMovePath(source, target, true)
}

// Windows não documenta FlushFileBuffers para handles de diretório. A barreira
// durável é aplicada nos publishes e tombstones por MoveFileExW WRITE_THROUGH.
func syncDirectory(path string) error {
	info, err := os.Stat(path)
	if err != nil {
		return err
	}
	if !info.IsDir() {
		return fmt.Errorf("não é diretório: %s", path)
	}
	return nil
}

func removeFileDurably(path string) error {
	return windowsRemoveDurably(path, os.Remove)
}

func removeAllDurably(path string) error {
	return windowsRemoveDurably(path, os.RemoveAll)
}

func windowsRemoveDurably(path string, remove func(string) error) error {
	info, err := os.Lstat(path)
	if os.IsNotExist(err) {
		return nil
	}
	if err != nil {
		return err
	}
	if info.Mode()&os.ModeSymlink != 0 {
		return fmt.Errorf("remoção durável recusou symlink: %s", path)
	}
	temporary, err := os.CreateTemp(filepath.Dir(path), "."+filepath.Base(path)+".bianchini-delete.*")
	if err != nil {
		return err
	}
	tombstone := temporary.Name()
	if err := temporary.Close(); err != nil {
		return err
	}
	if err := os.Remove(tombstone); err != nil {
		return err
	}
	if err := windowsMovePath(path, tombstone, false); err != nil {
		return err
	}
	// A ausência da origem já foi publicada com WRITE_THROUGH. A limpeza do
	// tombstone não participa do commit e nunca remove nomes não comprovados.
	_ = remove(tombstone)
	return nil
}
