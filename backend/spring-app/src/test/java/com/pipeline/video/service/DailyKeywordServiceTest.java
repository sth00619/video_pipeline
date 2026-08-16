package com.pipeline.video.service;

import com.pipeline.video.dto.TrendingVideoDto;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class DailyKeywordServiceTest {

    @Mock
    private FastApiClient fastApiClient;

    private DailyKeywordService service;

    @BeforeEach
    void setUp() {
        service = new DailyKeywordService(fastApiClient);
    }

    @Test
    void crossSeedVideosAreDeduplicatedByVideoIdAndFirstOccurrenceIsKept() {
        when(fastApiClient.getTrendingVideos("코스피", 30))
                .thenReturn(List.of(video("코스피의 첫 근거", "dup-id")));
        when(fastApiClient.getTrendingVideos("코스닥", 30))
                .thenReturn(List.of(video("코스닥의 중복 근거", "dup-id")));
        when(fastApiClient.getTrendingVideos("미국 주식", 30)).thenReturn(List.of());

        List<Map<String, Object>> result = service.refreshToday();

        List<Map<String, Object>> duplicatedEvidence = result.stream()
                .filter(row -> evidenceIds(row).contains("dup-id"))
                .toList();
        assertThat(duplicatedEvidence).hasSize(1);
        assertThat(duplicatedEvidence.get(0))
                .containsEntry("category", "KOSPI")
                .containsEntry("keyword", "코스피의 첫 근거");
    }

    @Test
    void thirtyItemLimitIsAppliedAfterCrossSeedDeduplication() {
        List<TrendingVideoDto> kospi = new ArrayList<>();
        kospi.add(video("첫 중복 근거", "dup-id"));
        for (int index = 1; index <= 28; index++) {
            kospi.add(video("코스피 근거 " + index, "kospi-" + index));
        }
        when(fastApiClient.getTrendingVideos("코스피", 30)).thenReturn(kospi);
        when(fastApiClient.getTrendingVideos("코스닥", 30)).thenReturn(List.of(
                video("두 번째 중복 근거", "dup-id"),
                video("제한 전에 남아야 하는 근거", "fresh-id")
        ));
        when(fastApiClient.getTrendingVideos("미국 주식", 30)).thenReturn(List.of());

        List<Map<String, Object>> result = service.refreshToday();

        assertThat(result).hasSize(30);
        assertThat(result.stream().flatMap(row -> evidenceIds(row).stream()))
                .contains("fresh-id")
                .doesNotHaveDuplicates();
    }

    private static TrendingVideoDto video(String title, String videoId) {
        return TrendingVideoDto.builder()
                .title(title)
                .videoId(videoId)
                .channelTitle("검증 채널")
                .views(10_000L)
                .subscribers(5_000L)
                .hoursSincePublish(24d)
                .subscriberCountAvailable(true)
                .isLive(false)
                .durationSeconds(300d)
                .performanceScore(90d)
                .performanceGrade("A")
                .build();
    }

    private static List<String> evidenceIds(Map<String, Object> row) {
        Object value = row.get("evidenceVideoIds");
        if (!(value instanceof List<?> ids)) {
            return List.of();
        }
        return ids.stream().map(String::valueOf).toList();
    }
}
