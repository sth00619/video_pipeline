package com.pipeline.video.service;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.pipeline.video.dto.TrendingVideoDto;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

import java.time.Duration;
import java.util.List;

@Slf4j
@Service
@RequiredArgsConstructor
public class TrendingService {

    private final StringRedisTemplate redisTemplate;
    private final FastApiClient fastApiClient;
    private final ObjectMapper objectMapper;

    public List<TrendingVideoDto> getTrendingVideos(String keyword) {
        String redisKey = "youtube:trending:" + keyword;

        try {
            // 1. Redis Cache Hit 체크
            String cachedJson = redisTemplate.opsForValue().get(redisKey);
            if (cachedJson != null) {
                log.info("Redis Cache Hit: {}", redisKey);
                return objectMapper.readValue(cachedJson, new TypeReference<List<TrendingVideoDto>>() {});
            }
        } catch (Exception e) {
            log.warn("Redis 조회 오류: {}", e.getMessage());
        }

        log.info("Redis Cache Miss: {}, FastAPI 수집 호출", redisKey);
        
        // 2. FastAPI (YouTube Data API) 호출
        int limit = 10;
        List<TrendingVideoDto> videos = fastApiClient.getTrendingVideos(keyword, limit);

        // 3. Redis 에 1시간 저장
        try {
            if (videos != null && !videos.isEmpty()) {
                String json = objectMapper.writeValueAsString(videos);
                redisTemplate.opsForValue().set(redisKey, json, Duration.ofHours(1));
                log.info("Redis 캐시 저장 성공: {} (1시간)", redisKey);
            }
        } catch (Exception e) {
            log.warn("Redis 저장 오류: {}", e.getMessage());
        }

        return videos != null ? videos : List.of();
    }
}
