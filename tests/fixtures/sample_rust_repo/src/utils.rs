/// Utility functions.

/// Validate that a number is finite and not NaN.
pub fn validate_number(value: f64) {
    if value.is_nan() || value.is_infinite() {
        panic!("Expected a finite number, got {}", value);
    }
}

/// Clamp a value between min and max.
pub fn clamp(value: f64, min: f64, max: f64) -> f64 {
    validate_number(value);
    validate_number(min);
    validate_number(max);
    if value < min {
        min
    } else if value > max {
        max
    } else {
        value
    }
}
