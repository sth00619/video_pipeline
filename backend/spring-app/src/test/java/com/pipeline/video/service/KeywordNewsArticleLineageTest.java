package com.pipeline.video.service;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.pipeline.video.domain.Asset;
import com.pipeline.video.domain.AssetType;
import com.pipeline.video.domain.Autonomy;
import com.pipeline.video.domain.JobStatus;
import com.pipeline.video.domain.VideoJob;
import com.pipeline.video.dto.KeywordItemDto;
import com.pipeline.video.repository.AssetRepository;
import com.pipeline.video.repository.VideoJobRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

import java.util.List;
import java.util.Map;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class KeywordNewsArticleLineageTest {

    private final ObjectMapper objectMapper = new ObjectMapper();
    private VideoJobRepository jobRepository;
    private AssetRepository assetRepository;
    private GateService gateService;
    private KeywordService keywordService;

    @BeforeEach
    void setUp() {
        jobRepository = mock(VideoJobRepository.class);
        assetRepository = mock(AssetRepository.class);
        gateService = mock(GateService.class);
        keywordService = new KeywordService(
                jobRepository,
                assetRepository,
                mock(FastApiClient.class),
                gateService,
                mock(AutonomyService.class),
                mock(KeywordAliasService.class),
                mock(CostService.class)
        );

        VideoJob job = VideoJob.builder()
                .id(1L)
                .title("키워드 기사 계보 테스트")
                .keyword("삼성전자")
                .status(JobStatus.KEYWORD_PENDING)
                .autonomy(Autonomy.GUIDED)
                .build();
        when(jobRepository.findById(1L)).thenReturn(Optional.of(job));
    }

    @Test
    void keywordItemDto_deserializesNewsArticles() throws Exception {
        String json = """
                {
                  "keyword": "삼성전자",
                  "score": 75,
                  "news_articles": [
                    {"title": "테스트", "link": "https://yna.co.kr/1", "outlet": "연합뉴스"}
                  ]
                }
                """;

        KeywordItemDto dto = objectMapper.readValue(json, KeywordItemDto.class);

        assertThat(dto.getNewsArticles()).hasSize(1);
        assertThat(dto.getNewsArticles().get(0))
                .containsEntry("link", "https://yna.co.kr/1");
    }

    @Test
    void keywordItemDto_toleratesAbsentNewsArticles() throws Exception {
        KeywordItemDto dto = objectMapper.readValue(
                "{\"keyword\": \"코스피\", \"score\": 60}",
                KeywordItemDto.class
        );

        assertThat(dto.getNewsArticles()).isNull();
    }

    @Test
    void confirm_preservesNewsArticlesInSelectedKeywordAsset() throws Exception {
        when(assetRepository.findByJobIdAndAssetType(1L, AssetType.KEYWORD)).thenReturn(List.of(
                keywordSearchAsset("""
                        [{
                          "keyword": "삼성전자",
                          "score": 75,
                          "evidence": {"news_count": 1},
                          "news_articles": [
                            {"title": "뉴스", "link": "https://yna.co.kr/1", "outlet": "연합뉴스"}
                          ]
                        }]
                        """)
        ));

        keywordService.confirm(1L, "삼성전자", "admin");

        Map<String, Object> selected = capturedSelectedAsset();
        assertThat(selected.get("news_articles")).isInstanceOf(List.class);
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> articles =
                (List<Map<String, Object>>) selected.get("news_articles");
        assertThat(articles).hasSize(1);
        assertThat(articles.get(0)).containsEntry("link", "https://yna.co.kr/1");
    }

    @Test
    void confirm_handlesNullNewsArticles() {
        when(assetRepository.findByJobIdAndAssetType(1L, AssetType.KEYWORD)).thenReturn(List.of(
                keywordSearchAsset("""
                        [{
                          "keyword": "삼성전자",
                          "score": 60,
                          "evidence": {"news_count": 0},
                          "news_articles": null
                        }]
                        """)
        ));

        assertThatCode(() -> keywordService.confirm(1L, "삼성전자", "admin"))
                .doesNotThrowAnyException();

        Map<String, Object> selected = capturedSelectedAsset();
        assertThat(selected).containsKey("news_articles");
        assertThat(selected.get("news_articles")).isNull();
    }

    private Asset keywordSearchAsset(String candidatesJson) {
        return Asset.builder()
                .jobId(1L)
                .assetType(AssetType.KEYWORD)
                .metaJson("{\"candidates\":" + candidatesJson + "}")
                .build();
    }

    private Map<String, Object> capturedSelectedAsset() {
        ArgumentCaptor<Asset> captor = ArgumentCaptor.forClass(Asset.class);
        verify(assetRepository).save(captor.capture());
        assertThat(captor.getValue().getAssetType()).isEqualTo(AssetType.KEYWORD);
        try {
            return objectMapper.readValue(
                    captor.getValue().getMetaJson(),
                    new TypeReference<>() {
                    }
            );
        } catch (Exception exception) {
            throw new AssertionError("선택 KEYWORD 에셋 JSON을 읽을 수 없습니다.", exception);
        }
    }
}
