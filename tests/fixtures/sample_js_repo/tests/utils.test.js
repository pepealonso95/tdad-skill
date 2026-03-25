import { validateNumber, clamp } from '../src/utils.js';

describe('validateNumber', () => {
  test('should accept valid numbers', () => {
    expect(() => validateNumber(42)).not.toThrow();
  });

  test('should reject non-numbers', () => {
    expect(() => validateNumber('foo')).toThrow(TypeError);
  });
});

describe('clamp', () => {
  test('should clamp value within range', () => {
    expect(clamp(5, 0, 10)).toBe(5);
    expect(clamp(-1, 0, 10)).toBe(0);
    expect(clamp(15, 0, 10)).toBe(10);
  });
});
