package com.pipeline.video.config;

import java.math.BigDecimal;

/** 영상 단위 비용 상한의 단일 기준값입니다. */
public final class PricingConfig {
    private PricingConfig() { }
    public static final BigDecimal VIDEO_BUDGET_CAP_KRW = BigDecimal.valueOf(40_000L);
}
