package utils;

/**
 * General-purpose utility methods.
 */
public class Utils {

    /**
     * Validate that a value is a finite number.
     */
    public static void validateNumber(double value) {
        if (Double.isNaN(value) || Double.isInfinite(value)) {
            throw new IllegalArgumentException("Expected a finite number, got " + value);
        }
    }

    /**
     * Clamp a value between min and max.
     */
    public static double clamp(double value, double min, double max) {
        validateNumber(value);
        validateNumber(min);
        validateNumber(max);
        return Math.min(Math.max(value, min), max);
    }
}
