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

    // ============================
    // Phase 2 — 쇼츠
    // ============================
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
        conn.setReadTimeout(600_000);
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

    // Phase 3-1
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

    // Phase 3-2
    public ScriptGenerateResponse generateScript(Long jobId, String keyword, int targetMinutes,
                                                  String category) {
        try {
            Map<String, Object> bodyMap = new HashMap<>();
            bodyMap.put("job_id", jobId);
            bodyMap.put("keyword", keyword);
            bodyMap.put("target_minutes", targetMinutes);
            bodyMap.put("category", category != null ? category : "CUSTOM");
            return objectMapper.readValue(
                    postJson(fastApiUrl + "/workers/script/generate", bodyMap),
                    ScriptGenerateResponse.class);
        } catch (Exception e) {
            throw new RuntimeException("스크립트 생성 오류: " + e.getMessage(), e);
        }
    }

    // Phase 3-3
    public TtsGenerateResponse generateTts(Long jobId, String script, String voiceId) {
        try {
            Map<String, Object> bodyMap = new HashMap<>();
            bodyMap.put("job_id", jobId);
            bodyMap.put("script", script);
            bodyMap.put("voice_id", voiceId);
            return objectMapper.readValue(
                    postJson(fastApiUrl + "/workers/tts/generate", bodyMap),
                    TtsGenerateResponse.class);
        } catch (Exception e) {
            throw new RuntimeException("TTS 생성 오류: " + e.getMessage(), e);
        }
    }

    // ============================
    // Phase 3-4 — 이미지 + GIF 생성
    // ============================
    public ImagesGenerateResponse generateImages(Long jobId, String ttsMetaJson, String scriptMetaJson) {
        try {
            Map<String, Object> bodyMap = new HashMap<>();
            bodyMap.put("job_id", jobId);
            bodyMap.put("tts_meta", ttsMetaJson);
            bodyMap.put("script_meta", scriptMetaJson);
            return objectMapper.readValue(
                    postJson(fastApiUrl + "/workers/images/generate", bodyMap),
                    ImagesGenerateResponse.class);
        } catch (Exception e) {
            throw new RuntimeException("이미지 생성 오류: " + e.getMessage(), e);
        }
    }

    // ============================
    // 공통 POST helper
    // ============================
    private String postJson(String urlStr, Map<String, Object> bodyMap) throws IOException {
        String jsonBody = objectMapper.writeValueAsString(bodyMap);
        log.info("FastAPI POST: {} bodyLen={}", urlStr, jsonBody.length());

        URL url = new URL(urlStr);
        HttpURLConnection conn = (HttpURLConnection) url.openConnection();
        conn.setRequestMethod("POST");
        conn.setDoOutput(true);
        conn.setConnectTimeout(10_000);
        conn.setReadTimeout(600_000);
        conn.setRequestProperty("Content-Type", "application/json");
        conn.setRequestProperty("Accept", "application/json");
        try (OutputStream os = conn.getOutputStream()) {
            os.write(jsonBody.getBytes(StandardCharsets.UTF_8));
            os.flush();
        }
        int code = conn.getResponseCode();
        InputStream is = code >= 200 && code < 300 ? conn.getInputStream() : conn.getErrorStream();
        String responseBody = new String(is.readAllBytes(), StandardCharsets.UTF_8);
        log.info("FastAPI 응답: code={}, bodyLen={}", code, responseBody.length());
        if (code < 200 || code >= 300) throw new RuntimeException("FastAPI 실패: " + code + " " + responseBody);
        return responseBody;
    }
}
