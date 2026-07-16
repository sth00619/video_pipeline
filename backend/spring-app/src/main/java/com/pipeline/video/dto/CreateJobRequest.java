package com.pipeline.video.dto;

import com.pipeline.video.domain.Autonomy;
import com.pipeline.video.domain.Category;
import com.pipeline.video.domain.Format;
import com.pipeline.video.domain.RenderProfile;
import lombok.Data;

import java.math.BigDecimal;

@Data
public class CreateJobRequest {
    private String title;
    private String keyword;
    private Category category;                       // 주식 카테고리
    private Autonomy autonomy = Autonomy.GUIDED;
    private Format format = Format.FACELESS_NARRATION;
    private RenderProfile renderProfile = RenderProfile.LONGFORM_16x9;
    private boolean makeShorts = false;
    private Integer shortsCount = 3;
    private Integer longformTargetMinutes = 20;       // 15/20/30 등 유동적
    private BigDecimal budgetCap;
    private String policyJson;
    private String channelId;
    private String characterOverride;
    private boolean dataVisualsEnabled = true;
}
