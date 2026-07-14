package com.pipeline.video.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;

@Data
@JsonIgnoreProperties(ignoreUnknown = true)
public class ShortsSegmentDto {
    @JsonProperty("index")
    private Integer index;

    @JsonProperty("title")
    private String title;

    @JsonProperty("text")
    private String text;

    @JsonProperty("start")
    private Double start;

    @JsonProperty("end")
    private Double end;

    @JsonProperty("duration")
    private Double duration;

    @JsonProperty("reason")
    private String reason;
}
