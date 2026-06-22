package com.pipeline.video.dto;

import com.pipeline.video.domain.Autonomy;
import com.pipeline.video.domain.JobStatus;
import com.pipeline.video.domain.RenderProfile;
import com.pipeline.video.domain.VideoJob;
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
    private RenderProfile renderProfile;
    private String synopsis;
    private boolean makeShorts;
    private Integer shortsCount;
    private BigDecimal budgetCap;
    private BigDecimal costAccumulated;
    private String createdBy;
    private String outputPath;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;

    public static JobResponse from(VideoJob job) {
        JobResponse r = new JobResponse();
        r.setId(job.getId());
        r.setTitle(job.getTitle());
        r.setKeyword(job.getKeyword());
        r.setStatus(job.getStatus());
        r.setAutonomy(job.getAutonomy());
        r.setRenderProfile(job.getRenderProfile());
        r.setSynopsis(job.getSynopsis());
        r.setMakeShorts(job.isMakeShorts());
        r.setShortsCount(job.getShortsCount());
        r.setBudgetCap(job.getBudgetCap());
        r.setCostAccumulated(job.getCostAccumulated());
        r.setCreatedBy(job.getCreatedBy());
        r.setOutputPath(job.getOutputPath());
        r.setCreatedAt(job.getCreatedAt());
        r.setUpdatedAt(job.getUpdatedAt());
        return r;
    }
}
