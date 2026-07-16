package com.pipeline.video.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;

import java.util.List;

@Data
@JsonIgnoreProperties(ignoreUnknown = true)
public class KeywordItemDto {
    @JsonProperty("keyword")
    private String keyword;

    @JsonProperty("views")
    private Long views;

    @JsonProperty("subscribers")
    private Long subscribers;

    @JsonProperty("channel_avg_views")
    private Long channelAvgViews;

    @JsonProperty("search_volume")
    private Integer searchVolume;

    @JsonProperty("competition")
    private String competition;

    @JsonProperty("reason")
    private String reason;

    // 평가 지표 3종 (구독자 대비 조회수, 채널 평균 대비, 시간당)
    @JsonProperty("engagement_ratio")
    private Double engagementRatio;

    @JsonProperty("outperformance_index")
    private Double outperformanceIndex;

    @JsonProperty("velocity_vph")
    private Double velocityVph;

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

    @JsonProperty("evidence_video_ids")
    private List<String> evidenceVideoIds;

    @JsonProperty("is_outperformer")
    private Boolean isOutperformer;

    // 키워드가 추출된 원본 영상들의 메타 정보
    @JsonProperty("source_videos")
    private List<SourceVideoDto> sourceVideos;
}
