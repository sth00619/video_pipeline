package com.pipeline.video.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;

import java.util.List;

@Data
@JsonIgnoreProperties(ignoreUnknown = true)
public class KeywordSearchResponse {
    @JsonProperty("job_id")
    private Long jobId;

    @JsonProperty("seed")
    private String seed;

    @JsonProperty("candidates")
    private List<KeywordItemDto> candidates;
}
