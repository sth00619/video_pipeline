package com.pipeline.video.service;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.pipeline.video.domain.PersonAsset;
import com.pipeline.video.domain.PersonPhoto;
import com.pipeline.video.domain.PhotoLicenseType;
import com.pipeline.video.domain.RightsReviewStatus;
import com.pipeline.video.repository.PersonAssetRepository;
import com.pipeline.video.repository.PersonPhotoRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

/**
 * Resolves approved real-person photos for automatic thumbnail recommendations.
 *
 * <p>The script generator is not required to emit a {@code persons} array. An
 * explicit brief request still wins, but registered Korean/English names and
 * aliases are also matched against the generated title, keyword and script.
 * Only locally registered, rights-reviewed photos can leave this boundary.</p>
 */
@Service
@RequiredArgsConstructor
@Slf4j
public class ThumbnailPersonResolver {

    private static final Set<PhotoLicenseType> ALLOWED_LICENSES = Set.of(
            PhotoLicenseType.PRESS_KIT,
            PhotoLicenseType.KOGL_TYPE1,
            PhotoLicenseType.CC_BY,
            PhotoLicenseType.CC_BY_SA,
            PhotoLicenseType.OWNED,
            PhotoLicenseType.STOCK_LICENSED,
            PhotoLicenseType.AGENCY_LICENSED
    );

    private final PersonAssetRepository personAssetRepository;
    private final PersonPhotoRepository personPhotoRepository;
    private final ObjectMapper objectMapper;

    public List<Map<String, Object>> resolve(
            Map<String, Object> thumbnailBrief,
            String title,
            String keyword,
            String scriptText
    ) {
        List<PersonAsset> assets = personAssetRepository.findAll();
        if (assets.isEmpty()) return List.of();

        List<ExplicitRequest> explicitRequests = explicitRequests(thumbnailBrief);
        String context = normalize(String.join("\n",
                valueOrEmpty(title),
                valueOrEmpty(keyword),
                valueOrEmpty(scriptText)
        ));

        Map<String, PersonMatch> matches = new LinkedHashMap<>();
        for (ExplicitRequest request : explicitRequests) {
            PersonAsset asset = findExplicitAsset(assets, request.name());
            if (asset != null) {
                matches.put(asset.getPersonId(), new PersonMatch(
                        asset, request.mood(), request.name(), "thumbnail_brief", 100_000
                ));
            }
        }

        for (PersonAsset asset : assets) {
            PersonMatch inferred = inferFromContext(asset, context);
            if (inferred == null) continue;
            matches.merge(asset.getPersonId(), inferred,
                    (existing, candidate) -> existing.score() >= candidate.score() ? existing : candidate);
        }

        return matches.values().stream()
                .sorted(Comparator.comparingInt(PersonMatch::score).reversed()
                        .thenComparing(match -> match.asset().getPersonId()))
                .map(this::resolvePhoto)
                .filter(map -> !map.isEmpty())
                .limit(2)
                .toList();
    }

    private PersonMatch inferFromContext(PersonAsset asset, String context) {
        String bestTerm = "";
        int bestScore = 0;
        for (String term : aliases(asset)) {
            String normalized = normalize(term);
            if (normalized.length() < 2 || !context.contains(normalized)) continue;
            int occurrences = countOccurrences(context, normalized);
            int score = normalized.length() * 100 + occurrences * 10;
            if (score > bestScore) {
                bestTerm = term;
                bestScore = score;
            }
        }
        if (bestScore == 0) return null;
        return new PersonMatch(asset, "", bestTerm, "script_context", bestScore);
    }

    private Map<String, Object> resolvePhoto(PersonMatch match) {
        List<PersonPhoto> eligible = personPhotoRepository
                .findByPersonIdAndApprovedTrueOrderByCreatedAtDesc(match.asset().getPersonId())
                .stream()
                .filter(this::hasUsageRights)
                .toList();
        if (eligible.isEmpty()) {
            log.info("자동 썸네일 인물은 감지했지만 승인 사진이 없습니다: personId={}, match={}",
                    match.asset().getPersonId(), match.matchTerm());
            return Map.of();
        }

        PersonPhoto photo = eligible.stream()
                .filter(candidate -> match.mood().isBlank()
                        || match.mood().equalsIgnoreCase(valueOrEmpty(candidate.getEmotionTag())))
                .findFirst()
                .orElse(eligible.get(0));

        Map<String, Object> mapped = new HashMap<>();
        mapped.put("person_id", match.asset().getPersonId());
        mapped.put("person_name", match.asset().getNameKo());
        mapped.put("match_term", match.matchTerm());
        mapped.put("match_source", match.matchSource());
        mapped.put("photo_id", photo.getPhotoId());
        mapped.put("original_path", photo.getOriginalPath());
        mapped.put("cutout_path", photo.getCutoutPath());
        mapped.put("license_type", photo.getLicenseType().name());
        mapped.put("license_ref", photo.getLicenseRef());
        mapped.put("credit_text", photo.getCreditText());
        mapped.put("emotion_tag", photo.getEmotionTag());
        mapped.put("pose", photo.getPose());
        mapped.put("approved", photo.isApproved());
        mapped.put("rights_review_status", photo.getRightsReviewStatus().name());
        mapped.put("cutout_model", photo.getCutoutModel());
        return mapped;
    }

