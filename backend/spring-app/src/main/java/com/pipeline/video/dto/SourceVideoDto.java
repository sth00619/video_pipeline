package com.pipeline.video.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;

@Data
@JsonIgnoreProperties(ignoreUnknown = true)
public class SourceVideoDto {
    @JsonProperty("title")
    private String title;

    @JsonProperty("channel_title")
    private String channelTitle;

    @JsonProperty("views")
    private Long views;

    @JsonProperty("subscribers")
    private Long subscribers;

    @JsonProperty("video_id")
    private String videoId;

    @JsonProperty("likes")
    private Long likes;

    @JsonProperty("comments")
    private Long comments;

    @JsonProperty("likes_available")
    private Boolean likesAvailable;

    @JsonProperty("comments_available")
    private Boolean commentsAvailable;

    @JsonProperty("duration_seconds")
    private Double durationSeconds;

    @JsonProperty("average_view_duration_seconds")
    private Double averageViewDurationSeconds;

    @JsonProperty("average_view_percentage")
    private Double averageViewPercentage;

    @JsonProperty("retention_available")
    private Boolean retentionAvailable;

    @JsonProperty("channel_avg_views_is_sample")
    private Boolean channelAvgViewsIsSample;

    @JsonProperty("subscriber_count_available")
    private Boolean subscriberCountAvailable;

    @JsonProperty("hours_since_publish")
    private Double hoursSincePublish;
}
