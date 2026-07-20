package com.pipeline.video.dto;

import lombok.Data;

import java.util.List;
import java.util.Map;

@Data
public class ScriptConfirmRequest {
    private String finalScript;
    private String comment;
    /** Preserve image-stage scene metadata while the operator approves narration. */
    private List<Map<String, Object>> sections;
}
