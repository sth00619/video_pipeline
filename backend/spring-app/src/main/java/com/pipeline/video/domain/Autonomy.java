package com.pipeline.video.domain;

public enum Autonomy {
    /** Legacy value retained only so existing database rows can be read. New jobs are normalized to GUIDED. */
    @Deprecated
    MANUAL,
    GUIDED,
    AUTO
}
