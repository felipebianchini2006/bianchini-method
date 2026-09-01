//go:build !windows

package gokernel

import "syscall"

func setTestUmask(mask int) (func(), bool) {
	previous := syscall.Umask(mask)
	return func() { syscall.Umask(previous) }, true
}
