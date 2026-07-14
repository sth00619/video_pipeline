package com.pipeline.video.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.pipeline.video.dto.*;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.*;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.multipart.MultipartFile;

import java.io.*;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

@Service
@Slf4j
@RequiredArgsConstructor
public class FastApiClient {

    @Value("${fastapi.url:http://fastapi-workers:8001}")
    private String fastApiUrl;

    private final RestTemplate restTemplate;
    private final ObjectMapper objectMapper = new ObjectMapper();

    // Phase 2 — 쇼츠
    public ShortsAnalyzeResponse analyzeShorts(MultipartFile file, int shortsCount, Long jobId)
            throws IOException {
        String urlStr = String.format("%s/workers/shorts/analyze?shorts_count=%d&job_id=%d",
                fastApiUrl, shortsCount, jobId);
        String boundary = UUID.randomUUID().toString().replace("-", "");
        String fileName = file.getOriginalFilename() != null ? file.getOriginalFilename() : "video.mp4";
        byte[] fileBytes = file.getBytes();

        URL url = new URL(urlStr);
        HttpURLConnection conn = (HttpURLConnection) url.openConnection();
        conn.setRequestMethod("POST");
        conn.setDoOutput(true);
        conn.setConnectTimeout(10_000);
        conn.setReadTimeout(1_800_000); // 30분
        conn.setRequestProperty("Content-Type", "multipart/form-data; boundary=" + boundary);
        try (OutputStream os = conn.getOutputStream()) {
            String partHeader = "--" + boundary + "\r\n"
                    + "Content-Disposition: form-data; name=\"file\"; filename=\"" + fileName + "\"\r\n"
                    + "Content-Type: video/mp4\r\n\r\n";
            os.write(partHeader.getBytes(StandardCharsets.UTF_8));
            os.write(fileBytes);
            os.write(("\r\n--" + boundary + "--\r\n").getBytes(StandardCharsets.UTF_8));
            os.flush();
        }
        int code = conn.getResponseCode();
        InputStream is = code >= 200 && code < 300 ? conn.getInputStream() : conn.getErrorStream();
        String body = new String(is.readAllBytes(), StandardCharsets.UTF_8);
        if (code < 200 || code >= 300) throw new RuntimeException("FastAPI analyze 실패: " + code);
        return objectMapper.readValue(body, ShortsAnalyzeResponse.class);
    }

    @SuppressWarnings("unchecked")
    public List<Map<String, Object>> normalizeShortsScenes(String sourceVideoPath, List<Map<String, Object>> scenes) {
        try {
            Map<String, Object> bodyMap = new HashMap<>();
            bodyMap.put("source_video_path", sourceVideoPath);
            bodyMap.put("scenes", scenes);
            String responseBody = postJson(fastApiUrl + "/workers/shorts/normalize-scenes", bodyMap);
            Map<String, Object> response = objectMapper.readValue(responseBody, Map.class);
            Object normalized = response.get("scenes");
            return normalized instanceof List<?> list ? (List<Map<String, Object>>) list : List.of();
        } catch (Exception e) {
            throw new RuntimeException("FastAPI scene timeline normalization failed: " + e.getMessage(), e);
        }
    }

    @SuppressWarnings("unchecked")
    public List<ShortClipInfo> cutShorts(Long jobId, String sourceVideoPath, ShortsConfirmRequest request) {
        try {
            List<Map<String, Object>> segmentMaps = new ArrayList<>();
            for (var s : request.getSegments()) {
                Map<String, Object> seg = new HashMap<>();
                seg.put("index", s.getIndex());
                seg.put("text", s.getText() != null ? s.getText() : "");
                seg.put("start", s.getStart());
                seg.put("end", s.getEnd());
                segmentMaps.add(seg);
            }
            Map<String, Object> bodyMap = new HashMap<>();
            bodyMap.put("source_video_path", sourceVideoPath);
            bodyMap.put("segments", segmentMaps);
            bodyMap.put("job_id", jobId);
            String responseBody = postJson(fastApiUrl + "/workers/shorts/cut", bodyMap);
            Map<String, Object> response = objectMapper.readValue(responseBody, Map.class);
            List<Map<String, Object>> rawClips = (List<Map<String, Object>>) response.get("clips");
            if (rawClips == null) return List.of();
            List<ShortClipInfo> clips = new ArrayList<>();
            for (Map<String, Object> m : rawClips) {
                ShortClipInfo info = new ShortClipInfo();
                info.setIndex((Integer) m.get("index"));
                info.setText((String) m.get("text"));
                info.setStart(((Number) m.get("start")).doubleValue());
                info.setEnd(((Number) m.get("end")).doubleValue());
                info.setOutputPath((String) m.get("output_path"));
                clips.add(info);
            }
            return clips;
        } catch (Exception e) {
            throw new RuntimeException("FastAPI cut 오류: " + e.getMessage(), e);
        }
    }

