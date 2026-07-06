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
import java.util.Map;
import java.util.HashMap;
import java.util.ArrayList;
import java.util.Comparator;
import com.pipeline.video.dto.SceneImageDto;
import com.pipeline.video.dto.TtsChunkDto;
import com.pipeline.video.dto.TtsGenerateResponse;

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

    @Transactional
    public LongformGenerateResponse rebuild(Long jobId, String username) {
        VideoJob job = jobRepository.findById(jobId)
                .orElseThrow(() -> new RuntimeException("Job not found: " + jobId));

        // 1. 모든 SCENE_IMAGE 에셋 조회 및 index 순서대로 정렬
        List<Asset> sceneAssets = assetRepository.findByJobIdAndAssetType(jobId, AssetType.SCENE_IMAGE);
        if (sceneAssets.isEmpty()) {
            throw new IllegalStateException("재조립할 씬 이미지 에셋이 존재하지 않습니다.");
        }

        List<SceneImageDto> scenes = new ArrayList<>();
        for (Asset a : sceneAssets) {
            try {
                SceneImageDto dto = objectMapper.readValue(a.getMetaJson(), SceneImageDto.class);
                scenes.add(dto);
            } catch (Exception e) {
                log.warn("씬 이미지 에셋 파싱 실패: {}", e.getMessage());
            }
        }
        scenes.sort(Comparator.comparing(SceneImageDto::getIndex));

        // 2. 각 씬의 prompt를 순서대로 이어붙여 새로운 전체 스크립트 작성
        StringBuilder fullScriptBuilder = new StringBuilder();
        for (SceneImageDto scene : scenes) {
            if (fullScriptBuilder.length() > 0) {
                fullScriptBuilder.append("\n");
            }
            fullScriptBuilder.append(scene.getPrompt());
        }
        String newScript = fullScriptBuilder.toString();

        // 3. SCRIPT 에셋 업데이트 (마지막 스크립트 상태 갱신)
        Asset finalScriptAsset = Asset.builder()
                .jobId(jobId)
                .assetType(AssetType.SCRIPT)
                .metaJson(safeJson(Map.of(
                        "script", newScript,
                        "final", true,
                        "char_count", newScript.length(),
                        "sections", List.of(),
                        "verified_facts", List.of()
                )))
                .build();
        assetRepository.save(finalScriptAsset);

        // 4. TTS 재생성 (gTTS + Whisper 호출)
        log.info("재조립을 위한 TTS 재생성 시작: jobId={}, scriptLength={}자", jobId, newScript.length());
        TtsGenerateResponse ttsResult = fastApiClient.generateTts(jobId, newScript, "default_ko");
        
        // TTS Asset 저장
        Asset ttsAsset = Asset.builder()
                .jobId(jobId)
                .assetType(AssetType.TTS_AUDIO)
                .localPath(ttsResult.getAudioPath())
                .metaJson(safeJson(ttsResult))
                .build();
        assetRepository.save(ttsAsset);

        // 5. [핵심 알고리즘] 새로운 TTS chunks 타이밍 정보를 바탕으로 각 씬의 start, duration 동적 매칭!
        List<TtsChunkDto> chunks = ttsResult.getChunks();
        if (chunks != null && !chunks.isEmpty()) {
            int chunkIdx = 0;
            double currentStart = 0.0;
            
            for (int i = 0; i < scenes.size(); i++) {
                SceneImageDto scene = scenes.get(i);
                String cleanPrompt = scene.getPrompt().replaceAll("[\\s\\p{Punct}]+", "");
                
                String cleanNextPrompt = "";
                if (i + 1 < scenes.size()) {
                    cleanNextPrompt = scenes.get(i + 1).getPrompt().replaceAll("[\\s\\p{Punct}]+", "");
                }
                
                double sceneDuration = 0.0;
                boolean foundFirst = false;
                
                while (chunkIdx < chunks.size()) {
                    TtsChunkDto chunk = chunks.get(chunkIdx);
                    String cleanChunkText = chunk.getText().replaceAll("[\\s\\p{Punct}]+", "");
                    
                    if (cleanChunkText.isEmpty()) {
                        chunkIdx++;
                        continue;
                    }
                    
                    // 다음 씬의 스크립트와 매칭되면 현재 씬 매칭 종료
                    if (!cleanNextPrompt.isEmpty() && cleanNextPrompt.contains(cleanChunkText)) {
                        break;
                    }
                    
                    if (!foundFirst) {
                        scene.setStart(chunk.getStart());
                        foundFirst = true;
                    }
                    sceneDuration += chunk.getDuration();
                    chunkIdx++;
                }
                
                if (!foundFirst) {
                    scene.setStart(currentStart);
                    scene.setDuration(15.0); // fallback
                } else {
                    scene.setDuration(sceneDuration);
                }
                
                currentStart = scene.getStart() + scene.getDuration();
                
                // 해당 SCENE_IMAGE 에셋 DB 업데이트
                for (Asset a : sceneAssets) {
                    try {
                        SceneImageDto dto = objectMapper.readValue(a.getMetaJson(), SceneImageDto.class);
                        if (dto.getIndex().equals(scene.getIndex())) {
                            a.setMetaJson(safeJson(scene));
                            assetRepository.save(a);
                            break;
                        }
                    } catch (Exception e) {
                        // ignore
                    }
                }
            }
        }

        // 6. 롱폼 영상 재조립 (FastAPI 호출)
        log.info("재조립을 위한 롱폼 인코딩 시작: jobId={}", jobId);
        
        // 새로 업데이트된 씬 에셋 목록을 다시 로드
        List<Asset> updatedSceneAssets = assetRepository.findByJobIdAndAssetType(jobId, AssetType.SCENE_IMAGE);
        updatedSceneAssets.sort((a, b) -> {
            try {
                SceneImageDto dtoA = objectMapper.readValue(a.getMetaJson(), SceneImageDto.class);
                SceneImageDto dtoB = objectMapper.readValue(b.getMetaJson(), SceneImageDto.class);
                return Integer.compare(dtoA.getIndex(), dtoB.getIndex());
            } catch (Exception e) {
                return 0;
            }
        });
        
        List<Asset> gifAssets = assetRepository.findByJobIdAndAssetType(jobId, AssetType.GIF_CLIP);

        String scenesJson = safeJson(updatedSceneAssets.stream()
                .map(Asset::getMetaJson).toList());
        String gifsJson = safeJson(gifAssets.stream()
                .map(Asset::getMetaJson).toList());

        LongformGenerateResponse result = fastApiClient.generateLongform(
                jobId, safeJson(ttsResult), scenesJson, gifsJson);

        // 7. LONGFORM_VIDEO 에셋 저장 및 job outputPath 업데이트
        Asset videoAsset = Asset.builder()
                .jobId(jobId)
                .assetType(AssetType.LONGFORM_VIDEO)
                .localPath(result.getVideoPath())
                .metaJson(safeJson(result))
                .build();
        assetRepository.save(videoAsset);

        job.setOutputPath(result.getVideoPath());
        jobRepository.save(job);

        // 비용 기록 (재조립 추가 비용)
        costService.record(jobId, "FFMPEG_REASSEMBLE", BigDecimal.ZERO, "USD",
                String.format("롱폼 재조립: %.0f초, %d씬", 
                        result.getDurationSeconds(), result.getSceneCount()));

        log.info("롱폼 동영상 재조립 완료: jobId={}, path={}", jobId, result.getVideoPath());
        return result;
    }
}
