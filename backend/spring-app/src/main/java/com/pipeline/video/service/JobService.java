package com.pipeline.video.service;

import com.pipeline.video.domain.*;
import com.pipeline.video.dto.*;
import com.pipeline.video.repository.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

import java.math.BigDecimal;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.stream.Collectors;

@Service
@RequiredArgsConstructor
@Slf4j
public class JobService {

    private final VideoJobRepository jobRepository;
    private final AssetRepository assetRepository;
    private final ChannelProfileRepository channelProfileRepository;
    private final CostLedgerRepository costLedgerRepository;
    private final ApprovalRepository approvalRepository;
    private final FastApiClient fastApiClient;
    private final CharacterAssetResolver characterAssetResolver;
    private final ThumbnailPersonResolver thumbnailPersonResolver;
    // [긴급 추가] 정지 버튼이 Temporal Workflow도 취소하도록 연결하기 위해 주입
    private final WorkflowOrchestrator workflowOrchestrator;
    private final ObjectMapper objectMapper = new ObjectMapper();

    @Transactional
    public JobResponse createJob(CreateJobRequest request, String username) {
        // category null이면 CUSTOM
        Category category = request.getCategory() != null ? request.getCategory() : Category.CUSTOM;

        // 영상 길이: null이면 20분 default
        Integer targetMinutes = request.getLongformTargetMinutes() != null
                ? request.getLongformTargetMinutes() : 20;

        Autonomy requestedAutonomy = request.getAutonomy() == Autonomy.AUTO
                ? Autonomy.AUTO : Autonomy.GUIDED;

        VideoJob job = VideoJob.builder()
                .title(request.getTitle())
                .keyword(request.getKeyword())
                .keywordPlanId(request.getKeywordPlanId())
                .category(category)
                .status(JobStatus.DRAFT)
                .autonomy(requestedAutonomy)
                .format(request.getFormat())
                .renderProfile(request.getRenderProfile())
                .makeShorts(request.isMakeShorts())
                .shortsCount(request.getShortsCount())
                .longformTargetMinutes(targetMinutes)
                .budgetCap(request.getBudgetCap())
                .costAccumulated(BigDecimal.ZERO)
                .policyJson(request.getPolicyJson())
                .channelId(request.getChannelId())
                .characterOverride(request.getCharacterOverride())
                .dataVisualsEnabled(request.isDataVisualsEnabled())
                .createdBy(username)
                .build();

        return JobResponse.from(jobRepository.save(job));
    }

    public List<JobResponse> getMyJobs(String username) {
        return jobRepository.findByCreatedByOrderByCreatedAtDesc(username)
                .stream().map(JobResponse::from).collect(Collectors.toList());
    }

