package com.pipeline.video.dto;

import com.pipeline.video.domain.Autonomy;
import com.pipeline.video.domain.Format;
import com.pipeline.video.domain.RenderProfile;
import lombok.Data;

import java.math.BigDecimal;

@Data
public class CreateJobRequest {
    private String title;
    private String keyword;
    private Autonomy autonomy = Autonomy.MANUAL;
    private Format format = Format.FACELESS_NARRATION;
    private RenderProfile renderProfile = RenderProfile.LONGFORM_16x9;
    private boolean makeShorts = false;
    private Integer shortsCount = 3;
    private Integer longformTargetMinutes = 20;
    private BigDecimal budgetCap;
    // 자유 정책 JSON (확장용)
    private String policyJson;
}