    @SuppressWarnings("unchecked")
    public Map<String, Object> extractShortsScenarios(Long jobId, List<Map<String, Object>> scenes) {
        try {
            Map<String, Object> bodyMap = new HashMap<>();
            bodyMap.put("job_id", jobId);
            bodyMap.put("scenes", scenes);
            String responseBody = postJson(fastApiUrl + "/workers/shorts/extract-scenarios", bodyMap);
            return objectMapper.readValue(responseBody, Map.class);
        } catch (Exception e) {
            throw new RuntimeException("FastAPI extract scenarios 오류: " + e.getMessage(), e);
        }
    }

    @SuppressWarnings("unchecked")
    public ShortClipInfo cutMergeShorts(Long jobId, String sourceVideoPath, List<Map<String, Object>> segments, String outputPath) {
        try {
            Map<String, Object> bodyMap = new HashMap<>();
            bodyMap.put("source_video_path", sourceVideoPath);
            bodyMap.put("segments", segments);
            bodyMap.put("job_id", jobId);
            bodyMap.put("output_path", outputPath);
            String responseBody = postJson(fastApiUrl + "/workers/shorts/cut-merge", bodyMap);
            Map<String, Object> response = objectMapper.readValue(responseBody, Map.class);
            Map<String, Object> clipMap = (Map<String, Object>) response.get("clip");
            
            ShortClipInfo info = new ShortClipInfo();
            info.setIndex((Integer) clipMap.get("index"));
            info.setText((String) clipMap.get("text"));
            info.setStart(((Number) clipMap.get("start")).doubleValue());
            info.setEnd(((Number) clipMap.get("end")).doubleValue());
            info.setOutputPath((String) clipMap.get("output_path"));
            return info;
        } catch (Exception e) {
            throw new RuntimeException("FastAPI cut-merge 오류: " + e.getMessage(), e);
        }
    }

    // Phase 3-1 — 키워드
    public KeywordSearchResponse searchKeywords(String seed, int limit, String category,
                                                int outperformerCount, Long jobId) {
        try {
            Map<String, Object> bodyMap = new HashMap<>();
            bodyMap.put("seed", seed != null ? seed : "");
            bodyMap.put("limit", limit);
            bodyMap.put("category", category);
            bodyMap.put("outperformer_count", outperformerCount);
            bodyMap.put("job_id", jobId);
            return objectMapper.readValue(
                    postJson(fastApiUrl + "/workers/keyword/search", bodyMap),
                    KeywordSearchResponse.class);
        } catch (Exception e) {
            throw new RuntimeException("키워드 탐색 오류: " + e.getMessage(), e);
        }
    }

    // Phase 3-2 — 스크립트
    public ScriptGenerateResponse generateScript(Long jobId, String keyword, int targetMinutes,
                                                  String category, String marketSnapshotJson) {
        try {
            Map<String, Object> bodyMap = new HashMap<>();
            bodyMap.put("job_id", jobId);
            bodyMap.put("keyword", keyword);
            bodyMap.put("target_minutes", targetMinutes);
            bodyMap.put("category", category != null ? category : "CUSTOM");
            
            if (marketSnapshotJson != null && !marketSnapshotJson.isBlank()) {
                try {
                    Map<String, Object> marketDataMap = objectMapper.readValue(marketSnapshotJson, Map.class);
                    bodyMap.put("market_data", marketDataMap);
                } catch (Exception parseEx) {
                    log.warn("marketSnapshotJson 파싱 실패: {}", parseEx.getMessage());
                }
            }
            
            return objectMapper.readValue(
                    postJson(fastApiUrl + "/workers/script/generate", bodyMap),
                    ScriptGenerateResponse.class);
        } catch (Exception e) {
            throw new RuntimeException("스크립트 생성 오류: " + e.getMessage(), e);
        }
    }

