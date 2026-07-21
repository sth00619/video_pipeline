package com.pipeline.video.service;

import java.util.List;

/** A FastAPI validation response that returns the job to keyword research. */
public class ScriptResearchRequiredException extends RuntimeException {
    private final List<String> missingTerms;

    public ScriptResearchRequiredException(String message, List<String> missingTerms) {
        super(message);
        this.missingTerms = missingTerms == null ? List.of() : List.copyOf(missingTerms);
    }

    public List<String> getMissingTerms() {
        return missingTerms;
    }
}