    /** Resume a job that failed before any script asset was produced.
     *
     * The keyword selection remains valid, so the restarted workflow receives
     * the KEYWORD signal and resumes at GenerateScript rather than repeating
     * discovery or creating a second job.
     */
    @Transactional
    public JobResponse retryFromScript(Long jobId) {
        VideoJob job = jobRepository.findById(jobId)
                .orElseThrow(() -> new RuntimeException("Job not found: " + jobId));
        if (job.getStatus() != JobStatus.FAILED) {
            throw new IllegalStateException("Only failed jobs can be resumed. Current status: " + job.getStatus());
        }
        if (job.getKeyword() == null || job.getKeyword().isBlank()) {
            throw new IllegalStateException("A selected keyword is required before retrying the script.");
        }
        if (!assetRepository.findByJobIdAndAssetType(jobId, AssetType.SCRIPT).isEmpty()) {
            throw new IllegalStateException("A script already exists; resume from its current review stage instead.");
        }

        job.setStatus(JobStatus.SCRIPT_PENDING);
        VideoJob saved = jobRepository.save(job);
        Runnable resume = () -> {
            workflowOrchestrator.startPipeline(jobId);
            workflowOrchestrator.sendApproveSignal(jobId, GateName.KEYWORD.name());
        };
        if (TransactionSynchronizationManager.isSynchronizationActive()) {
            TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
                @Override
                public void afterCommit() {
                    resume.run();
                }
            });
        } else {
            resume.run();
        }
        log.info("Restarting failed job from script generation: jobId={}", jobId);
        return JobResponse.from(saved);
    }

    public JobResponse getJob(Long id) {
        return jobRepository.findById(id)
                .map(JobResponse::from)
                .orElseThrow(() -> new RuntimeException("Job not found: " + id));
    }

    public List<JobResponse> getAllJobs() {
        return jobRepository.findAll()
                .stream().map(JobResponse::from).collect(Collectors.toList());
    }

    @Transactional
    public JobResponse publishVideo(Long jobId) {
        VideoJob job = jobRepository.findById(jobId)
                .orElseThrow(() -> new RuntimeException("Job not found: " + jobId));

        Optional<Asset> existingMeta = assetRepository.findTopByJobIdAndAssetTypeOrderByCreatedAtDesc(jobId, AssetType.YOUTUBE_METADATA);
        if (existingMeta.isEmpty()) {
            generateYoutubePackage(jobId);
        }

        String mockYoutubeUrl = "https://youtu.be/mock_youtube_video_" + jobId + "_" + System.currentTimeMillis();
        job.setYoutubeUrl(mockYoutubeUrl);
        job.setStatus(JobStatus.PUBLISHED);
        jobRepository.save(job);
        
        log.info("유튜브 영상 퍼블리시 완료: jobId={}, url={}", jobId, mockYoutubeUrl);
        return JobResponse.from(job);
    }

    @Transactional
    @SuppressWarnings("unchecked")
    public void generateYoutubePackage(Long jobId) {
        VideoJob job = jobRepository.findById(jobId)
                .orElseThrow(() -> new RuntimeException("Job not found: " + jobId));
        
        log.info("유튜브 패키지(메타데이터, 썸네일) 생성 시작: jobId={}", jobId);
        
        Optional<Asset> scriptAssetOpt = assetRepository.findTopByJobIdAndAssetTypeOrderByCreatedAtDesc(jobId, AssetType.SCRIPT);
        if (scriptAssetOpt.isEmpty()) {
            log.warn("대본 에셋이 없어 유튜브 패키지 생성을 건너뜁니다. jobId={}", jobId);
            return;
        }
        
        String scriptText = "";
        try {
            ScriptGenerateResponse scriptDto = objectMapper.readValue(scriptAssetOpt.get().getMetaJson(), ScriptGenerateResponse.class);
            scriptText = scriptDto.getScript();
        } catch (Exception e) {
            scriptText = scriptAssetOpt.get().getMetaJson();
        }
        
        Map<String, Object> longformMeta = null;
        Map<String, Object> shortsMeta = null;
        try {
            longformMeta = fastApiClient.generateYoutubeMetadata(scriptText, false);
        } catch (Exception e) {
            log.error("롱폼 유튜브 메타데이터 생성 실패: {}", e.getMessage());
        }
        
        if (job.isMakeShorts()) {
            String shortsScriptText = scriptText;
            Optional<Asset> shortsScenarioOpt = assetRepository.findTopByJobIdAndAssetTypeOrderByCreatedAtDesc(jobId, AssetType.SHORTS_SCENARIO);
            if (shortsScenarioOpt.isPresent()) {
                shortsScriptText = shortsScenarioOpt.get().getMetaJson();
            }
            try {
                shortsMeta = fastApiClient.generateYoutubeMetadata(shortsScriptText, true);
            } catch (Exception e) {
                log.error("쇼츠 유튜브 메타데이터 생성 실패: {}", e.getMessage());
            }
        }
        
        Map<String, Object> youtubePackage = new java.util.HashMap<>();
        youtubePackage.put("longform", longformMeta);
        youtubePackage.put("shorts", shortsMeta);
        
        assetRepository.findTopByJobIdAndAssetTypeOrderByCreatedAtDesc(jobId, AssetType.YOUTUBE_METADATA)
                .ifPresent(assetRepository::delete);
        
        Asset metadataAsset = Asset.builder()
                .jobId(jobId)
                .assetType(AssetType.YOUTUBE_METADATA)
                .metaJson(safeJson(youtubePackage))
                .build();
        assetRepository.save(metadataAsset);
        
        CharacterAssetResolver.ResolvedCharacter character = characterAssetResolver.resolve(job);
        String referenceStyleProfile = job.getChannelId() == null || job.getChannelId().isBlank()
                ? "black_han_sans_v1"
                : channelProfileRepository.findById(job.getChannelId())
                    .map(ChannelProfile::getReferenceStyleProfile)
                    .filter(value -> value != null && !value.isBlank())
                    .orElse("black_han_sans_v1");
        List<Map<String, Object>> sceneCandidates = buildThumbnailSceneCandidates(jobId);
        Map<String, Object> thumbnailBrief = loadThumbnailBrief(scriptAssetOpt.get().getMetaJson(), longformTitleFallback(job));
        Map<String, Object> characterIdentity = new java.util.HashMap<>();
        characterIdentity.put("profile_id", character.profileId());
        characterIdentity.put("identity_hash", character.identityHash());
        characterIdentity.put("character_key", character.profileId());
        
        String longformTitle = job.getTitle();
        if (longformMeta != null && longformMeta.containsKey("titles")) {
            List<String> titles = (List<String>) longformMeta.get("titles");
            if (titles != null && !titles.isEmpty()) longformTitle = titles.get(0);
        }
        List<Map<String, Object>> personPhotos = thumbnailPersonResolver.resolve(
                thumbnailBrief, longformTitle, job.getKeyword(), scriptText
        );
        log.info("자동 썸네일용 승인 인물 사진 연결: jobId={}, count={}", jobId, personPhotos.size());
        
        String longformThumbPath = "/app/data/jobs/" + jobId + "/longform_thumbnail.png";
        String shortsThumbPath = "/app/data/jobs/" + jobId + "/shorts_thumbnail.png";
        
        Map<String, Object> longformThumbnailResult = java.util.Map.of();
        try {
            longformThumbnailResult = fastApiClient.generateThumbnailImage(jobId, longformTitle, "longform", longformThumbPath,
                    character.imagePath(), character.stylePrompt(), character.loraModelId(), character.loraTriggerWord(),
                    character.loraScale() == null ? 1.0 : character.loraScale().doubleValue(),
                    sceneCandidates, thumbnailBrief, characterIdentity, personPhotos, character.watermarkPath(),
                    referenceStyleProfile, null, false);
        } catch (Exception e) {
            log.error("롱폼 썸네일 생성 실패: {}", e.getMessage());
        }
        
        if (job.isMakeShorts()) {
            String shortsTitle = longformTitle;
            if (shortsMeta != null && shortsMeta.containsKey("titles")) {
                List<String> sTitles = (List<String>) shortsMeta.get("titles");
                if (sTitles != null && !sTitles.isEmpty()) shortsTitle = sTitles.get(0);
            }
            try {
                fastApiClient.generateThumbnailImage(jobId, shortsTitle, "shorts", shortsThumbPath,
                        character.imagePath(), character.stylePrompt(), character.loraModelId(), character.loraTriggerWord(),
                        character.loraScale() == null ? 1.0 : character.loraScale().doubleValue(),
                        sceneCandidates, thumbnailBrief, characterIdentity, personPhotos, character.watermarkPath(),
                        referenceStyleProfile, null, false);
            } catch (Exception e) {
                log.error("쇼츠 썸네일 생성 실패: {}", e.getMessage());
            }
        }
        
        Map<String, Object> thumbPaths = new java.util.HashMap<>();
        thumbPaths.put("longform_path", "/api/jobs/" + jobId + "/thumbnail/longform");
        thumbPaths.put("shorts_path", "/api/jobs/" + jobId + "/thumbnail/shorts");
        thumbPaths.put("longform_result", longformThumbnailResult);
        thumbPaths.put("character_identity", characterIdentity);
        thumbPaths.put("source_mode", sceneCandidates.isEmpty() ? "ai_fallback" : "scene");
        thumbPaths.put("person_matches", personPhotos.stream().map(photo -> java.util.Map.of(
                "person_id", String.valueOf(photo.getOrDefault("person_id", "")),
                "person_name", String.valueOf(photo.getOrDefault("person_name", "")),
                "photo_id", String.valueOf(photo.getOrDefault("photo_id", "")),
                "match_term", String.valueOf(photo.getOrDefault("match_term", "")),
                "match_source", String.valueOf(photo.getOrDefault("match_source", ""))
        )).toList());
        
        assetRepository.findTopByJobIdAndAssetTypeOrderByCreatedAtDesc(jobId, AssetType.THUMBNAIL_IMAGE)
                .ifPresent(assetRepository::delete);
        
        Asset thumbnailAsset = Asset.builder()
                .jobId(jobId)
                .assetType(AssetType.THUMBNAIL_IMAGE)
                .localPath(longformThumbPath)
                .metaJson(safeJson(thumbPaths))
                .build();
        assetRepository.save(thumbnailAsset);
        
        log.info("유튜브 패키지 생성 완료: jobId={}", jobId);
    }

    private String longformTitleFallback(VideoJob job) {
        return job.getTitle() == null ? "시장 핵심 이슈" : job.getTitle();
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> loadThumbnailBrief(String scriptMetaJson, String fallbackTitle) {
        try {
            Map<String, Object> parsed = objectMapper.readValue(scriptMetaJson, Map.class);
            Object brief = parsed.get("thumbnail_brief");
            if (brief instanceof Map<?, ?> map) return new java.util.HashMap<>((Map<String, Object>) map);
        } catch (Exception exception) {
            log.warn("썸네일 브리프 복원 실패: {}", exception.getMessage());
        }
        Map<String, Object> fallback = new java.util.HashMap<>();
        fallback.put("hook_line", "{y:" + fallbackTitle + "}");
        fallback.put("punch_line", "{y:핵심 정리}");
        fallback.put("source_scene_ids", java.util.List.of("0"));
        return fallback;
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> buildThumbnailSceneCandidates(Long jobId) {
        List<Map<String, Object>> candidates = new java.util.ArrayList<>();
        Optional<Asset> manifestAsset = assetRepository.findTopByJobIdAndAssetTypeOrderByCreatedAtDesc(jobId, AssetType.ASSEMBLY_MANIFEST);
        if (manifestAsset.isPresent() && manifestAsset.get().getLocalPath() != null) {
            try {
                String payload = Files.readString(Path.of(manifestAsset.get().getLocalPath()));
                Map<String, Object> manifest = objectMapper.readValue(payload, Map.class);
                Object rawScenes = manifest.get("scenes");
                if (rawScenes instanceof List<?> scenes) {
                    for (Object value : scenes) {
                        if (!(value instanceof Map<?, ?> rawScene)) continue;
                        Map<String, Object> candidate = new java.util.HashMap<>((Map<String, Object>) rawScene);
                        if (!Boolean.TRUE.equals(candidate.get("used_in_final_video"))) continue;
                        Object imagePath = candidate.get("image_path");
                        if (!(imagePath instanceof String path) || path.isBlank()) continue;
                        candidate.putIfAbsent("scene_id", String.valueOf(candidate.getOrDefault("index", candidates.size())));
                        candidates.add(candidate);
                    }
                }
            } catch (Exception exception) {
                log.warn("조립 매니페스트에서 썸네일 후보 복원 실패: {}", exception.getMessage());
            }
            if (!candidates.isEmpty()) return candidates;
        }
        for (Asset asset : assetRepository.findByJobIdAndAssetType(jobId, AssetType.SCENE_IMAGE)) {
            try {
                Map<String, Object> scene = objectMapper.readValue(asset.getMetaJson(), Map.class);
                String path = scene.get("image_path") instanceof String value ? value : asset.getLocalPath();
                if (path == null || path.isBlank()) continue;
                Map<String, Object> candidate = new java.util.HashMap<>(scene);
                candidate.put("image_path", path);
                candidate.put("used_in_final_video", true);
                candidate.putIfAbsent("scene_id", String.valueOf(scene.getOrDefault("index", candidates.size())));
                candidates.add(candidate);
            } catch (Exception exception) {
                log.warn("썸네일 후보 씬 메타데이터 복원 실패: assetId={}, error={}", asset.getId(), exception.getMessage());
            }
        }
        return candidates;
    }

    /**
     * Promotes an already-rendered, scene-backed thumbnail candidate.  No
     * image generation runs here: the selected file is copied to the legacy
     * primary path consumed by the YouTube package and download endpoint.
     */
    @Transactional
    public Map<String, Object> selectThumbnailVariant(Long jobId, String format, int variant) {
        if (!"longform".equals(format) && !"shorts".equals(format)) {
            throw new IllegalArgumentException("thumbnail format must be longform or shorts");
        }
        if (variant < 1 || variant > 3) {
            throw new IllegalArgumentException("thumbnail variant must be between 1 and 3");
        }
        String baseName = format + "_thumbnail";
        Path jobDirectory = Path.of("/app/data/jobs", String.valueOf(jobId));
        Path source = jobDirectory.resolve(baseName + "_v" + variant + ".png");
        if (!Files.isRegularFile(source) && variant == 1) source = jobDirectory.resolve(baseName + ".png");
        Path target = jobDirectory.resolve(baseName + ".png");
        if (!Files.isRegularFile(source)) {
            throw new IllegalStateException("thumbnail variant not found: " + variant);
        }
        try {
            if (!source.equals(target)) {
                Files.copy(source, target, StandardCopyOption.REPLACE_EXISTING);
            }
        } catch (java.io.IOException exception) {
            throw new IllegalStateException("thumbnail variant promotion failed", exception);
        }

        assetRepository.findTopByJobIdAndAssetTypeOrderByCreatedAtDesc(jobId, AssetType.THUMBNAIL_IMAGE)
                .ifPresent(asset -> {
                    Map<String, Object> metadata;
                    try {
                        metadata = objectMapper.readValue(asset.getMetaJson(), Map.class);
                    } catch (Exception ignored) {
                        metadata = new java.util.HashMap<>();
                    }
                    metadata.put(format + "_selected_variant", variant);
                    metadata.put(format + "_path", "/api/jobs/" + jobId + "/thumbnail/" + format);
                    asset.setLocalPath(target.toString());
                    asset.setMetaJson(safeJson(metadata));
                    assetRepository.save(asset);
                });
        return Map.of("format", format, "selected_variant", variant, "path", target.toString());
    }

    /** Re-render only the approved thumbnail candidates; script/video assets stay untouched. */
    @Transactional
    public Map<String, Object> regenerateThumbnail(Long jobId, String format, String preset) {
        if (!"longform".equals(format) && !"shorts".equals(format)) {
            throw new IllegalArgumentException("thumbnail format must be longform or shorts");
        }
        if (preset != null && !preset.isBlank() && !List.of("person_led", "mascot_led", "chart_led").contains(preset)) {
            throw new IllegalArgumentException("unsupported thumbnail preset");
        }
        VideoJob job = jobRepository.findById(jobId)
                .orElseThrow(() -> new IllegalArgumentException("Job not found"));
        Optional<Asset> scriptAsset = assetRepository.findTopByJobIdAndAssetTypeOrderByCreatedAtDesc(jobId, AssetType.SCRIPT);
        if (scriptAsset.isEmpty()) throw new IllegalStateException("thumbnail regeneration requires a script asset");
        List<Map<String, Object>> candidates = buildThumbnailSceneCandidates(jobId);
        if (candidates.isEmpty()) throw new IllegalStateException("thumbnail regeneration requires final-video scene candidates");

        Map<String, Object> brief = loadThumbnailBrief(scriptAsset.get().getMetaJson(), longformTitleFallback(job));
        String scriptText = scriptAsset.get().getMetaJson();
        CharacterAssetResolver.ResolvedCharacter character = characterAssetResolver.resolve(job);
        Map<String, Object> identity = new java.util.HashMap<>();
        identity.put("profile_id", character.profileId());
        identity.put("identity_hash", character.identityHash());
        identity.put("character_key", character.profileId());
        List<Map<String, Object>> people = thumbnailPersonResolver.resolve(brief, job.getTitle(), job.getKeyword(), scriptText);
        String styleProfile = job.getChannelId() == null || job.getChannelId().isBlank()
                ? "black_han_sans_v1"
                : channelProfileRepository.findById(job.getChannelId()).map(ChannelProfile::getReferenceStyleProfile)
                    .filter(value -> value != null && !value.isBlank()).orElse("black_han_sans_v1");
        Path jobDirectory = Path.of("/app/data/jobs", String.valueOf(jobId));
        String outputPath = jobDirectory.resolve(format + "_thumbnail.png").toString();
        archiveThumbnailVariants(jobDirectory, format);
        Map<String, Object> result = fastApiClient.generateThumbnailImage(
                jobId, job.getTitle(), format, outputPath,
                character.imagePath(), character.stylePrompt(), character.loraModelId(), character.loraTriggerWord(),
                character.loraScale() == null ? 1.0 : character.loraScale().doubleValue(),
                candidates, brief, identity, people, character.watermarkPath(), styleProfile, preset, true);

        assetRepository.findTopByJobIdAndAssetTypeOrderByCreatedAtDesc(jobId, AssetType.THUMBNAIL_IMAGE).ifPresent(asset -> {
            Map<String, Object> metadata;
            try { metadata = objectMapper.readValue(asset.getMetaJson(), Map.class); }
            catch (Exception ignored) { metadata = new java.util.HashMap<>(); }
            int version = ((Number) metadata.getOrDefault("thumbnail_regeneration_version", 0)).intValue() + 1;
            metadata.put("thumbnail_regeneration_version", version);
            metadata.put(format + "_result", result);
            metadata.put(format + "_selected_variant", ((Number) result.getOrDefault("selected_variant", 0)).intValue() + 1);
            asset.setMetaJson(safeJson(metadata));
            assetRepository.save(asset);
        });
        return Map.of("format", format, "result", result, "preset", preset == null ? "auto" : preset);
    }

    private void archiveThumbnailVariants(Path jobDirectory, String format) {
        try {
            Path archive = jobDirectory.resolve("thumbnail_history").resolve(format + "-" + System.currentTimeMillis());
            Files.createDirectories(archive);
            for (int variant = 1; variant <= 3; variant++) {
                String suffix = variant == 1 ? ".png" : "_v" + variant + ".png";
                Path source = jobDirectory.resolve(format + "_thumbnail" + suffix);
                if (Files.isRegularFile(source)) Files.copy(source, archive.resolve(source.getFileName()));
            }
        } catch (java.io.IOException exception) {
            throw new IllegalStateException("thumbnail history archive failed", exception);
        }
    }

    @Transactional
    public JobResponse stopJob(Long jobId, String username) {
        VideoJob job = jobRepository.findById(jobId)
                .orElseThrow(() -> new RuntimeException("Job not found: " + jobId));

        if (job.getStatus() == JobStatus.READY || job.getStatus() == JobStatus.PUBLISHED || job.getStatus() == JobStatus.FAILED) {
            log.info("Job {} is already in terminal state {}, skip stop request.", jobId, job.getStatus());
            return JobResponse.from(job);
        }

        log.info("Job {} 중지 요청 (by {}). 현재 상태: {}", jobId, username, job.getStatus());
        job.setStatus(JobStatus.FAILED);
        VideoJob savedJob = jobRepository.save(job);

        // [긴급 수정] 기존에는 FastAPI 워커에만 중지 명령을 보냈는데, Temporal
        // Workflow가 파이프라인 실행을 담당하게 된 지금은 Workflow 자체도
        // 취소해야 실제로 다음 단계(TTS/이미지/조립)로 안 넘어갑니다.
        // FastAPI stopJob()은 이미 실행 중인 개별 프로세스(ffmpeg 등)를 죽이는
        // 역할이고, Temporal cancelPipeline()은 "다음 단계로 진행하지 않게"
        // 막는 역할이라 둘 다 필요합니다.
        workflowOrchestrator.cancelPipeline(jobId);

        // FastAPI 워커에 중지 명령 전송
        fastApiClient.stopJob(jobId);

        return JobResponse.from(savedJob);
    }

    @Transactional
    public void deleteJob(Long jobId, String username) {
        VideoJob job = jobRepository.findById(jobId)
                .orElseThrow(() -> new RuntimeException("Job not found: " + jobId));

        if (job.getStatus() != JobStatus.DRAFT && job.getStatus() != JobStatus.READY && job.getStatus() != JobStatus.FAILED) {
            throw new IllegalStateException("진행 중인 작업(현재 상태: " + job.getStatus() + ")은 삭제할 수 없습니다. 먼저 중지해 주세요.");
        }

        log.info("Job {} 삭제 시작 (by {})", jobId, username);

        assetRepository.deleteByJobId(jobId);
        costLedgerRepository.deleteByJobId(jobId);
        approvalRepository.deleteByJobId(jobId);
        jobRepository.delete(job);

        // FastAPI 워커에 리소스 삭제 통지
        fastApiClient.deleteJob(jobId);

        log.info("Job {} 삭제 완료", jobId);
    }

    private String safeJson(Object obj) {
        try {
            return objectMapper.writeValueAsString(obj);
        } catch (Exception e) {
            return "{}";
        }
    }
}
