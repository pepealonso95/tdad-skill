// Package utils provides helper functions for numeric validation.
package utils

import (
	"fmt"
	"math"
)

// ValidateNumber checks that the value is finite.
func ValidateNumber(v float64) error {
	if math.IsNaN(v) || math.IsInf(v, 0) {
		return fmt.Errorf("invalid number: %f", v)
	}
	return nil
}

// Clamp restricts v to the range [min, max].
func Clamp(v, min, max float64) float64 {
	if err := ValidateNumber(v); err != nil {
		return min
	}
	if v < min {
		return min
	}
	if v > max {
		return max
	}
	return v
}
