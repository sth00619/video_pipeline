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
        saveUploadedTranscript(jobId, result);

        costService.record(jobId, "WHISPER_STT", BigDecimal.ZERO, "USD", "쇼츠 분석");
        log.info("쇼츠 분석 완료: jobId={}", jobId);
        return result;
    }

    private void saveUploadedTranscript(Long jobId, ShortsAnalyzeResponse result) {
        try {
            Map<String, Object> meta = new LinkedHashMap<>();
            meta.put("transcript", result.getTranscript() != null ? result.getTranscript() : "");
            meta.put("total_duration", result.getTotalDuration());
            meta.put("words", result.getWords() != null ? result.getWords() : List.of());
            meta.put("segments", result.getTranscriptSegments() != null ? result.getTranscriptSegments() : List.of());
            meta.put("source_video_path", result.getSourceVideoPath());
            assetRepository.save(Asset.builder()
                    .jobId(jobId)
                    .assetType(AssetType.TRANSCRIPT)
                    .localPath(result.getSourceVideoPath())
                    .metaJson(objectMapper.writeValueAsString(meta))
                    .build());
            assetRepository.save(Asset.builder()
                    .jobId(jobId)
                    .assetType(AssetType.SOURCE_VIDEO)
                    .localPath(result.getSourceVideoPath())
                    .metaJson("{\"source\":\"uploaded_shorts\"}")
                    .build());
        } catch (Exception e) {
            log.warn("Failed to persist uploaded Shorts transcript: {}", e.getMessage());
        }
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

        String sourcePath = resolveSourceVideoPath(job, jobId);
        request = normalizeSegments(sourcePath, request);

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
            scenes.addAll(cleanNarrationScenes(customScenes));
        } else {
            List<Asset> sceneAssets = assetRepository.findByJobIdAndAssetType(jobId, AssetType.SCENE_IMAGE);
            if (sceneAssets.isEmpty()) {
                Optional<Asset> transcriptAsset = assetRepository
                        .findTopByJobIdAndAssetTypeOrderByCreatedAtDesc(jobId, AssetType.TRANSCRIPT);
                if (transcriptAsset.isEmpty()) {
                    throw new IllegalStateException("No scene images or uploaded transcript are available.");
                }
                try {
                    Map<String, Object> transcriptMeta = objectMapper.readValue(
                            transcriptAsset.get().getMetaJson(), new TypeReference<>() {});
                    Object rawSegments = transcriptMeta.get("segments");
                    if (rawSegments instanceof List<?> items) {
                        int fallbackIndex = 1;
                        for (Object item : items) {
                            Map<String, Object> source = objectMapper.convertValue(item, new TypeReference<>() {});
                            Map<String, Object> scene = new HashMap<>();
                            scene.put("index", source.getOrDefault("index", fallbackIndex++));
                            scene.put("text", source.getOrDefault("text", ""));
                            scene.put("start", ((Number) source.getOrDefault("start", 0.0)).doubleValue());
                            scene.put("duration", ((Number) source.getOrDefault("duration", 0.0)).doubleValue());
                            scenes.add(scene);
                        }
                    }
                } catch (Exception e) {
                    log.warn("Uploaded transcript parsing failed: {}", e.getMessage());
                }
                if (scenes.isEmpty()) {
                    throw new IllegalStateException("Uploaded video transcript has no usable timed segments.");
                }
            }

            for (Asset asset : sceneAssets) {
                try {
                    Map<String, Object> meta = objectMapper.readValue(asset.getMetaJson(), new TypeReference<>() {});
                    Map<String, Object> scene = new HashMap<>();
                scene.put("index", meta.get("index"));
                // `prompt` is an English image-generation instruction, not narration.
                // Do not let it enter the Shorts timeline or keyword analysis.
                String text = meta.get("text") != null ? meta.get("text").toString() : "";
                scene.put("text", text);
                scene.put("start", meta.get("start") != null ? ((Number) meta.get("start")).doubleValue() : 0.0);
                scene.put("duration", meta.get("duration") != null ? ((Number) meta.get("duration")).doubleValue() : 15.0);
                if (isKoreanNarration(text)) scenes.add(scene);
            } catch (Exception e) {
                log.warn("씬 파싱 실패: {}", e.getMessage());
            }
        }
        }

        VideoJob job = jobRepository.findById(jobId)
                .orElseThrow(() -> new RuntimeException("Job not found: " + jobId));
        String sourcePath = resolveSourceVideoPath(job, jobId);
        // For a generated longform, TTS chunks are the authoritative narration
        // timestamps. They replace image-scene estimates when available.
        List<Map<String, Object>> ttsTimeline = loadTimedTtsScenes(jobId);
        if (!ttsTimeline.isEmpty()) scenes = ttsTimeline;
        scenes = cleanNarrationScenes(scenes);
        if (scenes.isEmpty()) {
            throw new IllegalStateException("No usable Korean narration was found. Upload analysis or TTS generation must finish first.");
        }
        List<Map<String, Object>> timedScenes = fastApiClient.normalizeShortsScenes(sourcePath, scenes);
        Map<String, Object> result = fastApiClient.extractShortsScenarios(jobId, timedScenes);
        // Return the repaired timeline so the web client can immediately cut
        // the scenario/keyword selection without relying on stale image assets.
        result.put("timeline_scenes", timedScenes);
        try {
            assetRepository.save(Asset.builder()
                    .jobId(jobId)
                    .assetType(AssetType.SHORTS_SCENARIO)
                    .metaJson(objectMapper.writeValueAsString(result))
                    .build());
        } catch (Exception e) {
            log.warn("Failed to save Shorts scenario result: {}", e.getMessage());
        }
        return result;
    }

    /** Keep image prompts out of spoken-text workflows. */
    private List<Map<String, Object>> cleanNarrationScenes(List<Map<String, Object>> rawScenes) {
        if (rawScenes == null) return new ArrayList<>();
        List<Map<String, Object>> cleaned = new ArrayList<>();
        int nextIndex = 1;
        for (Map<String, Object> raw : rawScenes) {
            if (raw == null) continue;
            String text = String.valueOf(raw.getOrDefault("text", "")).trim();
            if (text.startsWith("#")) continue;
            text = text.replaceFirst("^[#\\-—\\s]+", "").trim();
            if (!isKoreanNarration(text)) continue;
            Map<String, Object> scene = new LinkedHashMap<>();
            scene.put("index", nextIndex++);
            scene.put("text", text);
            double start = asDouble(raw.get("start"), 0.0);
            double duration = asDouble(raw.get("duration"), 0.0);
            if (duration <= 0 && raw.get("end") != null) duration = Math.max(0.0, asDouble(raw.get("end"), start) - start);
            scene.put("start", start);
            scene.put("duration", duration);
            cleaned.add(scene);
        }
        return cleaned;
    }

    private List<Map<String, Object>> loadTimedTtsScenes(Long jobId) {
        Optional<Asset> asset = assetRepository.findTopByJobIdAndAssetTypeOrderByCreatedAtDesc(jobId, AssetType.TTS_AUDIO);
        if (asset.isEmpty()) return List.of();
        try {
            Map<String, Object> meta = objectMapper.readValue(asset.get().getMetaJson(), new TypeReference<>() {});
            Object raw = meta.get("chunks");
            if (!(raw instanceof List<?> items)) return List.of();
            List<Map<String, Object>> chunks = new ArrayList<>();
            for (Object item : items) chunks.add(objectMapper.convertValue(item, new TypeReference<Map<String, Object>>() {}));
            return groupNarrationScenes(cleanNarrationScenes(chunks));
        } catch (Exception e) {
            log.warn("TTS timing parsing failed: {}", e.getMessage());
            return List.of();
        }
    }

    /** Keep UI cards meaningful while retaining exact TTS timing. */
    private List<Map<String, Object>> groupNarrationScenes(List<Map<String, Object>> chunks) {
        List<Map<String, Object>> grouped = new ArrayList<>();
        StringBuilder text = new StringBuilder();
        double start = 0.0, end = 0.0;
        int index = 1;
        for (Map<String, Object> chunk : chunks) {
            String current = String.valueOf(chunk.get("text"));
            double currentStart = asDouble(chunk.get("start"), end);
            double currentEnd = currentStart + Math.max(0.0, asDouble(chunk.get("duration"), 0.0));
            if (text.length() == 0) start = currentStart;
            if (text.length() > 0 && ((currentEnd - start) > 9.5 || text.length() + current.length() > 115)) {
                grouped.add(timedScene(index++, text.toString(), start, Math.max(0.05, end - start)));
                text.setLength(0);
                start = currentStart;
            }
            if (text.length() > 0) text.append(' ');
            text.append(current);
            end = Math.max(end, currentEnd);
        }
        if (text.length() > 0) grouped.add(timedScene(index, text.toString(), start, Math.max(0.05, end - start)));
        return grouped;
    }

    private Map<String, Object> timedScene(int index, String text, double start, double duration) {
        Map<String, Object> scene = new LinkedHashMap<>();
        scene.put("index", index); scene.put("text", text);
        scene.put("start", start); scene.put("duration", duration);
        return scene;
    }

    private boolean isKoreanNarration(String text) {
        if (text == null || text.isBlank() || text.startsWith("#") || text.startsWith("[")) return false;
        String lower = text.toLowerCase(Locale.ROOT);
        if (lower.contains("2d digital") || lower.contains("comic illustration") || lower.contains("no readable text")
                || lower.contains("scene:") || lower.contains("action:") || lower.contains("camera:")) return false;
        return text.chars().filter(ch -> ch >= 0xAC00 && ch <= 0xD7A3).count() >= 2;
    }

    private double asDouble(Object value, double fallback) {
        if (value instanceof Number number) return number.doubleValue();
        try { return value == null ? fallback : Double.parseDouble(value.toString()); }
        catch (NumberFormatException ignored) { return fallback; }
    }

    @Transactional
    public List<ShortClipInfo> confirmMerge(Long jobId, ShortsConfirmRequest request, String username) {
        VideoJob job = jobRepository.findById(jobId)
                .orElseThrow(() -> new RuntimeException("Job not found: " + jobId));

        String sourcePath = resolveSourceVideoPath(job, jobId);
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

        request = normalizeSegments(sourcePath, request);
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

    private String resolveSourceVideoPath(VideoJob job, Long jobId) {
        if (job.getSourceVideoPath() != null && !job.getSourceVideoPath().isBlank()) {
            return job.getSourceVideoPath();
        }
        if (job.getOutputPath() != null && !job.getOutputPath().isBlank()) {
            return job.getOutputPath();
        }
        for (AssetType type : List.of(AssetType.LONGFORM_VIDEO, AssetType.SOURCE_VIDEO)) {
            Optional<Asset> asset = assetRepository.findTopByJobIdAndAssetTypeOrderByCreatedAtDesc(jobId, type);
            if (asset.isPresent() && asset.get().getLocalPath() != null && !asset.get().getLocalPath().isBlank()) {
                return asset.get().getLocalPath();
            }
        }
        throw new IllegalStateException("No source or longform video is available for Shorts creation.");
    }

    private ShortsConfirmRequest normalizeSegments(String sourcePath, ShortsConfirmRequest request) {
        List<Map<String, Object>> rawScenes = new ArrayList<>();
        for (ShortsSegmentDto segment : request.getSegments() != null ? request.getSegments() : List.<ShortsSegmentDto>of()) {
            Map<String, Object> scene = new LinkedHashMap<>();
            scene.put("index", segment.getIndex());
            scene.put("text", segment.getText() != null ? segment.getText() : "");
            scene.put("start", segment.getStart() != null ? segment.getStart() : 0.0);
            double duration = segment.getDuration() != null
                    ? segment.getDuration()
                    : ((segment.getEnd() != null && segment.getStart() != null) ? segment.getEnd() - segment.getStart() : 0.0);
            scene.put("duration", Math.max(0.0, duration));
            rawScenes.add(scene);
        }
        List<Map<String, Object>> normalized = fastApiClient.normalizeShortsScenes(sourcePath, rawScenes);
        List<ShortsSegmentDto> segments = new ArrayList<>();
        for (Map<String, Object> scene : normalized) {
            ShortsSegmentDto segment = new ShortsSegmentDto();
            segment.setIndex(((Number) scene.get("index")).intValue());
            segment.setText(String.valueOf(scene.getOrDefault("text", "")));
            segment.setStart(((Number) scene.get("start")).doubleValue());
            segment.setEnd(((Number) scene.get("end")).doubleValue());
            segment.setDuration(((Number) scene.get("duration")).doubleValue());
            segments.add(segment);
        }
        ShortsConfirmRequest normalizedRequest = new ShortsConfirmRequest();
        normalizedRequest.setSegments(segments);
        return normalizedRequest;
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
