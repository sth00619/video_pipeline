package com.pipeline.video.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;

/**
 * 쇼츠 클립 정보 DTO
 * @JsonProperty로 Python snake_case ↔ Java camelCase 통일
 */
@Data
public class ShortClipInfo {

    @JsonProperty("shorts_job_id")
    private Long shortsJobId;

    private Integer index;
    private String text;
    private String label;
    private Double start;
    private Double end;
    private Double duration;

    @JsonProperty("output_path")
    private String outputPath;

    @JsonProperty("file_size_mb")
    private Double fileSizeMb;

    @JsonProperty("download_ready")
    private Boolean downloadReady;
}
