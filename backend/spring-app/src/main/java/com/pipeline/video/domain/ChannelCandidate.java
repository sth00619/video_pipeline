package com.pipeline.video.domain;

import com.fasterxml.jackson.annotation.JsonProperty;

public record ChannelCandidate(
        @JsonProperty("channel_id") String channelId,
        String title,
        String handle,
        String description,
        @JsonProperty("thumbnail_url") String thumbnailUrl,
        @JsonProperty("subscriber_count") Long subscriberCount,
        @JsonProperty("subscriber_count_available") boolean subscriberCountAvailable,
        @JsonProperty("hidden_subscriber_count") boolean hiddenSubscriberCount,
        @JsonProperty("total_view_count") Long totalViewCount,
        @JsonProperty("video_count") Long videoCount
) {
}
