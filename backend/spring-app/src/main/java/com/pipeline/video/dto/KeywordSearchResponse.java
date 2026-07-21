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

    @JsonProperty("selection_path")
    private String selectionPath;

    @JsonProperty("selected_keyword")
    private String selectedKeyword;

    @JsonProperty("selection_reason")
    private String selectionReason;

    @JsonProperty("time_interpretation")
    private Map<String, Object> timeInterpretation;

    @JsonProperty("topic_evidence_required")
    private Boolean topicEvidenceRequired;

    @JsonProperty("top_candidate_keyword")
    private String topCandidateKeyword;

    @JsonProperty("auto_confirmable")
    private Boolean autoConfirmable;
}
