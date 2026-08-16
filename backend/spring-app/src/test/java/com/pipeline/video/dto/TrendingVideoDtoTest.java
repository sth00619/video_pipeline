package com.pipeline.video.dto;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

class TrendingVideoDtoTest {

    private final ObjectMapper objectMapper = new ObjectMapper();

    @Test
    void b4OutperformerFieldsAreDeserializedFromFastApiSnakeCaseResponse() {
        TrendingVideoDto dto = objectMapper.convertValue(Map.of(
                "channel_recent_avg_views", 120_000,
                "channel_recent_sample_size", 10,
                "outperformer_basis", "recent_average_1_5x"
        ), TrendingVideoDto.class);

        assertThat(dto.getChannelRecentAvgViews()).isEqualTo(120_000L);
        assertThat(dto.getChannelRecentSampleSize()).isEqualTo(10);
        assertThat(dto.getOutperformerBasis()).isEqualTo("recent_average_1_5x");
    }
}
