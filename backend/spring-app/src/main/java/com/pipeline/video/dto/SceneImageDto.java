package com.pipeline.video.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;

import java.util.Map;
import java.util.List;

@Data
@JsonIgnoreProperties(ignoreUnknown = true)
public class SceneImageDto {
    @JsonProperty("index")
    private Integer index;

    @JsonProperty("image_path")
    private String imagePath;

    @JsonProperty("prompt")
    private String prompt;

    @JsonProperty("prompt_ko")
    private String promptKo;

    @JsonProperty("prompt_en")
    private String promptEn;

    @JsonProperty("pose")
    private String pose;

    @JsonProperty("text")
    private String text;

    @JsonProperty("start")
    private Double start;

    @JsonProperty("duration")
    private Double duration;

    @JsonProperty("section")
    private String section;

    @JsonProperty("visual_type")
    private String visualType;

    @JsonProperty("visual_plan")
    private Map<String, Object> visualPlan;

    @JsonProperty("art_direction")
    private Map<String, Object> artDirection;

    @JsonProperty("image_profile")
    private Map<String, Object> imageProfile;

    @JsonProperty("market_snapshot")
    private Map<String, Object> marketSnapshot;

    @JsonProperty("quality_score")
    private Integer qualityScore;

    @JsonProperty("quality_flags")
    private List<String> qualityFlags;

    @JsonProperty("retry_recommended")
    private Boolean retryRecommended;

    @JsonProperty("semantic_score")
    private Integer semanticScore;

    @JsonProperty("semantic_reason")
    private String semanticReason;
}
