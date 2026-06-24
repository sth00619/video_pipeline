package com.pipeline.video.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.pipeline.video.dto.ShortClipInfo;
import com.pipeline.video.dto.ShortsAnalyzeResponse;
import com.pipeline.video.dto.ShortsConfirmRequest;
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

    /**
     * 영상 업로드 → Whisper 분석
     */
    public ShortsAnalyzeResponse analyzeShorts(MultipartFile file, int shortsCount, Long jobId)
            throws IOException {
        String urlStr = String.format("%s/workers/shorts/analyze?shorts_count=%d&job_id=%d",
                fastApiUrl, shortsCount, jobId);

        String boundary = UUID.randomUUID().toString().replace("-", "");
        String fileName = file.getOriginalFilename() != null ? file.getOriginalFilename() : "video.mp4";
        byte[] fileBytes = file.getBytes();

        log.info("FastAPI analyze 호출: jobId={}, file={}, size={}bytes", jobId, fileName, fileBytes.length);

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

        if (code < 200 || code >= 300) {
            log.error("FastAPI analyze 오류: {} {}", code, body);
            throw new RuntimeException("FastAPI analyze 실패: " + code + " " + body);
        }

        log.info("FastAPI analyze 성공: jobId={}", jobId);
        return objectMapper.readValue(body, ShortsAnalyzeResponse.class);
    }

    /**
     * 확정된 구간으로 자르기 — HttpURLConnection 사용 (RestTemplate 대신)
     */
    @SuppressWarnings("unchecked")
    public List<ShortClipInfo> cutShorts(Long jobId, String sourceVideoPath,
                                          ShortsConfirmRequest request) {
        try {
            String urlStr = String.format("%s/workers/shorts/cut", fastApiUrl);

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

            String jsonBody = objectMapper.writeValueAsString(bodyMap);
            log.info("FastAPI cut 호출: jobId={}, segments={}, body={}",
                    jobId, request.getSegments().size(), jsonBody);

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
            log.info("FastAPI cut 응답: code={}, body={}", code, responseBody);

            if (code < 200 || code >= 300) {
                throw new RuntimeException("FastAPI cut 실패: " + code + " " + responseBody);
            }

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
            log.info("FastAPI cut 완료: {}개 클립 생성", clips.size());
            return clips;

        } catch (Exception e) {
            log.error("FastAPI cut 예외: {}", e.getMessage(), e);
            throw new RuntimeException("FastAPI cut 오류: " + e.getMessage(), e);
        }
    }
}
