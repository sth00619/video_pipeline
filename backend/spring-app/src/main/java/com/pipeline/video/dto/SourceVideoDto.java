package com.pipeline.video.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;

@Data
@JsonIgnoreProperties(ignoreUnknown = true)
public class SourceVideoDto {
    @JsonProperty("title")
    private String title;

    @JsonProperty("channel_title")
    private String channelTitle;

    @JsonProperty("views")
    private Long views;

    @JsonProperty("subscribers")
    private Long subscribers;

    @JsonProperty("hours_since_publish")
    private Double hoursSincePublish;
}
