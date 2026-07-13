package com.pipeline.video.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import lombok.Data;

@Data
@JsonIgnoreProperties(ignoreUnknown = true)
public class TtsChunkDto {
    @JsonProperty("index")
    private Integer index;

    @JsonProperty("text")
    private String text;

    @JsonProperty("start")
    private Double start;

    @JsonProperty("end")
    private Double end;

    @JsonProperty("duration")
    private Double duration;
}
