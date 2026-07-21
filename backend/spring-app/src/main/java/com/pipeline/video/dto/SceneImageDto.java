package com.pipeline.video.dto;

import com.fasterxml.jackson.annotation.JsonAnyGetter;
import com.fasterxml.jackson.annotation.JsonAnySetter;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;

import java.util.Map;
import java.util.List;
import java.util.LinkedHashMap;

@Data
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

    /**
     * On-screen subtitle override.  It is intentionally separate from the
     * Korean narration source so caption-only edits never change the image
     * prompt or ask the TTS/image stages to run again.
     */
    @JsonProperty("subtitle_text")
    private String subtitleText;

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

    /** Verified post-production graphics must survive the
     * Python -> Spring asset -> Python longform round trip. */
    @JsonProperty("market_chart")
    private Map<String, Object> marketChart;

    @JsonProperty("index_data")
    private Map<String, Object> indexData;

    @JsonProperty("motion_type")
    private String motionType;

    @JsonProperty("bubble_text")
    private String bubbleText;

    @JsonProperty("headline")
    private String headline;

    @JsonProperty("headline_mood")
    private String headlineMood;

    @JsonProperty("style_profile")
    private String styleProfile;

    @JsonProperty("scene_spec")
    private Map<String, Object> sceneSpec;

    @JsonProperty("quality_score")
    private Integer qualityScore;

    @JsonProperty("generation_method")
    private String generationMethod;

    @JsonProperty("use_kling")
    private Boolean useKling;

    @JsonProperty("quality_flags")
    private List<String> qualityFlags;

    @JsonProperty("retry_recommended")
    private Boolean retryRecommended;

    @JsonProperty("semantic_score")
    private Integer semanticScore;

    @JsonProperty("semantic_reason")
    private String semanticReason;

    /**
     * Preserve metadata emitted by Python even before Spring has a strongly
     * typed field for it. Dropping an unknown scene field here can silently
     * remove a verified graphic or motion instruction before assembly.
     */
    private final Map<String, Object> passthrough = new LinkedHashMap<>();

    @JsonAnySetter
    public void putPassthrough(String name, Object value) {
        passthrough.put(name, value);
    }

    @JsonAnyGetter
    public Map<String, Object> getPassthrough() {
        return passthrough;
    }
}
