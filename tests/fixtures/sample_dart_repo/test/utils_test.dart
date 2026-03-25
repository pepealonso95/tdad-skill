import 'package:test/test.dart';
import '../lib/utils.dart';

void main() {
  group('validateNumber', () {
    test('should accept valid numbers', () {
      expect(() => validateNumber(42), returnsNormally);
    });

    test('should reject NaN', () {
      expect(() => validateNumber(double.nan), throwsArgumentError);
    });
  });

  group('clamp', () {
    test('should clamp value within range', () {
      expect(clamp(5, 0, 10), equals(5));
      expect(clamp(-1, 0, 10), equals(0));
      expect(clamp(15, 0, 10), equals(10));
    });
  });
}
