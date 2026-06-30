package com.pipeline.video.dto;

import com.pipeline.video.domain.Category;
import lombok.Data;

@Data
public class KeywordSearchRequest {
    private String seedKeyword;
    private Integer limit = 5;
    private Category category;   // 선택 (null이면 CUSTOM)
}
