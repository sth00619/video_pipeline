package com.pipeline.video.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;

@Data
public class TtsChunkDto {
    @JsonProperty("index")
    private Integer index;

    @JsonProperty("text")
    private String text;

    @JsonProperty("start")
    private Double start;

    @JsonProperty("duration")
    private Double duration;
}