    // Phase 3-3 — TTS
    public TtsGenerateResponse generateTts(Long jobId, String script, String voiceId) {
        return generateTts(jobId, script, voiceId, null);
    }

    /**
     * TTS 생성 (배속 지정 가능).
     *
     * ttsSpeed = null이면 FastAPI 워커의 runtime_config 기본값(현재 1.3x)을 그대로 사용.
     * 태호님 피드백 "1.05배 정도 느려도 괜찮다"에 대응하려면 여기에 1.25 등을 지정하거나,
     * /pipeline/config API로 전역 기본값을 낮추면 됩니다.
     */
    public TtsGenerateResponse generateTts(Long jobId, String script, String voiceId, Double ttsSpeed) {
        try {
            Map<String, Object> bodyMap = new HashMap<>();
            bodyMap.put("job_id", jobId);
            bodyMap.put("script", script);
            bodyMap.put("voice_id", voiceId);
            if (ttsSpeed != null) {
                bodyMap.put("tts_speed", ttsSpeed);
            }
            return objectMapper.readValue(
                    postJson(fastApiUrl + "/workers/tts/generate", bodyMap),
                    TtsGenerateResponse.class);
        } catch (Exception e) {
            throw new RuntimeException("TTS 생성 오류: " + e.getMessage(), e);
        }
    }

    // Phase 3-4 — 이미지
    public ImagesGenerateResponse generateImages(Long jobId, String ttsMetaJson, String scriptMetaJson,
                                                  String characterImagePath, String characterStylePrompt,
                                                  String characterPosesDir) {
        return generateImages(jobId, ttsMetaJson, scriptMetaJson, characterImagePath,
                characterStylePrompt, characterPosesDir, null, null, null);
    }

    public ImagesGenerateResponse getImageBatchStatus(Long jobId) {
        try {
            Map<String, Object> bodyMap = new HashMap<>();
            bodyMap.put("job_id", jobId);
            return objectMapper.readValue(
                    postJson(fastApiUrl + "/workers/images/batch-status", bodyMap),
                    ImagesGenerateResponse.class);
        } catch (Exception e) {
            throw new RuntimeException("Gemini Pro Batch 상태 조회 오류: " + e.getMessage(), e);
        }
    }

    /**
     * [Sprint 3] LoRA 모델 지정 버전 이미지 생성.
     *
     * loraModelId가 null이 아닌 시 FastAPI는 fal-ai/flux-lora 엔드포인트를 사용하여
     * 캐릭터 일관성을 극대화합니다.
     */
    public ImagesGenerateResponse generateImages(Long jobId, String ttsMetaJson, String scriptMetaJson,
                                                  String characterImagePath, String characterStylePrompt,
                                                  String characterPosesDir,
                                                  String loraModelId, String loraTriggerWord,
                                                  Float loraScale) {
        try {
            Map<String, Object> bodyMap = new HashMap<>();
            bodyMap.put("job_id", jobId);
            bodyMap.put("tts_meta", ttsMetaJson);
            bodyMap.put("script_meta", scriptMetaJson);
            bodyMap.put("character_image_path", characterImagePath);
            bodyMap.put("character_style_prompt", characterStylePrompt);
            // [S2-4] 캐릭터 포즈 라이브러리 디렉토리
            if (characterPosesDir != null && !characterPosesDir.isBlank()) {
                bodyMap.put("character_poses_dir", characterPosesDir);
            }
            // [Sprint 3] LoRA 파라미터
            if (loraModelId != null && !loraModelId.isBlank()) {
                bodyMap.put("lora_model_id", loraModelId);
                if (loraTriggerWord != null && !loraTriggerWord.isBlank()) {
                    bodyMap.put("lora_trigger_word", loraTriggerWord);
                }
                bodyMap.put("lora_scale", loraScale != null ? loraScale : 1.0f);
            }
            return objectMapper.readValue(
                    postJson(fastApiUrl + "/workers/images/generate", bodyMap),
                    ImagesGenerateResponse.class);
        } catch (Exception e) {
            throw new RuntimeException("이미지 생성 오류: " + e.getMessage(), e);
        }
    }

    // Phase 3-4B — 단일 이미지 재생성
    public void generateSingleImage(Long jobId, int index, String text, String section,
                                     String characterImagePath, String characterStylePrompt,
                                     String characterPosesDir) {
        generateSingleImage(jobId, index, text, section, characterImagePath,
                characterStylePrompt, characterPosesDir, null, null, null);
    }

