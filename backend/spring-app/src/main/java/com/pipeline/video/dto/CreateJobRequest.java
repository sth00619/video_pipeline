package com.pipeline.video.dto;

import com.pipeline.video.domain.Autonomy;
import com.pipeline.video.domain.RenderProfile;
import lombok.Data;

import java.math.BigDecimal;

@Data
public class CreateJobRequest {
    private String title;
    private String keyword;
    private Autonomy autonomy;
    private RenderProfile renderProfile;
    private boolean makeShorts;
    private Integer shortsCount;
    private BigDecimal budgetCap;
}
