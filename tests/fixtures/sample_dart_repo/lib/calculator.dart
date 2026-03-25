import 'utils.dart';

/// Add two numbers.
int add(int a, int b) {
  validateNumber(a);
  validateNumber(b);
  return a + b;
}

/// Subtract b from a.
int subtract(int a, int b) {
  return a - b;
}

int multiply(int a, int b) {
  return a * b;
}

int divide(int a, int b) {
  if (b == 0) throw ArgumentError('Division by zero');
  return a ~/ b;
}

/// A stateful calculator.
class Calculator {
  int _lastResult = 0;

  Calculator();

  /// Named constructor.
  Calculator.withInitial(int initial) : _lastResult = initial;

  int compute(String op, int a, int b) {
    switch (op) {
      case 'add':
        _lastResult = add(a, b);
        break;
      case 'subtract':
        _lastResult = subtract(a, b);
        break;
      default:
        throw ArgumentError('Unknown operation: $op');
    }
    return _lastResult;
  }

  int get lastResult => _lastResult;
}

class AdvancedCalculator extends Calculator {
  double power(double base, double exp) {
    return base * exp;
  }
}
