package calculator;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

/**
 * Tests for the Calculator class.
 */
public class CalculatorTest {

    @Test
    public void testAdd() {
        Calculator calc = new Calculator();
        assertEquals(5.0, calc.add(2, 3));
    }

    @Test
    public void testSubtract() {
        Calculator calc = new Calculator();
        assertEquals(2.0, calc.subtract(5, 3));
    }

    @Test
    public void testLastResult() {
        Calculator calc = new Calculator();
        calc.add(3, 4);
        assertEquals(7.0, calc.getLastResult());
    }
}
