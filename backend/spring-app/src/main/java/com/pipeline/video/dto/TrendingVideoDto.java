package com.pipeline.video.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;
import java.util.List;

import com.fasterxml.jackson.databind.annotation.JsonNaming;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public class TrendingVideoDto {
    private String title;
    private String channelTitle;
    private String videoId;
    private Long views;
    private Long subscribers;
    private Long channelAvgViews;
    private String publishedAt;
    private Double hoursSincePublish;
    private String channelId;
    private Long likes;
    private Long comments;
    private Boolean likesAvailable;
    private Boolean commentsAvailable;
    private Double durationSeconds;
    private Double averageViewDurationSeconds;
    private Double averageViewPercentage;
    private Boolean retentionAvailable;
    private String statisticsAsOf;
    private Boolean channelAvgViewsIsSample;
    private Boolean subscriberCountAvailable;
    private Boolean isLive;
    private List<String> tags;
    private String categoryId;
    private Double performanceScore;
    private String performanceGrade;
    private List<String> topComments;
}