    /** [Sprint 3] LoRA 지정 단일 이미지 재생성 */
    public void generateSingleImage(Long jobId, int index, String text, String section,
                                     String characterImagePath, String characterStylePrompt,
                                     String characterPosesDir,
                                     String loraModelId, String loraTriggerWord, Float loraScale) {
        try {
            Map<String, Object> bodyMap = new HashMap<>();
            bodyMap.put("job_id", jobId);
            bodyMap.put("index", index);
            bodyMap.put("text", text);
            bodyMap.put("section", section);
            bodyMap.put("character_image_path", characterImagePath);
            bodyMap.put("character_style_prompt", characterStylePrompt);
            // [S2-4] 캐릭터 포즈 라이브러리 디렉토리
            if (characterPosesDir != null && !characterPosesDir.isBlank()) {
                bodyMap.put("character_poses_dir", characterPosesDir);
            }
            // [Sprint 3] LoRA 파라미터
            if (loraModelId != null && !loraModelId.isBlank()) {
                bodyMap.put("lora_model_id", loraModelId);
                if (loraTriggerWord != null && !loraTriggerWord.isBlank()) {
                    bodyMap.put("lora_trigger_word", loraTriggerWord);
                }
                bodyMap.put("lora_scale", loraScale != null ? loraScale : 1.0f);
            }
            postJson(fastApiUrl + "/workers/images/generate-single", bodyMap);
        } catch (Exception e) {
            throw new RuntimeException("단일 이미지 생성 오류: " + e.getMessage(), e);
        }
    }

    // Phase 3-5 — 롱폼
    public LongformGenerateResponse generateLongform(Long jobId, String ttsMetaJson,
                                                       String scenesJson, String gifsJson) {
        try {
            Map<String, Object> bodyMap = new HashMap<>();
            bodyMap.put("job_id", jobId);
            bodyMap.put("tts_meta", ttsMetaJson);
            bodyMap.put("scenes_meta", scenesJson);
            bodyMap.put("gifs_meta", gifsJson);
            return objectMapper.readValue(
                    postJson(fastApiUrl + "/workers/longform/generate", bodyMap),
                    LongformGenerateResponse.class);
        } catch (Exception e) {
            throw new RuntimeException("롱폼 조립 오류: " + e.getMessage(), e);
        }
    }

    // Phase 2+ — BGM 생성
    public void generateBgm(Long jobId, String category, int durationSeconds) {
        try {
            Map<String, Object> bodyMap = new HashMap<>();
            bodyMap.put("job_id", jobId);
            bodyMap.put("category", category != null ? category : "CUSTOM");
            bodyMap.put("duration_seconds", durationSeconds);
            postJson(fastApiUrl + "/workers/bgm/generate", bodyMap);
        } catch (Exception e) {
            log.error("BGM 생성 오류 (무시하고 계속 진행): {}", e.getMessage());
            // BGM 실패가 전체 파이프라인을 멈추게 하지 않음
        }
    }

    public List<TrendingVideoDto> getTrendingVideos(String keyword, int limit) {
        try {
            Map<String, Object> bodyMap = new HashMap<>();
            bodyMap.put("keyword", keyword);
            bodyMap.put("limit", limit);
            
            String responseBody = postJson(fastApiUrl + "/workers/trending/youtube", bodyMap);
            Map<String, Object> response = objectMapper.readValue(responseBody, Map.class);
            List<Map<String, Object>> videosMap = (List<Map<String, Object>>) response.get("videos");
            
            List<TrendingVideoDto> videos = new ArrayList<>();
            if (videosMap != null) {
                for (Map<String, Object> map : videosMap) {
                    TrendingVideoDto dto = objectMapper.convertValue(map, TrendingVideoDto.class);
                    videos.add(dto);
                }
            }
            return videos;
        } catch (Exception e) {
            throw new RuntimeException("트렌딩 비디오 검색 오류: " + e.getMessage(), e);
        }
    }

    @SuppressWarnings("unchecked")
    public Map<String, Object> generateYoutubeMetadata(String scriptText, boolean isShorts) {
        try {
            Map<String, Object> bodyMap = new HashMap<>();
            bodyMap.put("script_text", scriptText);
            bodyMap.put("is_shorts", isShorts);
            String responseBody = postJson(fastApiUrl + "/workers/youtube/metadata", bodyMap);
            return objectMapper.readValue(responseBody, Map.class);
        } catch (Exception e) {
            throw new RuntimeException("유튜브 메타데이터 생성 오류: " + e.getMessage(), e);
        }
    }

