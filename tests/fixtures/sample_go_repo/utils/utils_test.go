package utils

import "testing"

func TestValidateNumber(t *testing.T) {
	if err := ValidateNumber(42); err != nil {
		t.Errorf("ValidateNumber(42) returned error: %v", err)
	}
}

func TestClamp(t *testing.T) {
	tests := []struct {
		v, min, max, want float64
	}{
		{5, 0, 10, 5},
		{-1, 0, 10, 0},
		{15, 0, 10, 10},
	}
	for _, tc := range tests {
		got := Clamp(tc.v, tc.min, tc.max)
		if got != tc.want {
			t.Errorf("Clamp(%f, %f, %f) = %f; want %f",
				tc.v, tc.min, tc.max, got, tc.want)
		}
	}
}
