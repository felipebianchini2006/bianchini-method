package gokernel

import (
	"bytes"
	"encoding/json"
	"fmt"
	"math"
	"regexp"
)

var (
	jsonFencePattern = regexp.MustCompile("(?is)```json\\s*(.*?)\\s*```")
	hexDigestPattern = regexp.MustCompile(`^[0-9a-f]{64}$`)
)

func decodeJSONAny(content []byte) (any, error) {
	var value any
	decoder := json.NewDecoder(bytes.NewReader(content))
	decoder.UseNumber()
	if err := decoder.Decode(&value); err != nil {
		return nil, err
	}
	return value, nil
}

func decodeJSONObject(content []byte) (map[string]any, error) {
	value, err := decodeJSONAny(content)
	if err != nil {
		return nil, err
	}
	object, ok := value.(map[string]any)
	if !ok {
		return nil, fmt.Errorf("expected object")
	}
	return object, nil
}

func jsonErrorLine(content []byte, err error) int {
	offset := int64(1)
	if syntax, ok := err.(*json.SyntaxError); ok {
		offset = syntax.Offset
	}
	if offset < 1 {
		offset = 1
	}
	if offset > int64(len(content))+1 {
		offset = int64(len(content)) + 1
	}
	return bytesLine(content[:offset-1])
}

func bytesLine(prefix []byte) int {
	line := 1
	for _, value := range prefix {
		if value == '\n' {
			line++
		}
	}
	return line
}

func stateObject(value any) map[string]any {
	object, _ := value.(map[string]any)
	if object == nil {
		return map[string]any{}
	}
	return object
}

func stateArray(value any) []any {
	array, _ := value.([]any)
	return array
}

func stateString(value any) string {
	text, _ := value.(string)
	return text
}

func stateBool(value any) bool {
	boolean, _ := value.(bool)
	return boolean
}

func stateInt(value any) int {
	switch number := value.(type) {
	case int:
		return number
	case int64:
		return int(number)
	case float64:
		if math.IsNaN(number) || math.IsInf(number, 0) || math.Trunc(number) != number || number < math.MinInt64 || number > math.MaxInt64 {
			return 0
		}
		return int(number)
	case json.Number:
		parsed, err := number.Int64()
		if err == nil {
			return int(parsed)
		}
	}
	return 0
}

func stateStringSlice(value any) []string {
	array := stateArray(value)
	result := make([]string, 0, len(array))
	for _, item := range array {
		if text, ok := item.(string); ok {
			result = append(result, text)
		}
	}
	return result
}

func stringSet(values []string) map[string]bool {
	result := make(map[string]bool, len(values))
	for _, value := range values {
		result[value] = true
	}
	return result
}

func hasDuplicates(values []string) bool {
	return len(stringSet(values)) != len(values)
}

func stateError(message string, exitCode int) error {
	return &commandError{message: message, exitCode: exitCode}
}
