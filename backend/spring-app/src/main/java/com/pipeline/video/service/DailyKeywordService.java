package com.pipeline.video.service;

import com.pipeline.video.dto.TrendingVideoDto;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;

import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.TimeUnit;

/**
 * 롱폼 화면용 일일 키워드 스냅샷.
 *
 * 후보를 만들 때 LLM 요약을 먼저 기다리지 않는다. YouTube Data API에서 조회한 최근
 * 공개 영상 자체를 근거가 있는 후보로 보여 주고, 작업자가 영상·수치를 보고 주제를 선택한다.
 * 이렇게 하면 한 공급자 지연 때문에 후보 목록 전체가 비는 문제를 피할 수 있다.
 */
@Service
@RequiredArgsConstructor
@Slf4j
public class DailyKeywordService {
    private static final ZoneId KST = ZoneId.of("Asia/Seoul");
    // One search request costs the same whether it returns 5 or 30 videos.
    // Pull a wider pool first. S/A videos are ranked first, but they are not
    // an exclusion rule: a seven-day 3k-subscriber/500-view qualified source remains useful
    // evidence when the S/A pool is small.
    private static final int VIDEOS_PER_SEED = 30;
    private static final int MAX_DAILY_CANDIDATES = 30;
    private static final int REFRESH_TIMEOUT_SECONDS = 15;
    private static final long MIN_EVIDENCE_SUBSCRIBERS = 3_000L;
    private static final long MIN_EVIDENCE_VIEWS = 500L;
    // "구독자 수의 1% 이상 조회"는 대형 채널의 최신 영상을 너무 일찍
    // 탈락시키지 않으면서 반응이 전혀 없는 영상은 걸러내는 기준이다.
    private static final double MIN_EVIDENCE_VIEWER_MULTIPLE = 0.01d;

    private final FastApiClient fastApiClient;
    private final Map<String, List<Map<String, Object>>> snapshots = new ConcurrentHashMap<>();
    private final List<Map<String, Object>> manual = Collections.synchronizedList(new ArrayList<>());

    @Scheduled(cron = "0 0 9 * * *", zone = "Asia/Seoul")
    public void scheduledRefresh() {
        refreshToday();
    }

    public synchronized List<Map<String, Object>> getToday() {
        String day = LocalDate.now(KST).toString();
        if (!snapshots.containsKey(day)) {
            refreshToday();
        }
        List<Map<String, Object>> result = new ArrayList<>(snapshots.getOrDefault(day, List.of()));
        synchronized (manual) {
            result.addAll(manual);
        }
        return result;
    }

    public boolean youtubeConfigured() {
        Object youtube = fastApiClient.getProviderStatus().get("youtube");
        return youtube instanceof Map<?, ?> map && Boolean.TRUE.equals(map.get("configured"));
    }

    public Map<String, Object> previewManualKeyword(String keyword, int recentHours) {
        String normalized = keyword == null ? "" : keyword.trim();
        if (normalized.isBlank()) {
            throw new IllegalArgumentException("키워드를 입력해 주세요.");
        }
        return fastApiClient.getManualKeywordContext(normalized, Math.max(1, Math.min(recentHours, 24)));
    }

