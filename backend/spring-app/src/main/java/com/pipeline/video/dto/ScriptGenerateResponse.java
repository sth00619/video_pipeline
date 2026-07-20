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

    @JsonProperty("length_contract")
    private Map<String, Object> lengthContract;

    @JsonProperty("keyword_validation")
    private Map<String, Object> keywordValidation;

    @JsonProperty("unit_validation")
    private Map<String, Object> unitValidation;

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

    /** Mock output or a provider fallback must be reviewed before AUTO can continue. */
    @JsonProperty("requires_manual_review")
    private Boolean requiresManualReview;

    @JsonProperty("llm_provider_log")
    private List<java.util.Map<String, Object>> llmProviderLog;

    @JsonProperty("market_snapshot")
    private Map<String, Object> marketSnapshot;

    @JsonProperty("quality_report")
    private Map<String, Object> qualityReport;
}
