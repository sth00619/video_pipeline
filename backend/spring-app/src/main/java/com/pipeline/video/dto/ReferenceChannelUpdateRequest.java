package com.pipeline.video.dto;

import com.pipeline.video.domain.ReferenceChannelTier;
import jakarta.validation.constraints.NotBlank;

public record ReferenceChannelUpdateRequest(
        @NotBlank(message = "표시 이름은 필수입니다.") String displayName,
        ReferenceChannelTier tier,
        Integer displayOrder,
        Boolean active
) {
}
