package com.pipeline.video.dto;

import lombok.Getter;
import lombok.Setter;

@Getter
@Setter
public class CharacterLibraryGenerateRequest {
    private String characterDescription;
    private boolean regenerate;
}
