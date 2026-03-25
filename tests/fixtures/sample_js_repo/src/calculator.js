/**
 * Calculator module — mirrors the Python sample_repo for cross-language testing.
 */

import { validateNumber } from './utils.js';

/**
 * Add two numbers.
 */
export function add(a, b) {
  validateNumber(a);
  validateNumber(b);
  return a + b;
}

export function subtract(a, b) {
  return a - b;
}

export function multiply(a, b) {
  return a * b;
}

export function divide(a, b) {
  if (b === 0) throw new Error("Division by zero");
  return a / b;
}

export class Calculator {
  constructor() {
    this._lastResult = 0;
  }

  compute(op, a, b) {
    switch (op) {
      case "add":
        this._lastResult = add(a, b);
        break;
      case "subtract":
        this._lastResult = subtract(a, b);
        break;
      default:
        throw new Error(`Unknown operation: ${op}`);
    }
    return this._lastResult;
  }

  get lastResult() {
    return this._lastResult;
  }
}
