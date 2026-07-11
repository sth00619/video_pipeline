package com.pipeline.video.service;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.pipeline.video.domain.*;
import com.pipeline.video.dto.ScriptGenerateResponse;
import com.pipeline.video.repository.AssetRepository;
import com.pipeline.video.repository.VideoJobRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.util.Map;
import java.util.List;

@Service
@Slf4j
@RequiredArgsConstructor
public class ScriptService {

    private final VideoJobRepository jobRepository;
    private final AssetRepository assetRepository;
    private final FastApiClient fastApiClient;
    private final GateService gateService;
    private final AutonomyService autonomyService;
    private final CostService costService;
    private final ObjectMapper objectMapper = new ObjectMapper();

    @Transactional
    public ScriptGenerateResponse generate(Long jobId, String username) {
        VideoJob job = jobRepository.findById(jobId)
                .orElseThrow(() -> new RuntimeException("Job not found: " + jobId));

        if (job.getStatus() == JobStatus.DRAFT || job.getStatus() == JobStatus.KEYWORD_PENDING) {
            throw new IllegalStateException("키워드 확정 전에는 스크립트를 생성할 수 없습니다. 현재: " + job.getStatus());
        }
        if (job.getKeyword() == null || job.getKeyword().isBlank()) {
            throw new IllegalStateException("키워드가 선택되지 않음.");
        }

        int targetMinutes = job.getLongformTargetMinutes() != null
                ? job.getLongformTargetMinutes() : 20;
        // 1.25배속 가속을 고려하여 스크립트 분량을 1.25배 늘려서 생성
        int llmTargetMinutes = (int) Math.round(targetMinutes * 1.25);
        String categoryName = job.getCategory() != null ? job.getCategory().name() : "CUSTOM";

        log.info("스크립트 생성: jobId={}, keyword={}, target={}분 (LLM 타겟: {}분), category={}",
                jobId, job.getKeyword(), targetMinutes, llmTargetMinutes, categoryName);

        String marketSnapshotJson = null;
        try {
            // 해당 jobId의 KEYWORD 에셋 조회
            java.util.List<Asset> keywordAssets = assetRepository.findByJobIdAndAssetType(jobId, AssetType.KEYWORD);
            for (Asset a : keywordAssets) {
                if (a.getMetaJson() != null && a.getMetaJson().contains("market_snapshot")) {
                    Map<String, Object> metaMap = objectMapper.readValue(a.getMetaJson(), Map.class);
                    if (metaMap.containsKey("market_snapshot")) {
                        marketSnapshotJson = objectMapper.writeValueAsString(metaMap.get("market_snapshot"));
                        log.info("KEYWORD 에셋에서 market_snapshot 추출 성공");
                        break;
                    }
                }
            }
        } catch (Exception ex) {
            log.warn("KEYWORD 에셋에서 market_snapshot 추출 오류: {}", ex.getMessage());
        }

        ScriptGenerateResponse result = fastApiClient.generateScript(
                jobId, job.getKeyword(), llmTargetMinutes, categoryName, marketSnapshotJson);

        // [버그 수정] 기존에는 BigDecimal.ZERO로 하드코딩되어 있어서 스크립트 생성 비용이
        // 예산 누적에 전혀 반영되지 않았습니다 (JobDetail 비용 게이지가 항상 0으로 표시되던
        // 원인 중 하나). 이제 3-Round 팩트체크 왕복까지 감안한 근사치를 기록합니다.
        int outputChars = result.getCharCount() != null ? result.getCharCount() : 0;
        int inputChars = marketSnapshotJson != null ? marketSnapshotJson.length() : 500;
        java.math.BigDecimal claudeCost = CostEstimator.claude(inputChars, outputChars, 3);
        costService.record(jobId, "CLAUDE_LLM", claudeCost, "USD",
                String.format("스크립트 %d분 (실제 %d분) %d자, 3-Round 팩트체크", targetMinutes, llmTargetMinutes,
                        outputChars));

        Asset asset = Asset.builder()
                .jobId(jobId)
                .assetType(AssetType.SCRIPT)
                .metaJson(safeJson(result))
                .build();
        assetRepository.save(asset);

        if (autonomyService.isAuto(job)) {
            log.info("AUTO 모드 — 스크립트 자동 확정");
            confirm(jobId, result.getScript(), result.getSections(), "AUTO");
        }

        return result;
    }

