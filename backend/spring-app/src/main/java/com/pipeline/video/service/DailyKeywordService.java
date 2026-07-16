package com.pipeline.video.service;

import com.pipeline.video.dto.KeywordItemDto;
import com.pipeline.video.dto.KeywordSearchResponse;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;

import java.time.*;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;

/** Dashboard용 일일 키워드 스냅샷. 기준 시각은 KST 08:00, 갱신은 KST 09:00이다. */
@Service
@RequiredArgsConstructor
@Slf4j
public class DailyKeywordService {
    private final FastApiClient fastApiClient;
    private final Map<String, List<Map<String, Object>>> snapshots = new ConcurrentHashMap<>();
    private final List<Map<String, Object>> manual = Collections.synchronizedList(new ArrayList<>());
    private static final ZoneId KST = ZoneId.of("Asia/Seoul");

    @Scheduled(cron = "0 0 9 * * *", zone = "Asia/Seoul")
    public void scheduledRefresh() { refreshToday(); }

    public synchronized List<Map<String, Object>> getToday() {
        String day = LocalDate.now(KST).toString();
        if (!snapshots.containsKey(day)) refreshToday();
        List<Map<String, Object>> result = new ArrayList<>(snapshots.getOrDefault(day, List.of()));
        synchronized (manual) { result.addAll(manual); }
        return result;
    }

    public boolean youtubeConfigured() {
        Object youtube = fastApiClient.getProviderStatus().get("youtube");
        return youtube instanceof Map<?, ?> map && Boolean.TRUE.equals(map.get("configured"));
    }

    public synchronized List<Map<String, Object>> refreshToday() {
        String day = LocalDate.now(KST).toString();
        List<Map<String, Object>> rows = new ArrayList<>();
        for (String[] seed : new String[][]{{"KOSPI", "코스피"}, {"KOSDAQ", "코스닥"}, {"US_STOCKS", "미국 주식"}}) {
            try {
                KeywordSearchResponse response = fastApiClient.searchKeywords(seed[1], 8, seed[0], 3, 0L);
                if (response.getCandidates() == null) continue;
                for (KeywordItemDto item : response.getCandidates()) {
                    Map<String, Object> row = new LinkedHashMap<>();
                    row.put("keyword", item.getKeyword()); row.put("category", seed[0]);
                    row.put("source", "daily"); row.put("views", item.getViews());
                    row.put("subscribers", item.getSubscribers()); row.put("likes", item.getLikes());
                    row.put("comments", item.getComments()); row.put("viewsPerSubscriber", ratio(item.getViews(), item.getSubscribers()));
                    row.put("velocityVph", item.getVelocityVph()); row.put("reason", item.getReason());
                    row.put("evidenceVideoIds", item.getEvidenceVideoIds()); row.put("sourceVideos", item.getSourceVideos());
                    rows.add(row);
                }
            } catch (Exception e) { log.warn("daily keyword refresh failed: {}", e.getMessage()); }
        }
        snapshots.put(day, rows);
        return rows;
    }

    public Map<String, Object> addManual(String keyword, String category, String note) {
        Map<String, Object> row = new LinkedHashMap<>();
        row.put("keyword", keyword.trim()); row.put("category", category == null ? "CUSTOM" : category);
        row.put("source", "manual"); row.put("note", note == null ? "" : note);
        row.put("addedAt", Instant.now().toString()); row.put("metricsAvailable", false);
        // 긴급 뉴스 수동 주입은 즉시 같은 공개 API 검색을 한 번 수행한다.
        try {
            KeywordSearchResponse response = fastApiClient.searchKeywords(keyword.trim(), 1,
                    category == null ? "CUSTOM" : category, 1, 0L);
            if (response.getCandidates() != null && !response.getCandidates().isEmpty()) {
                KeywordItemDto item = response.getCandidates().get(0);
                row.put("views", item.getViews()); row.put("subscribers", item.getSubscribers());
                row.put("likes", item.getLikes()); row.put("comments", item.getComments());
                row.put("viewsPerSubscriber", ratio(item.getViews(), item.getSubscribers()));
                row.put("velocityVph", item.getVelocityVph()); row.put("evidenceVideoIds", item.getEvidenceVideoIds());
                row.put("metricsAvailable", true);
            }
        } catch (Exception e) { log.warn("manual keyword metrics unavailable: {}", e.getMessage()); }
        synchronized (manual) { manual.removeIf(x -> keyword.trim().equalsIgnoreCase(String.valueOf(x.get("keyword")))); manual.add(row); }
        return row;
    }

    private static Double ratio(Long views, Long subscribers) {
        return views != null && subscribers != null && subscribers > 0 ? views.doubleValue() / subscribers : null;
    }
}
