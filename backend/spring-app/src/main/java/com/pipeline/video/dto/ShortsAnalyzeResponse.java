package com.pipeline.video.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;

import java.util.List;
import java.util.Map;

@Data
@JsonIgnoreProperties(ignoreUnknown = true)
public class ShortsAnalyzeResponse {

    @JsonProperty("job_id")
    private Long jobId;

    @JsonProperty("source_video_path")
    private String sourceVideoPath;

    @JsonProperty("transcript")
    private String transcript;

    @JsonProperty("words")
    private List<Map<String, Object>> words;

    @JsonProperty("transcript_segments")
    private List<ShortsSegmentDto> transcriptSegments;

    @JsonProperty("suggested_segments")
    private List<ShortsSegmentDto> suggestedSegments;

    @JsonProperty("total_duration")
    private Double totalDuration;
}