    @Transactional
    public void confirm(Long jobId, String finalScript, String username) {
        confirm(jobId, finalScript, null, username);
    }

    @Transactional
    public void confirm(Long jobId, String finalScript, List<Map<String, Object>> inputSections, String username) {
        VideoJob job = jobRepository.findById(jobId)
                .orElseThrow(() -> new RuntimeException("Job not found: " + jobId));

        if (job.getStatus() == JobStatus.DRAFT || job.getStatus() == JobStatus.KEYWORD_PENDING) {
            throw new IllegalStateException("키워드 확정 전에는 스크립트를 확정할 수 없습니다. 현재: " + job.getStatus());
        }
        if (finalScript == null || finalScript.isBlank()) {
            throw new IllegalStateException("최종 스크립트가 비어있습니다.");
        }

        // 최종 스크립트 텍스트를 파싱하여 섹션 분리 (사용자 수정 사항 반영)
        List<Map<String, Object>> sections = new java.util.ArrayList<>();
        List<Map<String, Object>> verifiedFacts = List.of();
        
        try {
            // 기존 에셋에서 verified_facts만 복원
            java.util.Optional<Asset> prevAssetOpt = assetRepository.findTopByJobIdAndAssetTypeOrderByCreatedAtDesc(jobId, AssetType.SCRIPT);
            if (prevAssetOpt.isPresent()) {
                ScriptGenerateResponse prevDto = objectMapper.readValue(prevAssetOpt.get().getMetaJson(), ScriptGenerateResponse.class);
                if (prevDto.getVerifiedFacts() != null) {
                    verifiedFacts = prevDto.getVerifiedFacts();
                }
            }
        } catch (Exception e) {
            log.warn("이전 스크립트 에셋 메타데이터 파싱 실패: {}", e.getMessage());
        }

        if (inputSections != null && !inputSections.isEmpty()) {
            sections = inputSections;
        } else {
            try {
                String[] parts = finalScript.split("(?m)^##\\s*");
                if (parts.length <= 1) {
                    parts = finalScript.split("(?m)^\\s*\\n+");
                }
                for (String part : parts) {
                    part = part.trim();
                    if (part.isEmpty()) continue;
                    
                    int firstNewline = part.indexOf('\n');
                    String title;
                    String rawContent;
                    if (firstNewline != -1) {
                        title = part.substring(0, firstNewline).trim();
                        rawContent = part.substring(firstNewline + 1).trim();
                    } else {
                        title = "섹션";
                        rawContent = part;
                    }
                    
                    // [대사]와 [비주얼] 분리 파싱
                    String narration = "";
                    String prompt = "";
                    
                    int daesaIdx = rawContent.indexOf("[대사]");
                    int visualIdx = rawContent.indexOf("[비주얼]");
                    
                    if (daesaIdx != -1) {
                        if (visualIdx != -1 && visualIdx > daesaIdx) {
                            narration = rawContent.substring(daesaIdx + 4, visualIdx).trim();
                        } else {
                            narration = rawContent.substring(daesaIdx + 4).trim();
                        }
                    } else {
                        if (visualIdx != -1) {
                            narration = rawContent.substring(0, visualIdx).trim();
                        } else {
                            narration = rawContent;
                        }
                    }
                    
                    if (visualIdx != -1) {
                        prompt = rawContent.substring(visualIdx + 5).trim();
                    } else {
                        // [버그 수정] 여기 하드코딩된 4번째 캐릭터 설명 사본을 제거합니다.
                        // 파이썬 워커 쪽 script_worker._generate_visual_prompt()가 이미
                        // 씬 텍스트 기반의 정확한 프롬프트를 만들어주므로, 여기서는 그것에
                        // 위임하는 게 맞습니다. 스크립트 수정 → 재저장 경로에서만 이 분기가
                        // 타는데, 그때는 씬 텍스트만 넘겨주고 실제 프롬프트 생성은 이미지
                        // 재생성 시 FastAPI 쪽에서 다시 만들어집니다.
                        prompt = "";
                    }
                    
                    Map<String, Object> secMap = new java.util.HashMap<>();
                    secMap.put("title", title);
                    secMap.put("text", narration);
                    secMap.put("content", narration);
                    secMap.put("prompt", prompt);
                    secMap.put("char_count", narration.length());
                    
                    // section key 매핑
                    String sectionKey = "background";
                    if (title.contains("인트로") || title.toLowerCase().contains("intro")) {
                        sectionKey = "intro";
                    } else if (title.contains("배경") || title.toLowerCase().contains("background")) {
                        sectionKey = "background";
                    } else if (title.contains("데이터") || title.toLowerCase().contains("data")) {
                        sectionKey = "data";
                    } else if (title.contains("시나리오") || title.toLowerCase().contains("scenario")) {
                        sectionKey = "scenario";
                    } else if (title.contains("가이드") || title.toLowerCase().contains("action") || title.toLowerCase().contains("guide")) {
                        sectionKey = "action";
                    } else if (title.contains("결론") || title.toLowerCase().contains("conclusion")) {
                        sectionKey = "conclusion";
                    }
                    secMap.put("section", sectionKey);
                    
                    sections.add(secMap);
                }
            } catch (Exception parseEx) {
                log.warn("최종 스크립트 섹션 파싱 실패, 이전 에셋 복원 폴백: {}", parseEx.getMessage());
            }
        }

        if (sections.isEmpty()) {
            // 폴백: 이전 에셋에서 복원
            try {
                java.util.Optional<Asset> prevAssetOpt = assetRepository.findTopByJobIdAndAssetTypeOrderByCreatedAtDesc(jobId, AssetType.SCRIPT);
                if (prevAssetOpt.isPresent()) {
                    ScriptGenerateResponse prevDto = objectMapper.readValue(prevAssetOpt.get().getMetaJson(), ScriptGenerateResponse.class);
                    if (prevDto.getSections() != null) {
                        sections = prevDto.getSections();
                    }
                }
            } catch (Exception e) {
                log.warn("이전 스크립트 에셋 복원 실패: {}", e.getMessage());
            }
        }

        // 스크립트 UI 노출용 마크다운 형식 재구성 (작업자에게는 깨끗한 한국어 대사만 제공)
        String scriptToSave = finalScript;
        if (!sections.isEmpty() && (finalScript == null || !finalScript.contains("##"))) {
            StringBuilder sb = new StringBuilder();
            for (Map<String, Object> sec : sections) {
                sb.append("## ").append(sec.get("title")).append("\n");
                String content = sec.get("content") != null ? sec.get("content").toString() : (sec.get("text") != null ? sec.get("text").toString() : "");
                sb.append(content).append("\n\n");
            }
            scriptToSave = sb.toString().trim();
        }

        Asset finalAsset = Asset.builder()
                .jobId(jobId)
                .assetType(AssetType.SCRIPT)
                .metaJson(safeJson(Map.of(
                        "script", scriptToSave,
                        "final", true,
                        "char_count", scriptToSave.length(),
                        "sections", sections,
                        "verified_facts", verifiedFacts
                )))
                .build();
        assetRepository.save(finalAsset);

        if (job.getStatus() == JobStatus.SCRIPT_PENDING) {
            gateService.approve(jobId, GateName.SCRIPT, username, "스크립트 확정");
        } else {
            log.info("스크립트 수정/재확정 완료 (상태 유지: {}): jobId={}", job.getStatus(), jobId);
        }
        log.info("스크립트 확정: jobId={}, length={}자, sections={}개", jobId, scriptToSave.length(), sections.size());
    }

    private String safeJson(Object obj) {
        try {
            return objectMapper.writeValueAsString(obj);
        } catch (JsonProcessingException e) {
            return "{}";
        }
    }
}
