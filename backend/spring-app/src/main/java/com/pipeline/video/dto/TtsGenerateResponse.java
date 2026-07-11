package com.pipeline.video.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;

import java.util.List;

/**
 * TTS 생성 응답 DTO.
 *
 * usedGtts / usedElevenlabs 필드를 추가했습니다:
 *   FastAPI 워커의 tts_worker.py는 이미 이 두 필드를 응답에 담아 보내고 있고,
 *   프론트 JobDetail.jsx도 ttsInfo.used_gtts를 표시하려 하는데,
 *   중간의 이 DTO에 필드가 없어서 값이 조용히 유실되고 있었습니다.
 *   (@JsonIgnoreProperties(ignoreUnknown=true) 때문에 예외는 안 났지만 값도 안 남음)
 *   이 두 필드가 있어야 TtsService의 비용 계산 분기(paid vs free)도 제대로 동작합니다.
 */
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

    @JsonProperty("used_gtts")
    private Boolean usedGtts;

    @JsonProperty("used_elevenlabs")
    private Boolean usedElevenlabs;
}
