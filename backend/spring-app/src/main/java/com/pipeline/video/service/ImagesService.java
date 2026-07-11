package com.pipeline.video.service;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.pipeline.video.domain.*;
import com.pipeline.video.dto.GifClipDto;
import com.pipeline.video.dto.ImagesGenerateResponse;
import com.pipeline.video.dto.SceneImageDto;
import com.pipeline.video.repository.AssetRepository;
import com.pipeline.video.repository.VideoJobRepository;
import com.pipeline.video.repository.ChannelProfileRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.util.Map;
import java.util.List;

/**
 * Phase 3-4 — 이미지 + GIF 생성 서비스
 *
 *  - generate(): TTS chunks 기반 씬 이미지 + 섹션 전환점 GIF 생성
 *  - confirm(): IMAGES 게이트 통과 → ASSEMBLING
 *
 *  산출물은 Phase 3-5 롱폼 조립에서 직접 참조됨.
 */
@Service
@Slf4j
@RequiredArgsConstructor
public class ImagesService {

    private final VideoJobRepository jobRepository;
    private final AssetRepository assetRepository;
    private final ChannelProfileRepository channelProfileRepository;
    private final FastApiClient fastApiClient;
    private final GateService gateService;
    private final AutonomyService autonomyService;
    private final CostService costService;
    private final ObjectMapper objectMapper = new ObjectMapper();

    @Transactional
    public ImagesGenerateResponse generate(Long jobId, String username) {
        VideoJob job = jobRepository.findById(jobId)
                .orElseThrow(() -> new RuntimeException("Job not found: " + jobId));

        if (job.getStatus() == JobStatus.DRAFT || job.getStatus() == JobStatus.KEYWORD_PENDING || job.getStatus() == JobStatus.SCRIPT_PENDING || job.getStatus() == JobStatus.TTS_PENDING) {
            throw new IllegalStateException("TTS 확정 전에는 이미지를 생성할 수 없습니다. 현재: " + job.getStatus());
        }

        // TTS chunks 로드
        String ttsMetaJson = loadAssetMeta(jobId, AssetType.TTS_AUDIO);
        // 스크립트 로드
        String scriptMetaJson = loadAssetMeta(jobId, AssetType.SCRIPT);

        // 채널 프로필 로드 (캐릭터 일관성 파라미터 추출)
        String characterImagePath = null;
        String characterStylePrompt = null;
        if (job.getChannelId() != null) {
            ChannelProfile profile = channelProfileRepository.findById(job.getChannelId()).orElse(null);
            if (profile != null) {
                characterImagePath = profile.getCharacterImagePath();
                characterStylePrompt = profile.getCharacterStylePrompt();
                log.info("채널 캐릭터 프로필 로드 완료: channelId={}, characterImagePath={}",
                        job.getChannelId(), characterImagePath);
            }
        }

        log.info("이미지 생성 시작: jobId={}, autonomy={}", jobId, job.getAutonomy());

        // FastAPI 호출
        ImagesGenerateResponse result = fastApiClient.generateImages(
                jobId, ttsMetaJson, scriptMetaJson, characterImagePath, characterStylePrompt);

        // [버그 수정] 기존 imgCost = BigDecimal.ZERO → 실제 이미지 장 수 기반 요금 추정
        java.math.BigDecimal imgCost = CostEstimator.geminiImages(result.getSceneCount());
        costService.record(jobId, "GEMINI_IMAGE", imgCost, "USD",
                String.format("씬 이미지 %d장 + GIF %d개",
                        result.getSceneCount(), result.getGifCount()));

        // Asset 저장 — 씬 이미지
        if (result.getScenes() != null) {
            for (SceneImageDto scene : result.getScenes()) {
                Asset asset = Asset.builder()
                        .jobId(jobId)
                        .assetType(AssetType.SCENE_IMAGE)
                        .localPath(scene.getImagePath())
                        .metaJson(safeJson(scene))
                        .build();
                assetRepository.save(asset);
            }
        }

        // Asset 저장 — GIF 클립
        if (result.getGifs() != null) {
            for (GifClipDto gif : result.getGifs()) {
                Asset asset = Asset.builder()
                        .jobId(jobId)
                        .assetType(AssetType.GIF_CLIP)
                        .localPath(gif.getGifPath())
                        .metaJson(safeJson(gif))
                        .build();
                assetRepository.save(asset);
            }
        }

        // AUTO 모드: 자동 confirm → ASSEMBLING
        if (autonomyService.isAuto(job)) {
            log.info("AUTO 모드 — 이미지 자동 확정");
            confirm(jobId, "AUTO");
        }

        return result;
    }

    @Transactional
    public void confirm(Long jobId, String username) {
        VideoJob job = jobRepository.findById(jobId)
                .orElseThrow(() -> new RuntimeException("Job not found: " + jobId));

        if (job.getStatus() == JobStatus.DRAFT || job.getStatus() == JobStatus.KEYWORD_PENDING || job.getStatus() == JobStatus.SCRIPT_PENDING || job.getStatus() == JobStatus.TTS_PENDING) {
            throw new IllegalStateException("TTS 확정 전에는 이미지를 확정할 수 없습니다. 현재: " + job.getStatus());
        }

        if (job.getStatus() == JobStatus.IMAGES_PENDING) {
            gateService.approve(jobId, GateName.IMAGES, username, "이미지/GIF 확정");
        } else {
            log.info("이미지 수정/재확정 완료 (상태 유지: {}): jobId={}", job.getStatus(), jobId);
        }
        log.info("이미지 확정 완료: jobId={}", jobId);
    }

