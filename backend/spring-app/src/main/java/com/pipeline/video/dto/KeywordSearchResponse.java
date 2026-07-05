package com.pipeline.video.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;

import java.util.List;
import java.util.Map;

@Data
@JsonIgnoreProperties(ignoreUnknown = true)
public class KeywordSearchResponse {
    @JsonProperty("job_id")
    private Long jobId;

    @JsonProperty("seed")
    private String seed;

    @JsonProperty("category")
    private String category;

    @JsonProperty("candidates")
    private List<KeywordItemDto> candidates;

    // v2 실시간 시장 지표 스냅샷
    @JsonProperty("market_snapshot")
    private Map<String, Object> marketSnapshot;
}
