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

    private static final String PROVIDER_CREDIT_ERROR_CODE = "IMAGE_PROVIDER_CREDIT_REQUIRED";

    /**
     * A provider billing/quota failure is terminal for this attempt, but not
     * for the user's job: previously rendered scenes are resumable after the
     * account is funded.  Do not roll back the retry-required job state.
     */
    public static class ImageProviderRetryRequiredException extends RuntimeException {
        public ImageProviderRetryRequiredException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    private final VideoJobRepository jobRepository;
    private final AssetRepository assetRepository;
    private final ChannelProfileRepository channelProfileRepository;
    private final CharacterAssetResolver characterAssetResolver;
    private final FastApiClient fastApiClient;
    private final GateService gateService;
    private final AutonomyService autonomyService;
    private final CostService costService;
    private final ObjectMapper objectMapper = new ObjectMapper();

    @Transactional(noRollbackFor = ImageProviderRetryRequiredException.class)
    public ImagesGenerateResponse generate(Long jobId, String username) {
        VideoJob job = jobRepository.findById(jobId)
                .orElseThrow(() -> new RuntimeException("Job not found: " + jobId));

        if (job.getStatus() == JobStatus.DRAFT || job.getStatus() == JobStatus.KEYWORD_PENDING || job.getStatus() == JobStatus.SCRIPT_PENDING || job.getStatus() == JobStatus.TTS_PENDING) {
            throw new IllegalStateException("TTS 확정 전에는 이미지를 생성할 수 없습니다. 현재: " + job.getStatus());
        }
        if (job.getStatus() == JobStatus.IMAGES_RETRY_REQUIRED) {
            // Keep approved keyword/script/TTS assets; only the image gate is
            // reopened after a terminal provider batch error.
            job.setStatus(JobStatus.IMAGES_PENDING);
            jobRepository.save(job);
        }

        // TTS chunks 로드
        String ttsMetaJson = loadAssetMeta(jobId, AssetType.TTS_AUDIO);
        // 스크립트 로드
        String scriptMetaJson = loadAssetMeta(jobId, AssetType.SCRIPT);

        CharacterAssetResolver.ResolvedCharacter character = characterAssetResolver.resolve(job);
        log.info("단일 캐릭터 정체성 해석 완료: jobId={}, profileId={}, hash={}",
                jobId, character.profileId(), character.identityHash().substring(0, 12));

        log.info("이미지 생성 시작: jobId={}, autonomy={}", jobId, job.getAutonomy());

        // FastAPI 호출
        ImagesGenerateResponse result;
        try {
            result = fastApiClient.generateImages(
                    jobId, ttsMetaJson, scriptMetaJson, character.imagePath(), character.stylePrompt(), character.posesDir(),
                    character.loraModelId(), character.loraTriggerWord(), character.loraScale());
        } catch (RuntimeException e) {
            if (isProviderCreditRequired(e)) {
                job.setStatus(JobStatus.IMAGES_RETRY_REQUIRED);
                jobRepository.save(job);
                log.warn("이미지 공급자 크레딧/쿼터 부족으로 재시도 대기: jobId={}", jobId);
                throw new ImageProviderRetryRequiredException(
                        "이미지 공급자 크레딧 또는 쿼터가 부족합니다. 충전 후 이미지 생성만 다시 시도해 주세요.", e);
            }
            throw e;
        }

        if ("BATCH_PENDING".equals(result.getStatus())) {
            assetRepository.findByJobIdAndAssetType(jobId, AssetType.IMAGE_BATCH)
                    .forEach(assetRepository::delete);
            assetRepository.save(Asset.builder()
                    .jobId(jobId)
                    .assetType(AssetType.IMAGE_BATCH)
                    .localPath(result.getBatchJobName())
                    .metaJson(safeJson(result))
                    .build());
            log.info("Gemini Pro Batch submitted: jobId={}, batch={}", jobId, result.getBatchJobName());
            return result;
        }

        // [버그 수정] 기존 imgCost = BigDecimal.ZERO → 실제 이미지 장 수 기반 요금 추정
        long newlyRenderedSceneCount = result.getScenes() == null ? 0 : result.getScenes().stream()
                .filter(scene -> !"resumed_existing".equals(scene.getGenerationMethod()))
                .count();
        if (newlyRenderedSceneCount > 0) {
        java.math.BigDecimal imgCost = CostEstimator.geminiImages((int) newlyRenderedSceneCount);
        costService.record(jobId, "GEMINI_IMAGE", imgCost, "USD",
                String.format("씬 이미지 %d장 + GIF %d개",
                        result.getSceneCount(), result.getGifCount()));

        // Asset 저장 — 씬 이미지
        }

        if (result.getScenes() != null) {
            for (SceneImageDto scene : result.getScenes()) {
                boolean alreadyRegistered = assetRepository.findByJobIdAndAssetType(jobId, AssetType.SCENE_IMAGE)
                        .stream().anyMatch(existing -> scene.getImagePath().equals(existing.getLocalPath()));
                if (alreadyRegistered) continue;
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

    private static boolean isProviderCreditRequired(Throwable error) {
        for (Throwable current = error; current != null; current = current.getCause()) {
            String message = current.getMessage();
            if (message != null && message.contains(PROVIDER_CREDIT_ERROR_CODE)) {
                return true;
            }
        }
        return false;
    }

    @Transactional
    public void completeBatch(Long jobId, Long batchAssetId, ImagesGenerateResponse result) {
        if (!"BATCH_COMPLETE".equals(result.getStatus()) || assetRepository.findById(batchAssetId).isEmpty()) {
            return;
        }
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
        java.math.BigDecimal imgCost = CostEstimator.geminiProBatchImages(result.getSceneCount());
        costService.record(jobId, "GEMINI_PRO_BATCH_IMAGE", imgCost, "USD",
                String.format("Gemini Pro Batch scene images %d", result.getSceneCount()));
        assetRepository.deleteById(batchAssetId);
        VideoJob job = jobRepository.findById(jobId)
                .orElseThrow(() -> new RuntimeException("Job not found: " + jobId));
        if (autonomyService.shouldAutoApprove(job, GateName.IMAGES)) {
            gateService.tryAutoApproveAtCurrentStatus(jobId);
        }
        log.info("Gemini Pro Batch completed: jobId={}, scenes={}", jobId, result.getSceneCount());
    }

    /**
     * Retire a terminal Gemini batch failure.  Leaving IMAGE_BATCH behind
     * would make the scheduler poll the same failed remote batch forever.
     */
    @Transactional
    public void failBatch(Long jobId, Long batchAssetId, String reason) {
        assetRepository.findById(batchAssetId).ifPresent(asset -> {
            asset.setMetaJson(safeJson(Map.of(
                    "status", "BATCH_FAILED",
                    "batchJobName", asset.getLocalPath() == null ? "" : asset.getLocalPath(),
                    "error", reason == null ? "unknown batch failure" : reason
            )));
            assetRepository.save(asset);
        });
        VideoJob job = jobRepository.findById(jobId)
                .orElseThrow(() -> new RuntimeException("Job not found: " + jobId));
        if (job.getStatus() == JobStatus.IMAGES_PENDING) {
            job.setStatus(JobStatus.IMAGES_RETRY_REQUIRED);
            jobRepository.save(job);
        }
        log.error("Gemini Pro Batch marked retry-required after terminal failure: jobId={}, reason={}", jobId, reason);
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
    public void updateScene(Long jobId, int index, String text, String subtitleText, String section, String mode) {
        if ("caption_only".equalsIgnoreCase(mode)
                || "image_only".equalsIgnoreCase(mode)
                || "text_and_image".equalsIgnoreCase(mode)) {
            updateSceneV2(jobId, index, text, subtitleText, section, mode);
            return;
        }
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
            sceneDto.setText(text);
            sceneDto.setPromptKo(text);
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
            String characterPosesDir = null;  // [S2-4]
            String characterProfileId = job.getCharacterOverride() != null && !job.getCharacterOverride().isBlank()
                    ? job.getCharacterOverride() : job.getChannelId();
            if (characterProfileId != null) {
                ChannelProfile profile = channelProfileRepository.findById(characterProfileId).orElse(null);
                if (profile != null) {
                    characterImagePath = profile.getCharacterImagePath();
                    characterStylePrompt = profile.getCharacterStylePrompt();
                    characterPosesDir = profile.getCharacterPosesDir();
                }
            }

            // 이미지 재생성은 sceneDto의 (업데이트되었거나 기존의) prompt를 기준으로 호출
            String imageInstruction = text != null && !text.isBlank()
                    ? text
                    : (sceneDto.getPromptEn() != null && !sceneDto.getPromptEn().isBlank()
                        ? sceneDto.getPromptEn()
                        : sceneDto.getPrompt());
            fastApiClient.generateSingleImage(jobId, index, imageInstruction, sceneDto.getSection(), characterImagePath, characterStylePrompt, characterPosesDir);
            log.info("씬 이미지 재생성 요청 완료: jobId={}, index={}, section={}, mode={}", jobId, index, sceneDto.getSection(), mode);
        } else {
            log.info("씬 텍스트 수정 완료 (이미지 유지): jobId={}, index={}", jobId, index);
        }
    }

    /**
     * Three deliberately separate editor actions:
     * - caption_only updates only the rendered subtitle override;
     * - image_only reuses the stored English prompt unchanged;
     * - text_and_image makes a fresh English prompt from the Korean source and
     *   then redraws the image.
     */
    private void updateSceneV2(Long jobId, int index, String text, String subtitleText,
                               String section, String mode) {
        Asset target = null;
        SceneImageDto scene = null;
        for (Asset asset : assetRepository.findByJobIdAndAssetType(jobId, AssetType.SCENE_IMAGE)) {
            try {
                SceneImageDto parsed = objectMapper.readValue(asset.getMetaJson(), SceneImageDto.class);
                if (parsed.getIndex() != null && parsed.getIndex() == index) {
                    target = asset;
                    scene = parsed;
                    break;
                }
            } catch (Exception ignored) {
                // Keep looking through legacy/malformed scene records.
            }
        }
        if (target == null || scene == null) {
            throw new IllegalArgumentException("Scene image not found: index=" + index);
        }

        if ("caption_only".equalsIgnoreCase(mode)) {
            if (subtitleText == null || subtitleText.isBlank()) {
                throw new IllegalArgumentException("Subtitle text is required.");
            }
            scene.setSubtitleText(subtitleText.trim());
            target.setMetaJson(safeJson(scene));
            assetRepository.save(target);
            log.info("Scene subtitle updated without image regeneration: jobId={}, index={}", jobId, index);
            return;
        }

        if ("text_and_image".equalsIgnoreCase(mode)) {
            if (text == null || text.isBlank()) {
                throw new IllegalArgumentException("Korean source text is required.");
            }
            scene.setText(text.trim());
            scene.setPromptKo(text.trim());
        }
        if (section != null && !section.isBlank()) {
            scene.setSection(section);
        }

        VideoJob job = jobRepository.findById(jobId)
                .orElseThrow(() -> new RuntimeException("Job not found: " + jobId));
        String characterImagePath = null;
        String characterStylePrompt = null;
        String characterPosesDir = null;
        String profileId = job.getCharacterOverride() != null && !job.getCharacterOverride().isBlank()
                ? job.getCharacterOverride() : job.getChannelId();
        if (profileId != null) {
            ChannelProfile profile = channelProfileRepository.findById(profileId).orElse(null);
            if (profile != null) {
                characterImagePath = profile.getCharacterImagePath();
                characterStylePrompt = profile.getCharacterStylePrompt();
                characterPosesDir = profile.getCharacterPosesDir();
            }
        }

        String approvedEnglishPrompt = "image_only".equalsIgnoreCase(mode) ? scene.getPromptEn() : null;
        SceneImageDto rendered = fastApiClient.regenerateSceneImage(
                jobId, index, scene.getText(), approvedEnglishPrompt, scene.getSection(),
                characterImagePath, characterStylePrompt, characterPosesDir);
        if (rendered.getImagePath() != null && !rendered.getImagePath().isBlank()) {
            scene.setImagePath(rendered.getImagePath());
            target.setLocalPath(rendered.getImagePath());
        }
        if (rendered.getPromptEn() != null && !rendered.getPromptEn().isBlank()) {
            scene.setPromptEn(rendered.getPromptEn());
            scene.setPrompt(rendered.getPromptEn());
        }
        target.setMetaJson(safeJson(scene));
        assetRepository.save(target);
        log.info("Scene image updated: jobId={}, index={}, mode={}", jobId, index, mode);
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
        
        // [BUG FIX] Shift indices of all assets with index > targetIndex by 1.
        // MUST iterate in DESCENDING order so that e.g. index=3 becomes 4 BEFORE
        // index=2 becomes 3; otherwise the former index=3 and the newly-shifted
        // former index=2 both land on 3 at the same time, creating a duplicate.
        java.util.List<Asset> shiftTargets = new java.util.ArrayList<>();
        for (Asset asset : sortedAssets) {
            try {
                SceneImageDto dto = objectMapper.readValue(asset.getMetaJson(), SceneImageDto.class);
                if (dto.getIndex() != null && dto.getIndex() > index) {
                    shiftTargets.add(asset);
                }
            } catch (Exception e) {
                // ignore
            }
        }
        // Reverse so we shift highest indices first, avoiding transient duplicates.
        java.util.Collections.sort(shiftTargets, (a, b) -> {
            try {
                SceneImageDto dtoA = objectMapper.readValue(a.getMetaJson(), SceneImageDto.class);
                SceneImageDto dtoB = objectMapper.readValue(b.getMetaJson(), SceneImageDto.class);
                return Integer.compare(dtoB.getIndex(), dtoA.getIndex()); // descending
            } catch (Exception e) { return 0; }
        });
        for (Asset asset : shiftTargets) {
            try {
                SceneImageDto dto = objectMapper.readValue(asset.getMetaJson(), SceneImageDto.class);
                dto.setIndex(dto.getIndex() + 1);
                asset.setMetaJson(objectMapper.writeValueAsString(dto));
                assetRepository.save(asset);
            } catch (Exception e) {
                log.warn("씬 인덱스 시프트 중 오류: {}", e.getMessage());
            }
        }

        // Update target asset (part 1)
        targetDto.setPrompt(part1);
        targetDto.setText(part1);   // keep text in sync so rebuild() can reconstruct the script
        double origDuration = targetDto.getDuration() != null ? targetDto.getDuration() : 10.0;
        double origStart = targetDto.getStart() != null ? targetDto.getStart() : 0.0;

        targetDto.setDuration(origDuration / 2.0);
        targetAsset.setMetaJson(safeJson(targetDto));
        assetRepository.save(targetAsset);

        // Create new asset (part 2) at index + 1
        SceneImageDto newDto = new SceneImageDto();
        newDto.setIndex(index + 1);
        newDto.setPrompt(part2);
        newDto.setText(part2);      // populate text so rebuild() sees correct narration
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

    /**
     * Once a scene has an explicit value, the renderer uses only explicitly
     * selected scenes for Kling. The worker still enforces the first-minute cap.
     */
    @Transactional
    public void setSceneKling(Long jobId, int index, boolean enabled) {
        for (Asset asset : assetRepository.findByJobIdAndAssetType(jobId, AssetType.SCENE_IMAGE)) {
            try {
                SceneImageDto dto = objectMapper.readValue(asset.getMetaJson(), SceneImageDto.class);
                if (dto.getIndex() != null && dto.getIndex() == index) {
                    dto.setUseKling(enabled);
                    asset.setMetaJson(safeJson(dto));
                    assetRepository.save(asset);
                    log.info("Kling scene setting saved: jobId={}, index={}, enabled={}", jobId, index, enabled);
                    return;
                }
            } catch (Exception ignored) {
                // Continue searching assets with malformed legacy metadata.
            }
        }
        throw new IllegalArgumentException("해당 씬 이미지를 찾을 수 없습니다: index=" + index);
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
