package com.pipeline.video.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;

@Data
@JsonIgnoreProperties(ignoreUnknown = true)
public class ScriptGenerateResponse {
    @JsonProperty("job_id")
    private Long jobId;

    @JsonProperty("synopsis")
    private String synopsis;

    @JsonProperty("script")
    private String script;

    @JsonProperty("estimated_minutes")
    private Double estimatedMinutes;

    @JsonProperty("char_count")
    private Integer charCount;
}
