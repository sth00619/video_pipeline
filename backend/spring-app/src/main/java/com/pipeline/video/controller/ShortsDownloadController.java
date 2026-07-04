package com.pipeline.video.controller;

import lombok.extern.slf4j.Slf4j;
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;

import java.io.File;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;

/**
 * 파일 다운로드 프록시
 * - Spring 8080을 통해 /app/data/ 볼륨 파일 서빙
 * - docker-compose spring-app volumes: fastapi_data:/app/data 필요
 * - SecurityConfig에서 /api/files/** 허용 필요
 */
@RestController
@RequestMapping("/api/files")
@Slf4j
public class ShortsDownloadController {

    @GetMapping("/download")
    public ResponseEntity<Resource> download(@RequestParam String path) {
        try {
            String decoded = URLDecoder.decode(path, StandardCharsets.UTF_8);

            // 보안: /app/data/ 이하만 허용
            if (!decoded.startsWith("/app/data/")) {
                log.warn("허용되지 않은 경로: {}", decoded);
                return ResponseEntity.status(HttpStatus.FORBIDDEN).build();
            }

            File file = new File(decoded);
            if (!file.exists() || !file.isFile()) {
                log.warn("파일 없음: {}", decoded);
                return ResponseEntity.notFound().build();
            }

            String filename = file.getName();

            // 확장자로 미디어 타입 결정
            MediaType mediaType;
            if (filename.endsWith(".gif")) {
                mediaType = MediaType.IMAGE_GIF;
            } else if (filename.endsWith(".mp3")) {
                mediaType = MediaType.parseMediaType("audio/mpeg");
            } else {
                mediaType = MediaType.parseMediaType("video/mp4");
            }

            Resource resource = new FileSystemResource(file);

            return ResponseEntity.ok()
                    .contentType(mediaType)
                    .contentLength(file.length())
                    .header(HttpHeaders.CONTENT_DISPOSITION,
                            "attachment; filename=\"" + filename + "\"")
                    .header(HttpHeaders.CACHE_CONTROL, "no-cache")
                    .body(resource);

        } catch (Exception e) {
            log.error("다운로드 오류: {}", e.getMessage());
            return ResponseEntity.internalServerError().build();
        }
    }
}
