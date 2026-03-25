// Package calculator provides basic arithmetic operations.
package calculator

import "fmt"

// Add returns the sum of a and b.
func Add(a, b float64) float64 {
	return a + b
}

// Subtract returns the difference of a and b.
func Subtract(a, b float64) float64 {
	return a - b
}

// Calculator holds state for chained operations.
type Calculator struct {
	LastResult float64
}

// Compute performs the named operation and stores the result.
func (c *Calculator) Compute(op string, a, b float64) (float64, error) {
	switch op {
	case "add":
		c.LastResult = Add(a, b)
	case "subtract":
		c.LastResult = Subtract(a, b)
	default:
		return 0, fmt.Errorf("unknown operation: %s", op)
	}
	return c.LastResult, nil
}
