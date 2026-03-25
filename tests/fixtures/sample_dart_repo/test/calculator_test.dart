import 'package:test/test.dart';
import '../lib/calculator.dart';

void main() {
  group('Calculator functions', () {
    test('should add two numbers', () {
      expect(add(1, 2), equals(3));
    });

    test('should subtract two numbers', () {
      expect(subtract(5, 3), equals(2));
    });

    test('should multiply two numbers', () {
      expect(multiply(3, 4), equals(12));
    });

    test('should throw on division by zero', () {
      expect(() => divide(1, 0), throwsArgumentError);
    });
  });

  group('Calculator class', () {
    test('should compute addition', () {
      final calc = Calculator();
      expect(calc.compute('add', 1, 2), equals(3));
    });

    test('should store last result', () {
      final calc = Calculator();
      calc.compute('add', 3, 4);
      expect(calc.lastResult, equals(7));
    });
  });
}
