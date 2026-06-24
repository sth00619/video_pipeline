package com.pipeline.video.dto;

import com.pipeline.video.domain.*;
import lombok.Data;

import java.math.BigDecimal;
import java.time.LocalDateTime;

@Data
public class JobResponse {
    private Long id;
    private String title;
    private String keyword;
    private JobStatus status;
    private Autonomy autonomy;
    private Format format;
    private RenderProfile renderProfile;
    private boolean makeShorts;
    private Integer shortsCount;
    private Integer longformTargetMinutes;
    private BigDecimal budgetCap;
    private BigDecimal costAccumulated;
    private String createdBy;
    private String sourceVideoPath;
    private String outputPath;
    private String policyJson;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;

    public static JobResponse from(VideoJob job) {
        JobResponse r = new JobResponse();
        r.setId(job.getId());
        r.setTitle(job.getTitle());
        r.setKeyword(job.getKeyword());
        r.setStatus(job.getStatus());
        r.setAutonomy(job.getAutonomy());
        r.setFormat(job.getFormat());
        r.setRenderProfile(job.getRenderProfile());
        r.setMakeShorts(job.isMakeShorts());
        r.setShortsCount(job.getShortsCount());
        r.setLongformTargetMinutes(job.getLongformTargetMinutes());
        r.setBudgetCap(job.getBudgetCap());
        r.setCostAccumulated(job.getCostAccumulated());
        r.setCreatedBy(job.getCreatedBy());
        r.setSourceVideoPath(job.getSourceVideoPath());
        r.setOutputPath(job.getOutputPath());
        r.setPolicyJson(job.getPolicyJson());
        r.setCreatedAt(job.getCreatedAt());
        r.setUpdatedAt(job.getUpdatedAt());
        return r;
    }
}
