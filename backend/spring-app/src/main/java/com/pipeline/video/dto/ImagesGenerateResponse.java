package com.pipeline.video.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;

import java.util.List;

@Data
@JsonIgnoreProperties(ignoreUnknown = true)
public class ImagesGenerateResponse {
    @JsonProperty("job_id")
    private Long jobId;

    @JsonProperty("scene_count")
    private Integer sceneCount;

    @JsonProperty("gif_count")
    private Integer gifCount;

    @JsonProperty("scenes")
    private List<SceneImageDto> scenes;

    @JsonProperty("gifs")
    private List<GifClipDto> gifs;
}
