package com.pipeline.video.dto;

import lombok.Data;

import java.util.List;

@Data
public class ShortsConfirmRequest {
    private List<ShortsSegmentDto> segments;
}
