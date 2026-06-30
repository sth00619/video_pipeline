package com.pipeline.video.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;

import java.util.List;

@Data
@JsonIgnoreProperties(ignoreUnknown = true)
public class TtsGenerateResponse {
    @JsonProperty("job_id")
    private Long jobId;

    @JsonProperty("audio_path")
    private String audioPath;

    @JsonProperty("voice_id")
    private String voiceId;

    @JsonProperty("total_duration")
    private Double totalDuration;

    @JsonProperty("chunks")
    private List<TtsChunkDto> chunks;
}
