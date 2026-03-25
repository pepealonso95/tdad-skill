package calculator;

import utils.Utils;

/**
 * Simple calculator with basic arithmetic operations.
 */
public class Calculator {

    private double lastResult;

    public Calculator() {
        this.lastResult = 0;
    }

    /**
     * Add two numbers.
     */
    public double add(double a, double b) {
        Utils.validateNumber(a);
        Utils.validateNumber(b);
        this.lastResult = a + b;
        return this.lastResult;
    }

    /**
     * Subtract b from a.
     */
    public double subtract(double a, double b) {
        this.lastResult = a - b;
        return this.lastResult;
    }

    public double getLastResult() {
        return this.lastResult;
    }
}
