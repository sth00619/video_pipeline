package com.pipeline.video.service;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.pipeline.video.domain.*;
import com.pipeline.video.dto.KeywordSearchResponse;
import com.pipeline.video.repository.AssetRepository;
import com.pipeline.video.repository.VideoJobRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * Phase 3-1 — 키워드 탐색 (주식 콘텐츠 특화)
 *
 *  outperformer 표시 정책:
 *   - AUTO 모드: 1위 후보만 outperformer (자동 선택될 후보)
 *   - MANUAL/GUIDED: 상위 3위까지 outperformer (관리자 비교 편의)
 */
@Service
@Slf4j
@RequiredArgsConstructor
public class KeywordService {

    private final VideoJobRepository jobRepository;
    private final AssetRepository assetRepository;
    private final FastApiClient fastApiClient;
    private final GateService gateService;
    private final AutonomyService autonomyService;
    private final KeywordAliasService keywordAliasService;
    private final CostService costService;
    private final ObjectMapper objectMapper = new ObjectMapper();

    @Transactional
    public KeywordSearchResponse search(Long jobId, String seedKeyword, int limit,
                                        Category category, String username) {
        VideoJob job = jobRepository.findById(jobId)
                .orElseThrow(() -> new RuntimeException("Job not found: " + jobId));

        if (job.getStatus() != JobStatus.DRAFT && job.getStatus() != JobStatus.KEYWORD_PENDING) {
            throw new IllegalStateException("키워드 탐색은 DRAFT/KEYWORD_PENDING 에서만 가능. 현재: " + job.getStatus());
        }

        // category 우선순위: 요청 > job 저장값 > CUSTOM
        Category effectiveCategory = category != null ? category
                : (job.getCategory() != null ? job.getCategory() : Category.CUSTOM);

        // outperformer 개수: AUTO=1, MANUAL/GUIDED=3
        int outperformerCount = autonomyService.isAuto(job) ? 1 : 3;

        log.info("키워드 탐색: jobId={}, category={}, seed={}, autonomy={}, outperformerCount={}",
                jobId, effectiveCategory, seedKeyword, job.getAutonomy(), outperformerCount);

        // FastAPI 호출
        KeywordSearchResponse result = fastApiClient.searchKeywords(
                seedKeyword, limit, effectiveCategory.name(), outperformerCount, jobId);

        // 비용 기록 (Mock $0)
        costService.record(jobId, "YOUTUBE_API", BigDecimal.ZERO, "USD", "키워드 트렌드 분석");

        // category를 Job에 저장
        job.setCategory(effectiveCategory);

        String selectedKeyword = null;
        String selectionPath = null;
        String selectionReason = null;
        if (autonomyService.isAuto(job) && result.getCandidates() != null
                && !result.getCandidates().isEmpty()
                && !Boolean.TRUE.equals(result.getTopicEvidenceRequired())) {
            String inputKeyword = normalizeKeyword(seedKeyword);
            String existingKeyword = normalizeKeyword(job.getKeyword());

            // Selection priority is intentionally independent of news volume,
            // video metrics, and candidate ranking. A supplied input is the
            // editor's brief and therefore always wins.
            if (!inputKeyword.isBlank()) {
                selectedKeyword = inputKeyword;
                selectionPath = "INPUT_KEYWORD";
                selectionReason = "입력 키워드가 있어 그대로 확정했습니다: " + selectedKeyword;
            } else if (!existingKeyword.isBlank()) {
                selectedKeyword = existingKeyword;
                selectionPath = "EXISTING_JOB_KEYWORD";
                selectionReason = "기존에 확정된 작업 키워드를 유지했습니다: " + selectedKeyword;
            } else {
                selectedKeyword = result.getCandidates().get(0).getKeyword();
                selectionPath = "AUTO_DISCOVERY";
                String rankingSummary = normalizeKeyword(result.getCandidates().get(0).getReason());
                selectionReason = "입력 키워드가 없어 후보 1위를 선택했습니다. 근거: "
                        + (rankingSummary.isBlank() ? "수집된 후보 순위" : rankingSummary);
            }
            result.setSelectionPath(selectionPath);
            result.setSelectedKeyword(selectedKeyword);
            result.setSelectionReason(selectionReason);
            // Persist canonical input terms in the decision text so the UI and
            // future audit can explain aliases such as 삼전→삼성전자.
            if (!keywordAliasService.terms(selectedKeyword).isEmpty()) {
                result.setSelectionReason(selectionReason + " · 정규화: " + String.join(", ", keywordAliasService.terms(selectedKeyword)));
            }
        }

        // Asset 저장 — selection_path/reason까지 함께 남겨 화면과 감사 로그가
        // 실제 결정 경로를 재현할 수 있게 한다.
        Asset asset = Asset.builder()
                .jobId(jobId)
                .assetType(AssetType.KEYWORD)
                .metaJson(safeJson(result))
                .build();
        assetRepository.save(asset);

        // 상태 전이
        job.setStatus(Boolean.TRUE.equals(result.getTopicEvidenceRequired())
                ? JobStatus.TOPIC_EVIDENCE_REQUIRED : JobStatus.KEYWORD_PENDING);
        jobRepository.save(job);

        if (selectedKeyword != null) {
            log.info("AUTO 모드 — {} 선택: {}", selectionPath, selectedKeyword);
            confirm(jobId, selectedKeyword, "AUTO");
        }

        return result;
    }

