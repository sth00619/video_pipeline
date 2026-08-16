package com.pipeline.video.dto;

import jakarta.validation.constraints.NotBlank;

public record ReferenceChannelConfirmItem(
        @NotBlank(message = "표시 이름은 필수입니다.") String displayName,
        @NotBlank(message = "확정할 채널 ID는 필수입니다.") String channelId,
        Integer displayOrder
) {
}
