package com.pipeline.video.dto;

import lombok.Data;

@Data
public class ShortClipInfo {
    private Integer index;
    private String text;
    private Double start;
    private Double end;
    private String outputPath;
}
