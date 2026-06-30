package com.pipeline.video.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;

@Data
@JsonIgnoreProperties(ignoreUnknown = true)
public class GifClipDto {
    @JsonProperty("index")
    private Integer index;

    @JsonProperty("gif_path")
    private String gifPath;

    @JsonProperty("prompt")
    private String prompt;

    @JsonProperty("insert_at")
    private Double insertAt;

    @JsonProperty("duration")
    private Double duration;
}
