package com.pipeline.video.config;

import java.math.BigDecimal;

/** 영상 길이별 비용 상한과 정책 버전의 단일 기준값입니다. */
public final class PricingConfig {
    private PricingConfig() { }
    public static final int LONGFORM_THRESHOLD_MINUTES = 20;
    public static volatile BigDecimal SHORTFORM_BUDGET_CAP_KRW = BigDecimal.valueOf(40_000L);
    public static volatile BigDecimal LONGFORM_BUDGET_CAP_KRW = BigDecimal.valueOf(70_000L);
    /** 예산 차단용 고정 환산율. 원장은 제공자 원통화로 보존한다. */
    public static final BigDecimal USD_TO_KRW_BUDGET_RATE = BigDecimal.valueOf(1_400L);
    /** Google Gemini 공식 Standard 2K 이미지 출력 단가(2026-08-25 확인). */
    public static final BigDecimal GEMINI_3_PRO_IMAGE_2K_USD = BigDecimal.valueOf(0.134D);
    /** Google Gemini 공식 Priority 이미지 $216/M × Pro 2K 1,120토큰(2026-08-30 확인). */
    public static final BigDecimal GEMINI_3_PRO_IMAGE_PRIORITY_2K_USD = BigDecimal.valueOf(0.24192D);
    public static final BigDecimal GEMINI_3_1_FLASH_IMAGE_2K_USD = BigDecimal.valueOf(0.101D);
    public static final String POLICY_VERSION = "duration-tier-2026-08-30";
    /** Gemini 정지 이미지에만 적용하는 기본 상한이다. Fal 모션 비용은 포함하지 않는다. */
    public static final BigDecimal DEFAULT_GEMINI_IMAGE_BUDGET_CAP_KRW = BigDecimal.valueOf(20_000L);
    public static final String GEMINI_IMAGE_ONLY_POLICY_VERSION = "gemini-pro-priority-only-2026-08-30";

    public static synchronized void updatePolicy(BigDecimal shortformCap, BigDecimal longformCap) {
        if (shortformCap != null && shortformCap.compareTo(BigDecimal.ZERO) > 0) {
            SHORTFORM_BUDGET_CAP_KRW = shortformCap;
        }
        if (longformCap != null && longformCap.compareTo(BigDecimal.ZERO) > 0) {
            LONGFORM_BUDGET_CAP_KRW = longformCap;
        }
    }

    public static BigDecimal budgetCapForTargetMinutes(Integer targetMinutes) {
        int minutes = targetMinutes == null ? LONGFORM_THRESHOLD_MINUTES : Math.max(0, targetMinutes);
        return minutes >= LONGFORM_THRESHOLD_MINUTES
                ? LONGFORM_BUDGET_CAP_KRW
                : SHORTFORM_BUDGET_CAP_KRW;
    }

    public static BigDecimal geminiImageBudgetCapFor(BigDecimal requestedCap, BigDecimal videoBudgetCap) {
        BigDecimal requested = requestedCap == null ? DEFAULT_GEMINI_IMAGE_BUDGET_CAP_KRW : requestedCap;
        if (requested.compareTo(BigDecimal.ZERO) <= 0) {
            throw new IllegalArgumentException("Gemini 이미지 예산 상한은 0원보다 커야 합니다.");
        }
        return requested.min(videoBudgetCap);
    }
}
