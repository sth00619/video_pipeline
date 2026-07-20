package com.pipeline.video.service;

import com.pipeline.video.domain.*;
import com.pipeline.video.dto.*;
import com.pipeline.video.repository.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
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
        
        String characterImagePath = null;
        String characterStylePrompt = null;
        String loraModelId = null;
        String loraTriggerWord = null;
        Double loraScale = 1.0;
        if (job.getChannelId() != null) {
            ChannelProfile profile = channelProfileRepository.findById(job.getChannelId()).orElse(null);
            if (profile != null) {
                characterImagePath = profile.getCharacterImagePath();
                characterStylePrompt = profile.getCharacterStylePrompt();
                loraModelId = profile.getLoraModelId();
                loraTriggerWord = profile.getLoraTriggerWord();
                if (profile.getLoraScale() != null) {
                    loraScale = profile.getLoraScale().doubleValue();
                }
            }
        }
        
        String longformTitle = job.getTitle();
        if (longformMeta != null && longformMeta.containsKey("titles")) {
            List<String> titles = (List<String>) longformMeta.get("titles");
            if (titles != null && !titles.isEmpty()) longformTitle = titles.get(0);
        }
        
        String longformThumbPath = "/app/data/jobs/" + jobId + "/longform_thumbnail.png";
        String shortsThumbPath = "/app/data/jobs/" + jobId + "/shorts_thumbnail.png";
        
        try {
            fastApiClient.generateThumbnailImage(jobId, longformTitle, "longform", longformThumbPath, 
                                                 characterImagePath, characterStylePrompt,
                                                 loraModelId, loraTriggerWord, loraScale);
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
                                                     characterImagePath, characterStylePrompt,
                                                     loraModelId, loraTriggerWord, loraScale);
            } catch (Exception e) {
                log.error("쇼츠 썸네일 생성 실패: {}", e.getMessage());
            }
        }
        
        Map<String, String> thumbPaths = new java.util.HashMap<>();
        thumbPaths.put("longform_path", "/api/jobs/" + jobId + "/thumbnail/longform");
        thumbPaths.put("shorts_path", "/api/jobs/" + jobId + "/thumbnail/shorts");
        
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
