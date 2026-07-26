package com.pipeline.video.dto;

import lombok.Getter;
import lombok.Setter;

@Getter
@Setter
public class CharacterLibraryGenerateRequest {
    private String characterDescription;
    private boolean regenerate;
    /** Explicitly opt in to the 5 roles × 3 emotional-state asset set. */
    private boolean includeRoleCostumes;
}