    public void generateThumbnailImage(Long jobId, String title, String format, String outputPath, 
                                       String characterImagePath, String characterStylePrompt,
                                       String loraModelId, String loraTriggerWord, Double loraScale) {
        try {
            Map<String, Object> bodyMap = new HashMap<>();
            bodyMap.put("job_id", jobId);
            bodyMap.put("title", title);
            bodyMap.put("format", format);
            bodyMap.put("output_path", outputPath);
            bodyMap.put("character_image_path", characterImagePath);
            bodyMap.put("character_style_prompt", characterStylePrompt);
            bodyMap.put("lora_model_id", loraModelId);
            bodyMap.put("lora_trigger_word", loraTriggerWord);
            bodyMap.put("lora_scale", loraScale);
            postJson(fastApiUrl + "/workers/youtube/thumbnail", bodyMap);
        } catch (Exception e) {
            throw new RuntimeException("유튜브 썸네일 생성 오류: " + e.getMessage(), e);
        }
    }

    public void stopJob(Long jobId) {
        try {
            Map<String, Object> bodyMap = new HashMap<>();
            bodyMap.put("job_id", jobId);
            postJson(fastApiUrl + "/workers/jobs/" + jobId + "/stop", bodyMap);
        } catch (Exception e) {
            log.error("FastAPI 작업 중지 통지 실패: jobId={}, error={}", jobId, e.getMessage());
        }
    }

    // ============================
    // [Sprint 3] LoRA 캐릭터 파인튜닝 API
    // ============================

    /**
     * [Sprint 3] LoRA 학습 시작.
     * ZIP 파일을 FastAPI에 multipart/form-data로 전송하고 학습 request_id를 반환.
     */
    @SuppressWarnings("unchecked")
    public Map<String, Object> startLoraTraining(
            String channelId, byte[] zipBytes, String triggerWord, int steps, boolean isStyle)
            throws IOException {
        String urlStr = String.format(
                "%s/workers/lora/train?channel_id=%s&trigger_word=%s&steps=%d&is_style=%b",
                fastApiUrl, channelId, triggerWord, steps, isStyle
        );
        String boundary = UUID.randomUUID().toString().replace("-", "");
        URL url = new URL(urlStr);
        HttpURLConnection conn = (HttpURLConnection) url.openConnection();
        conn.setRequestMethod("POST");
        conn.setDoOutput(true);
        conn.setConnectTimeout(10_000);
        conn.setReadTimeout(300_000); // 5분 (파일 업로드 + 큐 등록)
        conn.setRequestProperty("Content-Type", "multipart/form-data; boundary=" + boundary);

        try (OutputStream os = conn.getOutputStream()) {
            String partHeader = "--" + boundary + "\r\n"
                    + "Content-Disposition: form-data; name=\"zip_file\"; filename=\"reference_images.zip\"\r\n"
                    + "Content-Type: application/zip\r\n\r\n";
            os.write(partHeader.getBytes(StandardCharsets.UTF_8));
            os.write(zipBytes);
            os.write(("\r\n--" + boundary + "--\r\n").getBytes(StandardCharsets.UTF_8));
            os.flush();
        }
        int code = conn.getResponseCode();
        InputStream is = code >= 200 && code < 300 ? conn.getInputStream() : conn.getErrorStream();
        String body = new String(is.readAllBytes(), StandardCharsets.UTF_8);
        if (code < 200 || code >= 300) {
            throw new RuntimeException("LoRA 학습 시작 실패 (" + code + "): " + body);
        }
        return objectMapper.readValue(body, Map.class);
    }

    /**
     * [Sprint 3] LoRA 학습 진행 상태 조회.
     * 학습 완료 시 lora_model_url(safetensors URL) 포함.
     */
    @SuppressWarnings("unchecked")
    public Map<String, Object> getLoraStatus(String requestId) {
        try {
            String urlStr = fastApiUrl + "/workers/lora/status/" + requestId;
            URL url = new URL(urlStr);
            HttpURLConnection conn = (HttpURLConnection) url.openConnection();
            conn.setRequestMethod("GET");
            conn.setConnectTimeout(10_000);
            conn.setReadTimeout(30_000);
            int code = conn.getResponseCode();
            InputStream is = code >= 200 && code < 300 ? conn.getInputStream() : conn.getErrorStream();
            String body = new String(is.readAllBytes(), StandardCharsets.UTF_8);
            if (code < 200 || code >= 300) {
                throw new RuntimeException("LoRA 상태 조회 실패 (" + code + "): " + body);
            }
            return objectMapper.readValue(body, Map.class);
        } catch (Exception e) {
            throw new RuntimeException("LoRA 상태 조회 오류: " + e.getMessage(), e);
        }
    }

