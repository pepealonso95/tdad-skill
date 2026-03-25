/// Calculator module — mirrors the Python sample_repo for cross-language testing.

use crate::utils::validate_number;

/// Add two numbers.
pub fn add(a: f64, b: f64) -> f64 {
    validate_number(a);
    validate_number(b);
    a + b
}

pub fn subtract(a: f64, b: f64) -> f64 {
    a - b
}

pub fn multiply(a: f64, b: f64) -> f64 {
    a * b
}

pub fn divide(a: f64, b: f64) -> Result<f64, String> {
    if b == 0.0 {
        return Err("Division by zero".to_string());
    }
    Ok(a / b)
}

pub struct Calculator {
    last_result: f64,
}

impl Calculator {
    pub fn new() -> Self {
        Calculator { last_result: 0.0 }
    }

    pub fn compute(&mut self, op: &str, a: f64, b: f64) -> f64 {
        self.last_result = match op {
            "add" => add(a, b),
            "subtract" => subtract(a, b),
            _ => panic!("Unknown operation: {}", op),
        };
        self.last_result
    }

    pub fn get_last_result(&self) -> f64 {
        self.last_result
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_add() {
        assert_eq!(add(1.0, 2.0), 3.0);
    }

    #[test]
    fn test_subtract() {
        assert_eq!(subtract(5.0, 3.0), 2.0);
    }

    #[test]
    fn test_multiply() {
        assert_eq!(multiply(3.0, 4.0), 12.0);
    }

    #[test]
    fn test_divide() {
        assert_eq!(divide(10.0, 2.0).unwrap(), 5.0);
    }

    #[test]
    fn test_divide_by_zero() {
        assert!(divide(1.0, 0.0).is_err());
    }

    #[test]
    fn test_calculator_compute() {
        let mut calc = Calculator::new();
        assert_eq!(calc.compute("add", 1.0, 2.0), 3.0);
    }

    #[test]
    fn test_calculator_last_result() {
        let mut calc = Calculator::new();
        calc.compute("add", 3.0, 4.0);
        assert_eq!(calc.get_last_result(), 7.0);
    }
}
