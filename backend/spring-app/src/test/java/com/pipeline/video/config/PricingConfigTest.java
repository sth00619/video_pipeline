package com.pipeline.video.config;

import org.junit.jupiter.api.Test;

import java.math.BigDecimal;

import static org.junit.jupiter.api.Assertions.assertEquals;

class PricingConfigTest {

    @Test
    void appliesFortyThousandWonBelowTwentyMinutes() {
        assertEquals(BigDecimal.valueOf(40_000L), PricingConfig.budgetCapForTargetMinutes(19));
    }

    @Test
    void appliesEightyThousandWonAtAndAboveTwentyMinutes() {
        assertEquals(BigDecimal.valueOf(80_000L), PricingConfig.budgetCapForTargetMinutes(20));
        assertEquals(BigDecimal.valueOf(80_000L), PricingConfig.budgetCapForTargetMinutes(30));
    }
}