    public void deleteJob(Long jobId) {
        try {
            restTemplate.delete(fastApiUrl + "/workers/jobs/" + jobId);
            log.info("FastAPI 작업 리소스 삭제 통지 성공: jobId={}", jobId);
        } catch (Exception e) {
            log.error("FastAPI 작업 리소스 삭제 통지 실패: jobId={}, error={}", jobId, e.getMessage());
        }
    }

    // ============================
    // 공통 POST helper — UTF-8 charset 명시
    // ============================
    private String postJson(String urlStr, Map<String, Object> bodyMap) throws IOException {
        String jsonBody = objectMapper.writeValueAsString(bodyMap);
        log.info("FastAPI POST: {} bodyLen={}", urlStr, jsonBody.length());

        URL url = new URL(urlStr);
        HttpURLConnection conn = (HttpURLConnection) url.openConnection();
        conn.setRequestMethod("POST");
        conn.setDoOutput(true);
        conn.setConnectTimeout(10_000);
        conn.setReadTimeout(1_800_000); // 30분
        // UTF-8 charset 명시 — 한글 깨짐 방지 핵심
        conn.setRequestProperty("Content-Type", "application/json; charset=UTF-8");
        conn.setRequestProperty("Accept", "application/json");

        // UTF-8 바이트로 명시적 인코딩
        byte[] bodyBytes = jsonBody.getBytes(StandardCharsets.UTF_8);
        try (OutputStream os = conn.getOutputStream()) {
            os.write(bodyBytes);
            os.flush();
        }
        int code = conn.getResponseCode();
        InputStream is = code >= 200 && code < 300 ? conn.getInputStream() : conn.getErrorStream();
        String responseBody = new String(is.readAllBytes(), StandardCharsets.UTF_8);
        log.info("FastAPI 응답: code={}, bodyLen={}", code, responseBody.length());
        if (code < 200 || code >= 300) throw new RuntimeException("FastAPI 실패: " + code + " " + responseBody);
        return responseBody;
    }

    @SuppressWarnings("unchecked")
    public List<Map<String, Object>> getElevenLabsVoices() {
        try {
            return restTemplate.getForObject(fastApiUrl + "/workers/tts/voices", List.class);
        } catch (Exception e) {
            log.error("ElevenLabs 목소리 목록 조회 실패: {}", e.getMessage());
            return List.of();
        }
    }

    @SuppressWarnings("unchecked")
    public Map<String, Object> getCharacterLibraryStatus(String channelId) {
        try {
            return restTemplate.getForObject(
                    fastApiUrl + "/workers/character-library/" + channelId, Map.class);
        } catch (Exception e) {
            throw new RuntimeException("캐릭터 라이브러리 상태 조회 실패: " + e.getMessage(), e);
        }
    }

    @SuppressWarnings("unchecked")
    public Map<String, Object> generateCharacterLibrary(
            String channelId, String characterDescription, boolean regenerate) {
        try {
            Map<String, Object> body = new HashMap<>();
            body.put("channel_id", channelId);
            body.put("character_description", characterDescription);
            body.put("regenerate", regenerate);
            return objectMapper.readValue(
                    postJson(fastApiUrl + "/workers/character-library/generate", body), Map.class);
        } catch (Exception e) {
            throw new RuntimeException("캐릭터 포즈 생성 실패: " + e.getMessage(), e);
        }
    }

    public ResponseEntity<byte[]> getCharacterPose(String channelId, String pose) {
        try {
            return restTemplate.exchange(
                    fastApiUrl + "/workers/character-library/" + channelId + "/pose/" + pose,
                    HttpMethod.GET,
                    null,
                    byte[].class);
        } catch (Exception e) {
            throw new RuntimeException("캐릭터 포즈 조회 실패: " + e.getMessage(), e);
        }
    }
}