    /**
     * 세 개의 시드 검색을 병렬 수행한다. 개별 검색이 지연되거나 실패해도 나머지 카테고리의
     * 후보는 계속 반환한다. 각 후보는 반드시 실제 공개 영상 한 개 이상을 근거로 가진다.
     */
    public synchronized List<Map<String, Object>> refreshToday() {
        String day = LocalDate.now(KST).toString();
        List<CompletableFuture<List<Map<String, Object>>>> futures = Arrays.stream(new String[][]{
                        {"KOSPI", "코스피"}, {"KOSDAQ", "코스닥"}, {"US_STOCKS", "미국 주식"}
                })
                .map(seed -> CompletableFuture.supplyAsync(() -> collectSeed(seed))
                        .completeOnTimeout(List.of(), REFRESH_TIMEOUT_SECONDS, TimeUnit.SECONDS)
                        .exceptionally(error -> {
                            log.warn("daily YouTube candidate lookup failed: {}", error.getMessage());
                            return List.of();
                        }))
                .toList();

        List<Map<String, Object>> collectedRows = new ArrayList<>();
        futures.forEach(future -> collectedRows.addAll(future.join()));
        List<Map<String, Object>> rows = collectedRows.stream()
                .filter(row -> number(row.get("subscribers")) >= MIN_EVIDENCE_SUBSCRIBERS)
                .filter(row -> number(row.get("views")) >= MIN_EVIDENCE_VIEWS)
                .filter(row -> sourceMultiple(row) >= MIN_EVIDENCE_VIEWER_MULTIPLE)
                // The product is longform-first: retain Shorts as signals, but
                // show longform evidence before equally strong Shorts.
                .sorted(Comparator
                        .comparing((Map<String, Object> row) -> number(row.get("durationSeconds")) > 60 ? 1 : 0, Comparator.reverseOrder())
                        .thenComparing((Map<String, Object> row) -> number(row.get("performanceScore")), Comparator.reverseOrder())
                        .thenComparing((Map<String, Object> row) -> number(row.get("velocityVph")), Comparator.reverseOrder()))
                .limit(MAX_DAILY_CANDIDATES)
                .toList();
        snapshots.put(day, rows);
        return rows;
    }

    private List<Map<String, Object>> collectSeed(String[] seed) {
        List<TrendingVideoDto> videos = fastApiClient.getTrendingVideos(seed[1], VIDEOS_PER_SEED);
        if (videos == null || videos.isEmpty()) {
            return List.of();
        }
        List<Map<String, Object>> rows = new ArrayList<>();
        for (TrendingVideoDto video : videos) {
            if (video == null || video.getTitle() == null || video.getTitle().isBlank()) {
                continue;
            }
            if (!isEligibleEvidence(video)) {
                continue;
            }
            rows.add(candidateFromVideo(video.getTitle().trim(), seed[0], "daily", video,
                    "매일 오전 9시 자동 수집 · 최근 공개 영상 기반"));
        }
        return rows;
    }

    /** 수동 키워드는 즉시 동일한 공개 YouTube 지표를 붙여서 후보에 보관한다. */
    public Map<String, Object> addManual(String keyword, String category, String note) {
        String normalized = keyword == null ? "" : keyword.trim();
        if (normalized.isBlank()) {
            throw new IllegalArgumentException("키워드를 입력해 주세요.");
        }
        String normalizedCategory = category == null || category.isBlank() ? "CUSTOM" : category;
        Map<String, Object> row;
        try {
            List<TrendingVideoDto> videos = fastApiClient.getTrendingVideos(normalized, 1);
            if (videos != null && !videos.isEmpty() && isEligibleEvidence(videos.get(0))) {
                row = candidateFromVideo(normalized, normalizedCategory, "manual", videos.get(0),
                        "직접 입력 · 최근 공개 영상 기반");
            } else {
                row = emptyManualCandidate(normalized, normalizedCategory);
            }
        } catch (Exception error) {
            log.warn("manual keyword metrics unavailable: {}", error.getMessage());
            row = emptyManualCandidate(normalized, normalizedCategory);
        }
        row.put("note", note == null ? "" : note.trim());
        row.put("addedAt", Instant.now().toString());
        synchronized (manual) {
            manual.removeIf(item -> normalized.equalsIgnoreCase(String.valueOf(item.get("keyword"))));
            manual.add(row);
        }
        return row;
    }

    /** FastAPI가 Redis 6시간 캐시를 관리하는 태그·제목 기반 마인드맵 위임. */
    public Map<String, Object> buildMindMap(String keyword, List<Map<String, Object>> videos) {
        return fastApiClient.buildKeywordMindMap(keyword, videos);
    }

