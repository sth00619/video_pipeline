package com.pipeline.video.service;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.pipeline.video.domain.*;
import com.pipeline.video.dto.ShortClipInfo;
import com.pipeline.video.dto.ShortsAnalyzeResponse;
import com.pipeline.video.dto.ShortsConfirmRequest;
import com.pipeline.video.repository.AssetRepository;
import com.pipeline.video.repository.VideoJobRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.math.BigDecimal;
import java.util.List;

/**
 * Phase 2-A + 2-B 통합 ShortsService.
 *
 *  - analyze(): Whisper 분석. 자율성 정책에 따라 AUTO 모드면 confirm까지 자동 호출.
 *  - confirm(): 확정 구간으로 자르기. AUTO/GUIDED-skipped 라면 SHORTS_PREVIEW도 자동 승인.
 *
 *  Mock 단계라 모든 비용은 $0이지만 CostService.record() 흐름은 갖춰둠 (Phase 3 실제 비용 발생 시 동작).
 */
@Service
@Slf4j
@RequiredArgsConstructor
public class ShortsService {

    private final VideoJobRepository jobRepository;
    private final AssetRepository assetRepository;
    private final FastApiClient fastApiClient;
    private final GateService gateService;
    private final AutonomyService autonomyService;
    private final CostService costService;
    private final ObjectMapper objectMapper = new ObjectMapper();

    @Transactional
    public ShortsAnalyzeResponse analyze(Long jobId, MultipartFile file, int shortsCount, String username)
            throws IOException {
        VideoJob job = jobRepository.findById(jobId)
                .orElseThrow(() -> new RuntimeException("Job not found: " + jobId));

        log.info("쇼츠 분석 시작: jobId={}, count={}, autonomy={}",
                jobId, shortsCount, job.getAutonomy());

        // FastAPI 호출
        ShortsAnalyzeResponse result = fastApiClient.analyzeShorts(file, shortsCount, jobId);

        // 비용 기록 (Mock $0, Phase 3에서 실제 가격)
        costService.record(jobId, "WHISPER_TRANSCRIBE",
                BigDecimal.ZERO, "USD", "쇼츠 분석용 Whisper 처리");

        // 작업 상태 업데이트
        job.setSourceVideoPath(result.getSourceVideoPath());
        job.setMakeShorts(true);
        job.setShortsCount(shortsCount);
        job.setStatus(JobStatus.SHORTS_SEGMENTS_PENDING);
        jobRepository.save(job);

        // Asset 저장
        saveAsset(jobId, AssetType.SOURCE_VIDEO, result.getSourceVideoPath(),
                buildSourceMeta(file));
        saveAsset(jobId, AssetType.TRANSCRIPT, null, safeJson(result));

        // 자율성 정책: AUTO 모드면 즉시 confirm까지 자동 실행
        if (autonomyService.isAuto(job) && result.getSuggestedSegments() != null
                && !result.getSuggestedSegments().isEmpty()) {
            log.info("AUTO 모드 — 제안 구간으로 즉시 confirm 자동 호출");
            ShortsConfirmRequest autoReq = new ShortsConfirmRequest();
            autoReq.setSegments(result.getSuggestedSegments());
            confirm(jobId, autoReq, "AUTO");
        }

        return result;
    }

    @Transactional
    public List<ShortClipInfo> confirm(Long jobId, ShortsConfirmRequest request, String username) {
        VideoJob job = jobRepository.findById(jobId)
                .orElseThrow(() -> new RuntimeException("Job not found: " + jobId));

        if (job.getStatus() != JobStatus.SHORTS_SEGMENTS_PENDING) {
            throw new IllegalStateException(
                    "쇼츠 구간 확정은 SHORTS_SEGMENTS_PENDING 상태에서만 가능. 현재: " + job.getStatus());
        }
        if (job.getSourceVideoPath() == null) {
            throw new IllegalStateException("원본 영상 경로 없음. analyze를 먼저 호출하세요.");
        }

        // 게이트 통과 (자율성 정책상 자동/수동 자동 판정)
        gateService.approve(jobId, GateName.SHORTS_SEGMENTS, username, "구간 확정");

        // FastAPI cut 호출
        log.info("쇼츠 자르기 시작: jobId={}, segments={}", jobId, request.getSegments().size());
        List<ShortClipInfo> clips = fastApiClient.cutShorts(jobId, job.getSourceVideoPath(), request);

        // 비용 기록 (Mock $0)
        costService.record(jobId, "FFMPEG_CUT",
                BigDecimal.ZERO, "USD", "쇼츠 자르기 + 9:16 변환");

        // Asset 저장
        for (ShortClipInfo clip : clips) {
            saveAsset(jobId, AssetType.SHORT_CLIP, clip.getOutputPath(), safeJson(clip));
        }

        // 자르기 완료 → 미리보기 대기
        job.setStatus(JobStatus.SHORTS_PREVIEW_PENDING);
        jobRepository.save(job);
        log.info("쇼츠 {}개 생성 완료: jobId={}", clips.size(), jobId);

        // 자율성 정책: AUTO 모드면 SHORTS_PREVIEW 게이트도 자동 승인 → READY
        if (autonomyService.shouldAutoApprove(job, GateName.SHORTS_PREVIEW)) {
            gateService.approve(jobId, GateName.SHORTS_PREVIEW, "AUTO",
                    "자율성 정책에 의한 미리보기 자동 승인");
        }

        return clips;
    }

    public List<Asset> getShortsAssets(Long jobId) {
        return assetRepository.findByJobIdAndAssetType(jobId, AssetType.SHORT_CLIP);
    }

    // ============================
    // helpers
    // ============================
    private void saveAsset(Long jobId, AssetType type, String localPath, String metaJson) {
        Asset asset = Asset.builder()
                .jobId(jobId)
                .assetType(type)
                .localPath(localPath)
                .metaJson(metaJson)
                .build();
        assetRepository.save(asset);
    }

    private String buildSourceMeta(MultipartFile file) {
        return safeJson(java.util.Map.of(
                "originalFilename", file.getOriginalFilename() == null ? "" : file.getOriginalFilename(),
                "size", file.getSize(),
                "contentType", file.getContentType() == null ? "" : file.getContentType()
        ));
    }

    private String safeJson(Object obj) {
        try {
            return objectMapper.writeValueAsString(obj);
        } catch (JsonProcessingException e) {
            return "{}";
        }
    }
}
