package com.pipeline.video.dto;

import lombok.Data;

@Data
public class KeywordSearchRequest {
    private String seedKeyword;
    private Integer limit = 5;
}
