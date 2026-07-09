package com.pipeline.video.service;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.pipeline.video.domain.*;
import com.pipeline.video.dto.ShortClipInfo;
import com.pipeline.video.dto.ShortsAnalyzeResponse;
import com.pipeline.video.dto.ShortsConfirmRequest;
import com.pipeline.video.dto.ShortsSegmentDto;
import com.pipeline.video.repository.AssetRepository;
import com.pipeline.video.repository.VideoJobRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;

import java.io.File;
import java.math.BigDecimal;
import java.util.*;

@Service
@Slf4j
@RequiredArgsConstructor
public class ShortsService {

    private final VideoJobRepository jobRepository;
    private final AssetRepository assetRepository;
    private final FastApiClient fastApiClient;
    private final CostService costService;
    private final ObjectMapper objectMapper = new ObjectMapper();

    // ============================
    // AUTO/GUIDED: Whisper 분석
    // ============================
    @Transactional
    public ShortsAnalyzeResponse analyze(Long jobId, MultipartFile file,
                                          int shortsCount, String username) throws Exception {
        VideoJob job = jobRepository.findById(jobId)
                .orElseThrow(() -> new RuntimeException("Job not found: " + jobId));

        log.info("쇼츠 분석 시작: jobId={}, count={}, file={}",
                jobId, shortsCount, file.getOriginalFilename());

        ShortsAnalyzeResponse result = fastApiClient.analyzeShorts(file, shortsCount, jobId);

        job.setSourceVideoPath(result.getSourceVideoPath());
        job.setStatus(JobStatus.SHORTS_SEGMENTS_PENDING);
        jobRepository.save(job);

        costService.record(jobId, "WHISPER_STT", BigDecimal.ZERO, "USD", "쇼츠 분석");
        log.info("쇼츠 분석 완료: jobId={}", jobId);
        return result;
    }

    // ============================
    // MANUAL: 분석 없이 직접 구간 → 쇼츠 생성
    // ============================
    @Transactional
    public List<ShortClipInfo> cutDirect(Long jobId, MultipartFile file,
                                          String segmentsJson, String username) throws Exception {
        VideoJob job = jobRepository.findById(jobId)
                .orElseThrow(() -> new RuntimeException("Job not found: " + jobId));

        log.info("MANUAL 쇼츠 직접 생성: jobId={}", jobId);

        // 영상 저장 (/app/data/jobs/:id/ — fastapi_data 볼륨)
        String dir = "/app/data/jobs/" + jobId;
        new File(dir).mkdirs();
        String sourcePath = dir + "/source_manual.mp4";
        file.transferTo(new File(sourcePath));
        job.setSourceVideoPath(sourcePath);

        // JSON 구간 파싱 → ShortsSegmentDto 리스트
        List<Map<String, Object>> segMaps = objectMapper.readValue(
                segmentsJson, new TypeReference<>() {});

        ShortsConfirmRequest req = new ShortsConfirmRequest();
        List<ShortsSegmentDto> segs = new ArrayList<>();
        for (int i = 0; i < segMaps.size(); i++) {
            Map<String, Object> m = segMaps.get(i);
            ShortsSegmentDto s = new ShortsSegmentDto();
            s.setIndex(i + 1);
            s.setText(m.getOrDefault("label", "구간 " + (i + 1)).toString());
            s.setStart(((Number) m.get("start")).doubleValue());
            s.setEnd(((Number) m.get("end")).doubleValue());
            segs.add(s);
        }
        req.setSegments(segs);

        List<ShortClipInfo> clips = fastApiClient.cutShorts(jobId, sourcePath, req);
        saveClips(jobId, clips);

        job.setStatus(JobStatus.READY);
        jobRepository.save(job);
        costService.record(jobId, "FFMPEG_CUT", BigDecimal.ZERO, "USD",
                "MANUAL 쇼츠 " + clips.size() + "개");

        log.info("MANUAL 쇼츠 생성 완료: {}개", clips.size());
        return clips;
    }

