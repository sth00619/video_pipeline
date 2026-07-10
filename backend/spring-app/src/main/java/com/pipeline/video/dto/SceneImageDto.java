package com.pipeline.video.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;

@Data
@JsonIgnoreProperties(ignoreUnknown = true)
public class SceneImageDto {
    @JsonProperty("index")
    private Integer index;

    @JsonProperty("image_path")
    private String imagePath;

    @JsonProperty("prompt")
    private String prompt;

    @JsonProperty("text")
    private String text;

    @JsonProperty("start")
    private Double start;

    @JsonProperty("duration")
    private Double duration;

    @JsonProperty("section")
    private String section;
}
