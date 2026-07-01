package com.pipeline.video.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;

@Data
@JsonIgnoreProperties(ignoreUnknown = true)
public class LongformGenerateResponse {
    @JsonProperty("job_id")
    private Long jobId;

    @JsonProperty("video_path")
    private String videoPath;

    @JsonProperty("duration_seconds")
    private Double durationSeconds;

    @JsonProperty("scene_count")
    private Integer sceneCount;

    @JsonProperty("gif_count")
    private Integer gifCount;

    @JsonProperty("has_subtitles")
    private Boolean hasSubtitles;

    @JsonProperty("resolution")
    private String resolution;
}
