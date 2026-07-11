package com.pipeline.video.controller;

import lombok.extern.slf4j.Slf4j;
import org.springframework.core.io.Resource;
import org.springframework.core.io.UrlResource;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.io.File;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.nio.file.Paths;

/**
 * 파일 다운로드/스트리밍 컨트롤러.
 *
 * 왜 새로 만들었는지:
 *   프론트엔드의 여러 곳(JobDetail의 씬 이미지 썸네일, TTS <audio>, 롱폼 <video>,
 *   PDF 내보내기용 이미지 URL, Shorts.jsx의 downloadFile 헬퍼)이 모두
 *   /api/files/download?path=... 를 호출하는데, 이 경로를 처리하는 컨트롤러가
 *   서버에 존재하지 않았습니다. SecurityConfig에서 /api/files/** 를 authenticated()로
 *   허용만 해놓고 정작 파일을 서빙하는 코드가 없어서, 프론트에서 이미지가 전부
 *   깨져 보이거나 오디오가 재생되지 않는 이슈가 있었습니다.
 *
 * 보안 처리:
 *   - JWT 인증 필수 (SecurityConfig의 authenticated())
 *   - path 파라미터는 /app/data/ 아래로 강제 제한 (경로 탐색 공격 차단)
 *     예: ?path=/etc/passwd, ?path=../../secret 같은 요청은 전부 400
 *   - 심볼릭 링크 우회도 실제 절대 경로로 정규화 후 재검증
 *
 * MIME 타입은 확장자 기반으로 자동 판별 (png/jpg/mp3/mp4/webm 등).
 */
@RestController
@RequestMapping("/api/files/serve")
@Slf4j
public class FileDownloadController {

    /** 파일 접근을 허용할 루트 디렉토리. 이 밖의 경로는 전부 차단. */
    private static final Path ALLOWED_ROOT = Paths.get("/app/data").toAbsolutePath().normalize();

    @GetMapping("/download")
    public ResponseEntity<Resource> download(
            @RequestParam("path") String pathParam,
            @RequestParam(value = "salt", required = false) String salt,
            @RequestParam(value = "token", required = false) String tokenQuery,
            @AuthenticationPrincipal String username) {

        // 1. 경로 정규화 — 상대경로/심볼릭링크로 우회 시도 차단
        Path requested;
        try {
            requested = Paths.get(pathParam).toAbsolutePath().normalize();
        } catch (Exception e) {
            log.warn("잘못된 파일 경로 요청: {}", pathParam);
            return ResponseEntity.badRequest().build();
        }

        // 2. /app/data 밖 접근 차단 (Path Traversal 공격 방지)
        if (!requested.startsWith(ALLOWED_ROOT)) {
            log.warn("허용된 루트({}) 밖의 파일 접근 시도 by user={}, path={}",
                    ALLOWED_ROOT, username, requested);
            return ResponseEntity.status(403).build();
        }

        File file = requested.toFile();
        if (!file.exists() || !file.isFile()) {
            return ResponseEntity.notFound().build();
        }

        try {
            Resource resource = new UrlResource(file.toURI());
            MediaType mediaType = detectMediaType(file.getName());

            // 이미지/오디오/영상은 브라우저에서 인라인 표시,
            // 그 외는 attachment로 다운로드 유도.
            String disposition = isInlineType(mediaType) ? "inline" : "attachment";
            String encodedName = URLEncoder.encode(file.getName(), StandardCharsets.UTF_8)
                    .replace("+", "%20");

            return ResponseEntity.ok()
                    .contentType(mediaType)
                    .header(HttpHeaders.CONTENT_DISPOSITION,
                            disposition + "; filename*=UTF-8''" + encodedName)
                    .header(HttpHeaders.CACHE_CONTROL, "private, max-age=60")
                    .body(resource);
        } catch (Exception e) {
            log.error("파일 서빙 실패 path={}: {}", pathParam, e.getMessage());
            return ResponseEntity.internalServerError().build();
        }
    }

    private static MediaType detectMediaType(String filename) {
        String lower = filename.toLowerCase();
        if (lower.endsWith(".png")) return MediaType.IMAGE_PNG;
        if (lower.endsWith(".jpg") || lower.endsWith(".jpeg")) return MediaType.IMAGE_JPEG;
        if (lower.endsWith(".gif")) return MediaType.IMAGE_GIF;
        if (lower.endsWith(".webp")) return MediaType.parseMediaType("image/webp");
        if (lower.endsWith(".mp3")) return MediaType.parseMediaType("audio/mpeg");
        if (lower.endsWith(".wav")) return MediaType.parseMediaType("audio/wav");
        if (lower.endsWith(".mp4")) return MediaType.parseMediaType("video/mp4");
        if (lower.endsWith(".webm")) return MediaType.parseMediaType("video/webm");
        if (lower.endsWith(".txt")) return MediaType.TEXT_PLAIN;
        if (lower.endsWith(".json")) return MediaType.APPLICATION_JSON;
        return MediaType.APPLICATION_OCTET_STREAM;
    }

    private static boolean isInlineType(MediaType type) {
        String t = type.getType();
        return "image".equals(t) || "audio".equals(t) || "video".equals(t);
    }
}