    @Transactional
    public void updateScene(Long jobId, int index, String text, String section, String mode) {
        // 1. SCENE_IMAGE 타입의 에셋 전체 조회
        List<Asset> assets = assetRepository.findByJobIdAndAssetType(jobId, AssetType.SCENE_IMAGE);
        Asset target = null;
        SceneImageDto sceneDto = null;
        for (Asset asset : assets) {
            try {
                SceneImageDto dto = objectMapper.readValue(asset.getMetaJson(), SceneImageDto.class);
                if (dto.getIndex() == index) {
                    target = asset;
                    sceneDto = dto;
                    break;
                }
            } catch (Exception e) {
                // ignore
            }
        }
        if (target == null) {
            throw new IllegalArgumentException("해당 씬 이미지를 찾을 수 없습니다: index=" + index);
        }

        // 2. prompt 변경: mode가 "image"가 아닌 경우에만 텍스트를 업데이트함
        if (mode == null || !mode.equalsIgnoreCase("image")) {
            sceneDto.setPrompt(text);
        }
        if (section != null && !section.isBlank()) {
            sceneDto.setSection(section);
        }
        target.setMetaJson(safeJson(sceneDto));
        assetRepository.save(target);

        // 3. 이미지 재생성: mode가 "text"가 아닌 경우에만 FastAPI 호출
        if (mode == null || !mode.equalsIgnoreCase("text")) {
            VideoJob job = jobRepository.findById(jobId)
                    .orElseThrow(() -> new RuntimeException("Job not found: " + jobId));
            String characterImagePath = null;
            String characterStylePrompt = null;
            if (job.getChannelId() != null) {
                ChannelProfile profile = channelProfileRepository.findById(job.getChannelId()).orElse(null);
                if (profile != null) {
                    characterImagePath = profile.getCharacterImagePath();
                    characterStylePrompt = profile.getCharacterStylePrompt();
                }
            }

            // 이미지 재생성은 sceneDto의 (업데이트되었거나 기존의) prompt를 기준으로 호출
            fastApiClient.generateSingleImage(jobId, index, sceneDto.getPrompt(), sceneDto.getSection(), characterImagePath, characterStylePrompt);
            log.info("씬 이미지 재생성 요청 완료: jobId={}, index={}, section={}, mode={}", jobId, index, sceneDto.getSection(), mode);
        } else {
            log.info("씬 텍스트 수정 완료 (이미지 유지): jobId={}, index={}", jobId, index);
        }
    }

    @Transactional
    public void splitScene(Long jobId, int index, String part1, String part2) {
        List<Asset> assets = assetRepository.findByJobIdAndAssetType(jobId, AssetType.SCENE_IMAGE);
        
        java.util.List<Asset> sortedAssets = new java.util.ArrayList<>(assets);
        sortedAssets.sort((a, b) -> {
            try {
                SceneImageDto dtoA = objectMapper.readValue(a.getMetaJson(), SceneImageDto.class);
                SceneImageDto dtoB = objectMapper.readValue(b.getMetaJson(), SceneImageDto.class);
                return Integer.compare(dtoA.getIndex(), dtoB.getIndex());
            } catch (Exception e) {
                return 0;
            }
        });
        
        Asset targetAsset = null;
        SceneImageDto targetDto = null;
        for (Asset asset : sortedAssets) {
            try {
                SceneImageDto dto = objectMapper.readValue(asset.getMetaJson(), SceneImageDto.class);
                if (dto.getIndex() == index) {
                    targetAsset = asset;
                    targetDto = dto;
                    break;
                }
            } catch (Exception e) {
                // ignore
            }
        }
        
        if (targetAsset == null) {
            throw new IllegalArgumentException("Cannot find scene to split: index=" + index);
        }
        
        // Shift indices of all assets with index > targetIndex by 1
        for (Asset asset : sortedAssets) {
            try {
                SceneImageDto dto = objectMapper.readValue(asset.getMetaJson(), SceneImageDto.class);
                if (dto.getIndex() > index) {
                    dto.setIndex(dto.getIndex() + 1);
                    asset.setMetaJson(objectMapper.writeValueAsString(dto));
                    assetRepository.save(asset);
                }
            } catch (Exception e) {
                // ignore
            }
        }
        
        // Update target asset (part 1)
        targetDto.setPrompt(part1);
        double origDuration = targetDto.getDuration() != null ? targetDto.getDuration() : 10.0;
        double origStart = targetDto.getStart() != null ? targetDto.getStart() : 0.0;
        
        targetDto.setDuration(origDuration / 2.0);
        targetAsset.setMetaJson(safeJson(targetDto));
        assetRepository.save(targetAsset);
        
        // Create new asset (part 2) at index + 1
        SceneImageDto newDto = new SceneImageDto();
        newDto.setIndex(index + 1);
        newDto.setPrompt(part2);
        newDto.setSection(targetDto.getSection());
        newDto.setImagePath(targetDto.getImagePath()); // Copy image path to maintain character profile
        newDto.setDuration(origDuration / 2.0);
        newDto.setStart(origStart + (origDuration / 2.0));
        
        Asset newAsset = Asset.builder()
            .jobId(jobId)
            .assetType(AssetType.SCENE_IMAGE)
            .localPath(targetAsset.getLocalPath())
            .metaJson(safeJson(newDto))
            .build();
            
        assetRepository.save(newAsset);
        log.info("씬 분할 완료: jobId={}, index={} → {} & {}", jobId, index, index, index + 1);
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
            return "{}";
        }
    }
}
