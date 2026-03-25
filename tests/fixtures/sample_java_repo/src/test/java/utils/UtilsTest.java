package utils;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

/**
 * Tests for the Utils class.
 */
public class UtilsTest {

    @Test
    public void testValidateNumber() {
        assertDoesNotThrow(() -> Utils.validateNumber(42.0));
    }

    @Test
    public void testValidateNumberRejectsNaN() {
        assertThrows(IllegalArgumentException.class, () -> Utils.validateNumber(Double.NaN));
    }

    @Test
    public void testClamp() {
        assertEquals(5.0, Utils.clamp(5, 0, 10));
        assertEquals(0.0, Utils.clamp(-1, 0, 10));
        assertEquals(10.0, Utils.clamp(15, 0, 10));
    }
}