    @Transactional
    public void confirm(Long jobId, String selectedKeyword, String username) {
        VideoJob job = jobRepository.findById(jobId)
                .orElseThrow(() -> new RuntimeException("Job not found: " + jobId));

        if (job.getStatus() != JobStatus.KEYWORD_PENDING) {
            throw new IllegalStateException("키워드 확정은 KEYWORD_PENDING 에서만 가능. 현재: " + job.getStatus());
        }
        if (selectedKeyword == null || selectedKeyword.isBlank()) {
            throw new IllegalStateException("선택된 키워드가 비어있습니다.");
        }

        job.setKeyword(selectedKeyword);
        jobRepository.save(job);

        Asset selectedAsset = Asset.builder()
                .jobId(jobId)
                .assetType(AssetType.KEYWORD)
                .metaJson(safeJson(Map.of("selected", selectedKeyword, "final", true)))
                .build();
        assetRepository.save(selectedAsset);

        gateService.approve(jobId, GateName.KEYWORD, username, "선택: " + selectedKeyword);
        log.info("키워드 확정: jobId={}, keyword={}", jobId, selectedKeyword);
    }

    private String safeJson(Object obj) {
        try {
            return objectMapper.writeValueAsString(obj);
        } catch (JsonProcessingException e) {
            return "{}";
        }
    }

    private static String normalizeKeyword(String value) {
        return value == null ? "" : value.replaceAll("\\s+", " ").trim();
    }

    private static boolean isSpecificSeed(String seed) {
        return specificSeedTerms(seed).size() > 0;
    }

    private static boolean isSeedRelated(String candidate, String seed) {
        String compactCandidate = normalizeKeyword(candidate).replace(" ", "").toLowerCase();
        List<String> terms = specificSeedTerms(seed);
        int matches = 0;
        for (String term : terms) {
            if (compactCandidate.contains(term.toLowerCase())) {
                matches++;
            }
        }
        // A multi-term brief requires two distinctive terms. This prevents a
        // generic word such as "실적" from turning a Samsung request into a
        // general market earnings video.
        return matches >= (terms.size() > 1 ? 2 : 1);
    }

    private static List<String> specificSeedTerms(String seed) {
        java.util.Set<String> generic = java.util.Set.of(
                "코스피", "코스닥", "주식", "증시", "시장", "경제", "이슈", "뉴스",
                "관련", "분석", "전망", "영향", "주가", "오늘", "최근");
        List<String> terms = new ArrayList<>();
        for (String raw : normalizeKeyword(seed).split(" ")) {
            String term = raw.replaceAll("[^0-9A-Za-z가-힣]", "");
            if (!term.isBlank() && !term.matches("\\d+") && !generic.contains(term) && !terms.contains(term)) {
                terms.add(term);
            }
        }
        return terms;
    }
}
