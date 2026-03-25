import { add, subtract, multiply, divide, Calculator } from '../src/calculator.js';

describe('Calculator functions', () => {
  test('should add two numbers', () => {
    expect(add(1, 2)).toBe(3);
  });

  test('should subtract two numbers', () => {
    expect(subtract(5, 3)).toBe(2);
  });

  test('should multiply two numbers', () => {
    expect(multiply(3, 4)).toBe(12);
  });

  test('should divide two numbers', () => {
    expect(divide(10, 2)).toBe(5);
  });

  test('should throw on division by zero', () => {
    expect(() => divide(1, 0)).toThrow('Division by zero');
  });
});

describe('Calculator class', () => {
  it('should compute addition', () => {
    const calc = new Calculator();
    expect(calc.compute('add', 1, 2)).toBe(3);
  });

  it('should store last result', () => {
    const calc = new Calculator();
    calc.compute('add', 3, 4);
    expect(calc.lastResult).toBe(7);
  });
});