    // ============================
    // AUTO/GUIDED: 구간 확정 → 쇼츠 생성
    // ============================
    @Transactional
    public List<ShortClipInfo> confirm(Long jobId, ShortsConfirmRequest request, String username) {
        VideoJob job = jobRepository.findById(jobId)
                .orElseThrow(() -> new RuntimeException("Job not found: " + jobId));

        String sourcePath = job.getSourceVideoPath();
        if (sourcePath == null || sourcePath.isBlank()) {
            Optional<Asset> lfAsset = assetRepository.findTopByJobIdAndAssetTypeOrderByCreatedAtDesc(jobId, AssetType.LONGFORM_VIDEO);
            if (lfAsset.isPresent()) {
                sourcePath = lfAsset.get().getLocalPath();
            }
        }
        if (sourcePath == null || sourcePath.isBlank())
            throw new IllegalStateException("원본 영상 또는 롱폼 영상 경로가 없습니다.");

        log.info("쇼츠 확정: jobId={}, segments={}개",
                jobId, request.getSegments().size());

        List<ShortClipInfo> clips = fastApiClient.cutShorts(jobId, sourcePath, request);
        saveClips(jobId, clips);

        job.setStatus(JobStatus.READY);
        jobRepository.save(job);

        log.info("쇼츠 확정 완료: {}개", clips.size());
        return clips;
    }

    @Transactional
    public Map<String, Object> extractScenarios(Long jobId, List<Map<String, Object>> customScenes, String username) {
        List<Map<String, Object>> scenes = new ArrayList<>();
        
        if (customScenes != null && !customScenes.isEmpty()) {
            scenes.addAll(customScenes);
        } else {
            List<Asset> sceneAssets = assetRepository.findByJobIdAndAssetType(jobId, AssetType.SCENE_IMAGE);
            if (sceneAssets.isEmpty()) {
                throw new IllegalStateException("씬 이미지 에셋이 존재하지 않으며 업로드된 씬 정보도 없습니다.");
            }

            for (Asset asset : sceneAssets) {
                try {
                    Map<String, Object> meta = objectMapper.readValue(asset.getMetaJson(), new TypeReference<>() {});
                    Map<String, Object> scene = new HashMap<>();
                scene.put("index", meta.get("index"));
                String text = meta.get("prompt") != null ? meta.get("prompt").toString() : "";
                scene.put("text", text);
                scene.put("start", meta.get("start") != null ? ((Number) meta.get("start")).doubleValue() : 0.0);
                scene.put("duration", meta.get("duration") != null ? ((Number) meta.get("duration")).doubleValue() : 15.0);
                scenes.add(scene);
            } catch (Exception e) {
                log.warn("씬 파싱 실패: {}", e.getMessage());
            }
        }
        }

        return fastApiClient.extractShortsScenarios(jobId, scenes);
    }

    @Transactional
    public List<ShortClipInfo> confirmMerge(Long jobId, ShortsConfirmRequest request, String username) {
        VideoJob job = jobRepository.findById(jobId)
                .orElseThrow(() -> new RuntimeException("Job not found: " + jobId));

        String sourcePath = job.getSourceVideoPath();
        if (sourcePath == null || sourcePath.isBlank()) {
            Optional<Asset> lfAsset = assetRepository.findTopByJobIdAndAssetTypeOrderByCreatedAtDesc(jobId, AssetType.LONGFORM_VIDEO);
            if (lfAsset.isPresent()) {
                sourcePath = lfAsset.get().getLocalPath();
            }
        }
        if (sourcePath == null || sourcePath.isBlank()) {
            throw new IllegalStateException("원본 영상 또는 롱폼 영상이 존재하지 않습니다.");
        }

        log.info("쇼츠 병합 확정: jobId={}, segments={}개", jobId, request.getSegments().size());

        String outputDir = "/app/data/jobs/" + jobId + "/shorts";
        new File(outputDir).mkdirs();
        String outputPath = outputDir + "/short_merged_" + System.currentTimeMillis() + ".mp4";

        List<Map<String, Object>> segmentMaps = new ArrayList<>();
        for (var s : request.getSegments()) {
            Map<String, Object> seg = new HashMap<>();
            seg.put("index", s.getIndex());
            seg.put("text", s.getText() != null ? s.getText() : "");
            seg.put("start", s.getStart());
            seg.put("end", s.getEnd());
            segmentMaps.add(seg);
        }

        ShortClipInfo clip = fastApiClient.cutMergeShorts(jobId, sourcePath, segmentMaps, outputPath);
        List<ShortClipInfo> clips = List.of(clip);
        saveClips(jobId, clips);

        job.setStatus(JobStatus.READY);
        jobRepository.save(job);

        log.info("쇼츠 병합 확정 완료");
        return clips;
    }

    private void saveClips(Long jobId, List<ShortClipInfo> clips) {
        for (ShortClipInfo clip : clips) {
            try {
                Asset asset = Asset.builder()
                        .jobId(jobId)
                        .assetType(AssetType.SHORT_CLIP)
                        .localPath(clip.getOutputPath())
                        .metaJson(objectMapper.writeValueAsString(clip))
                        .build();
                assetRepository.save(asset);
            } catch (Exception e) {
                log.error("Asset 저장 실패: {}", e.getMessage());
            }
        }
    }
}
