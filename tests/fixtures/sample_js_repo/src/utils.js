/**
 * Utility functions.
 */

export function validateNumber(value) {
  if (typeof value !== 'number' || isNaN(value)) {
    throw new TypeError(`Expected a number, got ${typeof value}`);
  }
}

export function clamp(value, min, max) {
  validateNumber(value);
  validateNumber(min);
  validateNumber(max);
  return Math.min(Math.max(value, min), max);
}