    /** 선택 키워드 기획은 수치 원본을 함께 전달하고, FastAPI가 JSON-only LLM 응답을 검증한다. */
    public Map<String, Object> buildPlans(Map<String, Object> request) {
        return fastApiClient.buildKeywordPlans(request);
    }

    private Map<String, Object> candidateFromVideo(String keyword, String category, String source,
                                                    TrendingVideoDto video, String sourceLabel) {
        Map<String, Object> row = new LinkedHashMap<>();
        row.put("keyword", keyword);
        row.put("category", category);
        row.put("source", source);
        row.put("views", video.getViews());
        row.put("subscribers", video.getSubscribers());
        row.put("likes", video.getLikes());
        row.put("comments", video.getComments());
        row.put("viewsPerSubscriber", ratio(video.getViews(), video.getSubscribers()));
        row.put("velocityVph", velocity(video.getViews(), video.getHoursSincePublish()));
        row.put("performanceScore", video.getPerformanceScore());
        row.put("performanceGrade", video.getPerformanceGrade());
        row.put("durationSeconds", video.getDurationSeconds());
        row.put("reason", sourceLabel + " · " + safe(video.getChannelTitle(), "채널 정보 없음")
                + " · " + relativeAge(video.getHoursSincePublish()));
        row.put("evidenceVideoIds", video.getVideoId() == null ? List.of() : List.of(video.getVideoId()));
        row.put("sourceVideos", List.of(video));
        row.put("metricsAvailable", true);
        row.put("collectedAt", Instant.now().toString());
        return row;
    }

    private Map<String, Object> emptyManualCandidate(String keyword, String category) {
        Map<String, Object> row = new LinkedHashMap<>();
        row.put("keyword", keyword);
        row.put("category", category);
        row.put("source", "manual");
        row.put("reason", "직접 입력 · 최근 7일 안의 일반 영상 중 구독자 3천·조회수 500 이상, 조회수가 구독자 수의 1% 이상인 근거를 아직 찾지 못했습니다.");
        row.put("evidenceVideoIds", List.of());
        row.put("sourceVideos", List.of());
        row.put("metricsAvailable", false);
        row.put("collectedAt", Instant.now().toString());
        return row;
    }

    private static String safe(String value, String fallback) {
        return value == null || value.isBlank() ? fallback : value;
    }

    private static String relativeAge(Double hours) {
        if (hours == null || hours < 0) {
            return "게시 시각 정보 없음";
        }
        if (hours < 1) {
            return "게시 1시간 이내";
        }
        if (hours < 24) {
            return "게시 " + Math.round(hours) + "시간";
        }
        return "게시 " + Math.round(hours / 24) + "일";
    }

    private static Double velocity(Long views, Double hours) {
        return views != null && hours != null && hours > 0 ? views.doubleValue() / hours : null;
    }

    private static Double ratio(Long views, Long subscribers) {
        return views != null && subscribers != null && subscribers > 0
                ? views.doubleValue() / subscribers
                : null;
    }

    private static Double number(Object value) {
        return value instanceof Number number ? number.doubleValue() : -1d;
    }

    private static double sourceMultiple(Map<String, Object> row) {
        double subscribers = number(row.get("subscribers"));
        return subscribers > 0 ? number(row.get("views")) / subscribers : 0d;
    }

    private static boolean isEligibleEvidence(TrendingVideoDto video) {
        return video != null && video.getSubscribers() != null
                && video.getSubscribers() >= MIN_EVIDENCE_SUBSCRIBERS
                && video.getViews() != null && video.getViews() >= MIN_EVIDENCE_VIEWS
                && ratio(video.getViews(), video.getSubscribers()) != null && ratio(video.getViews(), video.getSubscribers()) >= MIN_EVIDENCE_VIEWER_MULTIPLE
                && video.getHoursSincePublish() != null && video.getHoursSincePublish() > 0 && video.getHoursSincePublish() <= 24 * 7
                && !Boolean.TRUE.equals(video.getIsLive())
                && Boolean.TRUE.equals(video.getSubscriberCountAvailable());
    }
}
