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
        if (sourcePath == null || sourcePath.isBlank())
            throw new IllegalStateException("원본 영상 경로 없음. 먼저 분석을 실행하세요.");

        log.info("쇼츠 확정: jobId={}, segments={}개",
                jobId, request.getSegments().size());

        List<ShortClipInfo> clips = fastApiClient.cutShorts(jobId, sourcePath, request);
        saveClips(jobId, clips);

        job.setStatus(JobStatus.READY);
        jobRepository.save(job);

        log.info("쇼츠 확정 완료: {}개", clips.size());
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
