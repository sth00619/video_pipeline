package com.pipeline.video.service;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.pipeline.video.domain.*;
import com.pipeline.video.dto.LongformGenerateResponse;
import com.pipeline.video.repository.AssetRepository;
import com.pipeline.video.repository.VideoJobRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.util.List;

/**
 * Phase 3-5A — 롱폼 영상 조립 서비스
 *
 * 흐름:
 *   ASSEMBLING 진입 (IMAGES 게이트 통과 후)
 *     ↓
 *   generate(): TTS 음성 + 씬 이미지 + GIF → FFmpeg 조립 → MP4
 *     ↓
 *   상태 → PREVIEW_PENDING
 *     ↓
 *   confirm(): PREVIEW 게이트 통과 → SHORTS_SEGMENTS_PENDING (쇼츠 모드)
 *              또는 READY (쇼츠 미생성)
 */
@Service
@Slf4j
@RequiredArgsConstructor
public class LongformService {

    private final VideoJobRepository jobRepository;
    private final AssetRepository assetRepository;
    private final FastApiClient fastApiClient;
    private final GateService gateService;
    private final AutonomyService autonomyService;
    private final CostService costService;
    private final ObjectMapper objectMapper = new ObjectMapper();

    @Transactional
    public LongformGenerateResponse generate(Long jobId, String username) {
        VideoJob job = jobRepository.findById(jobId)
                .orElseThrow(() -> new RuntimeException("Job not found: " + jobId));

        if (job.getStatus() != JobStatus.ASSEMBLING) {
            throw new IllegalStateException("롱폼 조립은 ASSEMBLING 에서만 가능. 현재: " + job.getStatus());
        }

        // TTS Asset 로드 (audio_path + chunks)
        String ttsMetaJson = loadAssetMeta(jobId, AssetType.TTS_AUDIO);
        // SCENE_IMAGE Asset 목록 로드
        List<Asset> sceneAssets = assetRepository.findByJobIdAndAssetType(jobId, AssetType.SCENE_IMAGE);
        // GIF_CLIP Asset 목록 로드
        List<Asset> gifAssets = assetRepository.findByJobIdAndAssetType(jobId, AssetType.GIF_CLIP);

        log.info("롱폼 조립 시작: jobId={}, scenes={}, gifs={}, autonomy={}",
                jobId, sceneAssets.size(), gifAssets.size(), job.getAutonomy());

        // scenes와 gifs의 metaJson 목록 전송
        String scenesJson = safeJson(sceneAssets.stream()
                .map(Asset::getMetaJson).toList());
        String gifsJson = safeJson(gifAssets.stream()
                .map(Asset::getMetaJson).toList());

        // FastAPI 호출
        LongformGenerateResponse result = fastApiClient.generateLongform(
                jobId, ttsMetaJson, scenesJson, gifsJson);

        // 비용 기록 (Mock $0)
        costService.record(jobId, "FFMPEG_ASSEMBLE", BigDecimal.ZERO, "USD",
                String.format("롱폼 조립: %.0f초, %d씬", 
                        result.getDurationSeconds(), result.getSceneCount()));

        // Asset 저장
        Asset asset = Asset.builder()
                .jobId(jobId)
                .assetType(AssetType.LONGFORM_VIDEO)
                .localPath(result.getVideoPath())
                .metaJson(safeJson(result))
                .build();
        assetRepository.save(asset);

        // outputPath 업데이트
        job.setOutputPath(result.getVideoPath());
        // ASSEMBLING → PREVIEW_PENDING
        job.setStatus(JobStatus.PREVIEW_PENDING);
        jobRepository.save(job);

        // AUTO 모드: 자동 confirm
        if (autonomyService.isAuto(job)) {
            log.info("AUTO 모드 — 롱폼 미리보기 자동 확정");
            confirm(jobId, "AUTO");
        }

        return result;
    }

    @Transactional
    public void confirm(Long jobId, String username) {
        VideoJob job = jobRepository.findById(jobId)
                .orElseThrow(() -> new RuntimeException("Job not found: " + jobId));

        if (job.getStatus() != JobStatus.PREVIEW_PENDING) {
            throw new IllegalStateException("롱폼 확정은 PREVIEW_PENDING 에서만 가능. 현재: " + job.getStatus());
        }

        // PREVIEW 게이트 통과
        gateService.approve(jobId, GateName.PREVIEW, username, "롱폼 미리보기 확정");

        // 게이트 통과 후: makeShorts=true → SHORTS_SEGMENTS_PENDING
        //                 makeShorts=false → READY (PREVIEW 다음이 SHORTS_SEGMENTS_PENDING)
        // GateService.NEXT_STATUS_ON_APPROVE에 의해 SHORTS_SEGMENTS_PENDING으로 전이됨
        // makeShorts가 false이면 쇼츠 단계를 건너뛰고 READY로 직접 변경
        if (!job.isMakeShorts()) {
            job.setStatus(JobStatus.READY);
            jobRepository.save(job);
            log.info("쇼츠 미생성 → READY: jobId={}", jobId);
        } else {
            log.info("쇼츠 생성 예정 → SHORTS_SEGMENTS_PENDING: jobId={}", jobId);
        }
    }

    // ============================
    // helpers
    // ============================
    private String loadAssetMeta(Long jobId, AssetType type) {
        return assetRepository
                .findTopByJobIdAndAssetTypeOrderByCreatedAtDesc(jobId, type)
                .map(Asset::getMetaJson)
                .orElseThrow(() -> new RuntimeException(type + " Asset이 없습니다: " + jobId));
    }

    private String safeJson(Object obj) {
        try {
            return objectMapper.writeValueAsString(obj);
        } catch (JsonProcessingException e) {
            return "[]";
        }
    }
}
