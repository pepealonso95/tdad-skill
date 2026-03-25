/// Validate that a value is a finite number.
void validateNumber(num value) {
  if (value.isNaN || value.isInfinite) {
    throw ArgumentError('Expected a finite number, got $value');
  }
}

/// Clamp a value between min and max.
num clamp(num value, num min, num max) {
  validateNumber(value);
  validateNumber(min);
  validateNumber(max);
  if (value < min) return min;
  if (value > max) return max;
  return value;
}
