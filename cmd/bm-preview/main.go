package main

import (
	"os"

	"github.com/felipebianchini2006/bianchini-method/internal/gokernel"
)

func main() {
	os.Exit(gokernel.Run(os.Args[1:], os.Stdout, os.Stderr))
}
