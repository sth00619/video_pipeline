package com.pipeline.video.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;

@Data
public class KeywordItemDto {
    @JsonProperty("keyword")
    private String keyword;

    @JsonProperty("search_volume")
    private Integer searchVolume;

    @JsonProperty("competition")
    private String competition;

    @JsonProperty("reason")
    private String reason;
}