    private boolean hasUsageRights(PersonPhoto photo) {
        if (!photo.isApproved() || photo.getLicenseType() == null || photo.getRightsReviewStatus() == null) {
            return false;
        }
        if (!ALLOWED_LICENSES.contains(photo.getLicenseType())) return false;
        if (photo.getRightsReviewStatus() != RightsReviewStatus.APPROVED
                && photo.getRightsReviewStatus() != RightsReviewStatus.NOT_REQUIRED) {
            return false;
        }
        return photo.getOriginalPath() != null && !photo.getOriginalPath().isBlank()
                || photo.getCutoutPath() != null && !photo.getCutoutPath().isBlank();
    }

    private PersonAsset findExplicitAsset(List<PersonAsset> assets, String requestedName) {
        String normalizedRequest = normalize(requestedName);
        return assets.stream()
                .filter(asset -> aliases(asset).stream()
                        .map(this::normalize)
                        .anyMatch(normalizedRequest::equals))
                .findFirst()
                .orElseGet(() -> assets.stream()
                        .filter(asset -> normalize(asset.getPersonId()).equals(normalizedRequest))
                        .findFirst()
                        .orElse(null));
    }

    @SuppressWarnings("unchecked")
    private List<ExplicitRequest> explicitRequests(Map<String, Object> brief) {
        List<ExplicitRequest> requests = new ArrayList<>();
        Object rawPeople = brief == null ? null : brief.get("persons");
        if (rawPeople instanceof List<?> people) {
            for (Object value : people) {
                if (value instanceof String name && !name.isBlank()) {
                    requests.add(new ExplicitRequest(name.trim(), ""));
                } else if (value instanceof Map<?, ?> person) {
                    String name = valueOrEmpty(person.get("name")).trim();
                    String mood = valueOrEmpty(person.get("mood")).trim();
                    if (!name.isBlank()) requests.add(new ExplicitRequest(name, mood));
                }
            }
        }
        Object rawPrimary = brief == null ? null : brief.get("primary_subject");
        if (rawPrimary instanceof Map<?, ?> primary
                && "person".equalsIgnoreCase(valueOrEmpty(primary.get("kind")))) {
            String assetId = valueOrEmpty(primary.get("asset_id")).trim();
            if (!assetId.isBlank()) requests.add(new ExplicitRequest(assetId, ""));
        }
        return requests;
    }

    private List<String> aliases(PersonAsset asset) {
        LinkedHashSet<String> aliases = new LinkedHashSet<>();
        addAlias(aliases, asset.getNameKo());
        addAlias(aliases, asset.getNameEn());
        if (asset.getAliasesJson() != null && !asset.getAliasesJson().isBlank()) {
            try {
                List<String> parsed = objectMapper.readValue(
                        asset.getAliasesJson(), new TypeReference<List<String>>() { }
                );
                parsed.forEach(value -> addAlias(aliases, value));
            } catch (Exception exception) {
                log.warn("인물 별칭 JSON을 읽지 못했습니다: personId={}, error={}",
                        asset.getPersonId(), exception.getMessage());
            }
        }
        return new ArrayList<>(aliases);
    }

    private void addAlias(Set<String> aliases, String value) {
        if (value != null && !value.isBlank()) aliases.add(value.trim());
    }

    private String normalize(String value) {
        return valueOrEmpty(value)
                .toLowerCase(Locale.ROOT)
                .replaceAll("[\\s·._'\"()\\[\\]{}-]+", "");
    }

    private int countOccurrences(String text, String term) {
        int count = 0;
        int offset = 0;
        while ((offset = text.indexOf(term, offset)) >= 0) {
            count++;
            offset += term.length();
        }
        return count;
    }

    private String valueOrEmpty(Object value) {
        return value == null ? "" : String.valueOf(value);
    }

    private record ExplicitRequest(String name, String mood) { }
    private record PersonMatch(
            PersonAsset asset,
            String mood,
            String matchTerm,
            String matchSource,
            int score
    ) { }
}
