//go:build windows

package gokernel

import (
	"os"
	"syscall"
	"unsafe"
)

var (
	closeKernel32     = syscall.NewLazyDLL("kernel32.dll")
	closeLockFileEx   = closeKernel32.NewProc("LockFileEx")
	closeUnlockFileEx = closeKernel32.NewProc("UnlockFileEx")
)

func lockCloseFile(file *os.File) error {
	overlapped := new(syscall.Overlapped)
	result, _, callErr := closeLockFileEx.Call(file.Fd(), 0x00000002|0x00000001, 0, 1, 0, uintptr(unsafe.Pointer(overlapped)))
	if result == 0 {
		return callErr
	}
	return nil
}

func unlockCloseFile(file *os.File) error {
	overlapped := new(syscall.Overlapped)
	result, _, callErr := closeUnlockFileEx.Call(file.Fd(), 0, 1, 0, uintptr(unsafe.Pointer(overlapped)))
	if result == 0 {
		return callErr
	}
	return nil
}
