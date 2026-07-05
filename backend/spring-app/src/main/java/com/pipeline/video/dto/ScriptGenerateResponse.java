package com.pipeline.video.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;

import java.util.List;
import java.util.Map;

@Data
@JsonIgnoreProperties(ignoreUnknown = true)
public class ScriptGenerateResponse {
    @JsonProperty("job_id")
    private Long jobId;

    @JsonProperty("keyword")
    private String keyword;

    @JsonProperty("synopsis")
    private String synopsis;

    @JsonProperty("script")
    private String script;

    @JsonProperty("sections")
    private List<Map<String, Object>> sections;

    @JsonProperty("estimated_minutes")
    private Double estimatedMinutes;

    @JsonProperty("char_count")
    private Integer charCount;

    // v3 팩트체크 결과
    @JsonProperty("verified_facts")
    private List<Map<String, Object>> verifiedFacts;

    @JsonProperty("fact_check_rounds")
    private Integer factCheckRounds;

    @JsonProperty("fact_check_log")
    private List<String> factCheckLog;

    @JsonProperty("market_snapshot_used")
    private Boolean marketSnapshotUsed;

    @JsonProperty("used_real_llm")
    private Boolean usedRealLlm;
}
