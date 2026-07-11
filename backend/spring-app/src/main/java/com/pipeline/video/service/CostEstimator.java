package com.pipeline.video.service;

import java.math.BigDecimal;
import java.math.RoundingMode;

/**
 * 프로바이더별 실제 요금 추정 유틸리티.
 *
 * 배경:
 *   지금까지 ScriptService / TtsService / ImagesService / KeywordService /
 *   LongformService / ShortsService 전부가 costService.record(..., BigDecimal.ZERO, ...)
 *   로 $0을 기록하고 있었습니다. 그래서 budgetCap이 걸려있어도 실제 지출이
 *   전혀 누적되지 않아 예산 가드레일이 사실상 작동하지 않았고, JobDetail의
 *   비용 게이지도 항상 0으로만 표시되었습니다.
 *
 * 여기서 사용하는 요율(2025년 4분기 공식 요금표 기준 근사치):
 *   - Claude Sonnet 4.6: input $3/M tokens, output $15/M tokens
 *     (스크립트 워커는 3-Round 팩트체크로 왕복이 3회이므로 요금이 누적됨)
 *   - ElevenLabs Multilingual v2: 약 $0.30 / 1,000자
 *     (실제로는 구독 플랜에 따라 정액이지만, 사용량 기반 근사)
 *   - Gemini 3 Flash Image: 약 $0.039 / 이미지 (1024x1024 기준)
 *   - YouTube Data API v3: 무료 쿼터 내에서만 사용 (실비 $0)
 *   - Fal.ai Kling image-to-video Pro: 약 $0.09 / 초
 *
 * 주의:
 *   실제 청구액은 API 응답의 usage 필드에 나오지만, 여기선 문자 수/토큰 수
 *   기반의 근사치를 반환합니다. 정확한 청구액은 월말 콘솔에서 확인해야 합니다.
 *   요율이 바뀌면 이 클래스만 고치면 되도록 상수로 분리해 두었습니다.
 */
public final class CostEstimator {

    // Claude Sonnet 4.6 (per million tokens, USD)
    private static final BigDecimal CLAUDE_INPUT_PER_MTOK = new BigDecimal("3.00");
    private static final BigDecimal CLAUDE_OUTPUT_PER_MTOK = new BigDecimal("15.00");

    // ElevenLabs Multilingual v2 (per 1000 chars, USD 근사)
    private static final BigDecimal ELEVENLABS_PER_1K_CHARS = new BigDecimal("0.30");

    // Gemini 3 Flash Image (per generated image, USD 근사)
    private static final BigDecimal GEMINI_PER_IMAGE = new BigDecimal("0.039");

    // Fal.ai Kling image-to-video Pro (per second, USD 근사)
    // [리서치 반영] v3(고가) → v2.6 Pro로 모델 다운그레이드 + generate_audio=false
    // 적용에 맞춰 요율 갱신 (v3 대비 v2.6 Pro가 캐릭터 일관성 대비 비용이 더
    // 좋아서 채택. fal.ai 공식 요율: $0.07/초, audio off 기준)
    private static final BigDecimal FAL_KLING_PER_SEC = new BigDecimal("0.07");

    private CostEstimator() {}

    /**
     * Claude 텍스트 생성 비용 추정.
     *
     * 스크립트 워커는 3-Round 팩트체크 + 최종 생성으로 왕복이 여러 번이므로,
     * roundTrips 파라미터로 배수를 조정할 수 있습니다.
     * 한국어 1자 ≈ 1.5 토큰으로 근사.
     */
    public static BigDecimal claude(int inputChars, int outputChars, int roundTrips) {
        double inputTokens = inputChars * 1.5 * Math.max(roundTrips, 1);
        double outputTokens = outputChars * 1.5 * Math.max(roundTrips, 1);
        BigDecimal inputCost = CLAUDE_INPUT_PER_MTOK
                .multiply(BigDecimal.valueOf(inputTokens / 1_000_000.0));
        BigDecimal outputCost = CLAUDE_OUTPUT_PER_MTOK
                .multiply(BigDecimal.valueOf(outputTokens / 1_000_000.0));
        return inputCost.add(outputCost).setScale(4, RoundingMode.HALF_UP);
    }

    /** ElevenLabs TTS 비용 추정 (문자 수 기반) */
    public static BigDecimal elevenLabs(int charCount) {
        return ELEVENLABS_PER_1K_CHARS
                .multiply(BigDecimal.valueOf(charCount / 1000.0))
                .setScale(4, RoundingMode.HALF_UP);
    }

    /** Gemini 이미지 생성 비용 추정 (장 수 기반) */
    public static BigDecimal geminiImages(int imageCount) {
        return GEMINI_PER_IMAGE.multiply(BigDecimal.valueOf(imageCount))
                .setScale(4, RoundingMode.HALF_UP);
    }

    /** Fal.ai Kling image-to-video 비용 추정 (총 초 수 기반) */
    public static BigDecimal falKling(double totalSeconds) {
        return FAL_KLING_PER_SEC.multiply(BigDecimal.valueOf(totalSeconds))
                .setScale(4, RoundingMode.HALF_UP);
    }
}
