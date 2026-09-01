//go:build windows

package gokernel

func setTestUmask(int) (func(), bool) {
	return func() {}, false
}
