package calculator

import "testing"

func TestAdd(t *testing.T) {
	got := Add(1, 2)
	if got != 3 {
		t.Errorf("Add(1, 2) = %f; want 3", got)
	}
}

func TestSubtract(t *testing.T) {
	got := Subtract(5, 3)
	if got != 2 {
		t.Errorf("Subtract(5, 3) = %f; want 2", got)
	}
}
