package com.pipeline.video.service;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.pipeline.video.domain.*;
import com.pipeline.video.dto.TtsGenerateResponse;
import com.pipeline.video.repository.AssetRepository;
import com.pipeline.video.repository.VideoJobRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.util.Map;

/**
 * Phase 3-3 — TTS 음성 합성 서비스
 *
 *  - generate(): 최종 스크립트 → 청크 분할 → mp3 + 청크별 타이밍 정보 반환
 *  - confirm(): TTS 게이트 통과 → IMAGES_PENDING
 *
 *  핵심: chunks 정보가 Phase 3-4(이미지 매칭), 3-5(자막 동기화)에 활용됨
 */
@Service
@Slf4j
@RequiredArgsConstructor
public class TtsService {

    private final VideoJobRepository jobRepository;
    private final AssetRepository assetRepository;
    private final FastApiClient fastApiClient;
    private final GateService gateService;
    private final AutonomyService autonomyService;
    private final CostService costService;
    private final ObjectMapper objectMapper = new ObjectMapper();

    @Transactional
    public TtsGenerateResponse generate(Long jobId, String voiceId, String username) {
        VideoJob job = jobRepository.findById(jobId)
                .orElseThrow(() -> new RuntimeException("Job not found: " + jobId));

        if (job.getStatus() != JobStatus.TTS_PENDING) {
            throw new IllegalStateException("TTS 생성은 TTS_PENDING 에서만 가능. 현재: " + job.getStatus());
        }

        // 최종 스크립트 조회 (가장 최근 SCRIPT Asset)
        String script = loadFinalScript(jobId);
        if (script == null || script.isBlank()) {
            throw new IllegalStateException("최종 스크립트가 없습니다. 스크립트 확정을 먼저 진행하세요.");
        }

        log.info("TTS 생성 시작: jobId={}, scriptLength={}자, voice={}, autonomy={}",
                jobId, script.length(), voiceId, job.getAutonomy());

        // FastAPI 호출
        TtsGenerateResponse result = fastApiClient.generateTts(jobId, script, voiceId);

        // 비용 기록 (Mock $0, 실제 ElevenLabs는 $0.30/1K characters 기준)
        costService.record(jobId, "ELEVENLABS_TTS", BigDecimal.ZERO, "USD",
                String.format("TTS 합성: %d자, %.1f초", script.length(), result.getTotalDuration()));

        // Asset 저장
        Asset asset = Asset.builder()
                .jobId(jobId)
                .assetType(AssetType.TTS_AUDIO)
                .localPath(result.getAudioPath())
                .metaJson(safeJson(result))
                .build();
        assetRepository.save(asset);

        // AUTO 모드: 자동 confirm → IMAGES_PENDING
        if (autonomyService.isAuto(job)) {
            log.info("AUTO 모드 — TTS 자동 확정");
            confirm(jobId, "AUTO");
        }

        return result;
    }

    @Transactional
    public void confirm(Long jobId, String username) {
        VideoJob job = jobRepository.findById(jobId)
                .orElseThrow(() -> new RuntimeException("Job not found: " + jobId));

        if (job.getStatus() != JobStatus.TTS_PENDING) {
            throw new IllegalStateException("TTS 확정은 TTS_PENDING 에서만 가능. 현재: " + job.getStatus());
        }

        // 게이트 통과 → IMAGES_PENDING
        gateService.approve(jobId, GateName.TTS, username, "TTS 확정");
        log.info("TTS 확정 완료: jobId={}", jobId);
    }

    // ============================
    // helpers
    // ============================
    @SuppressWarnings("unchecked")
    private String loadFinalScript(Long jobId) {
        Asset asset = assetRepository
                .findTopByJobIdAndAssetTypeOrderByCreatedAtDesc(jobId, AssetType.SCRIPT)
                .orElseThrow(() -> new RuntimeException("스크립트 Asset이 없습니다: " + jobId));

        try {
            Map<String, Object> meta = objectMapper.readValue(asset.getMetaJson(), Map.class);
            // confirm 단계에서 저장한 final=true 우선
            Object scriptVal = meta.get("script");
            if (scriptVal != null) return scriptVal.toString();
            return null;
        } catch (Exception e) {
            log.error("스크립트 파싱 실패: {}", e.getMessage());
            return null;
        }
    }

    private String safeJson(Object obj) {
        try {
            return objectMapper.writeValueAsString(obj);
        } catch (JsonProcessingException e) {
            return "{}";
        }
    }
}
