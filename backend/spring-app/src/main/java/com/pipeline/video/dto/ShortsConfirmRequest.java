package com.pipeline.video.dto;

import lombok.Data;

import java.util.List;

@Data
public class ShortsConfirmRequest {
    private Long shortsJobId;
    private List<ShortsSegmentDto> segments;
}
