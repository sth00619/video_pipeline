package com.pipeline.video.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.pipeline.video.domain.PersonAsset;
import com.pipeline.video.domain.PersonPhoto;
import com.pipeline.video.domain.PhotoLicenseType;
import com.pipeline.video.domain.RightsReviewStatus;
import com.pipeline.video.repository.PersonAssetRepository;
import com.pipeline.video.repository.PersonPhotoRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class ThumbnailPersonResolverTest {

    @Mock
    private PersonAssetRepository personAssetRepository;
    @Mock
    private PersonPhotoRepository personPhotoRepository;

    private ThumbnailPersonResolver resolver;

    @BeforeEach
    void setUp() {
        resolver = new ThumbnailPersonResolver(
                personAssetRepository,
                personPhotoRepository,
                new ObjectMapper()
        );
    }

    @Test
    void findsApprovedPhotoFromKoreanAliasInScriptWithoutPersonsArray() {
        PersonAsset asset = PersonAsset.builder()
                .personId("jensen-huang")
                .nameKo("젠슨 황")
                .nameEn("Jensen Huang")
                .aliasesJson("[\"황 CEO\", \"엔비디아 CEO\"]")
                .build();
        PersonPhoto photo = approvedPhoto("jensen-press", "jensen-huang", PhotoLicenseType.PRESS_KIT);
        when(personAssetRepository.findAll()).thenReturn(List.of(asset));
        when(personPhotoRepository.findByPersonIdAndApprovedTrueOrderByCreatedAtDesc("jensen-huang"))
                .thenReturn(List.of(photo));

        List<Map<String, Object>> result = resolver.resolve(
                Map.of(),
                "엔비디아 실적 발표",
                "반도체",
                "엔비디아 CEO가 발표한 다음 전략을 살펴봅니다."
        );

        assertThat(result).hasSize(1);
        assertThat(result.get(0))
                .containsEntry("person_id", "jensen-huang")
                .containsEntry("person_name", "젠슨 황")
                .containsEntry("match_term", "엔비디아 CEO")
                .containsEntry("match_source", "script_context")
                .containsEntry("photo_id", "jensen-press");
    }

    @Test
    void explicitBriefWinsAndUnlicensedPhotoNeverReachesRenderer() {
        PersonAsset asset = PersonAsset.builder()
                .personId("sample-person")
                .nameKo("샘플 인물")
                .nameEn("Sample Person")
                .aliasesJson("[]")
                .build();
        PersonPhoto unknown = approvedPhoto("unknown-photo", "sample-person", PhotoLicenseType.UNKNOWN);
        when(personAssetRepository.findAll()).thenReturn(List.of(asset));
        when(personPhotoRepository.findByPersonIdAndApprovedTrueOrderByCreatedAtDesc("sample-person"))
                .thenReturn(List.of(unknown));

        List<Map<String, Object>> result = resolver.resolve(
                Map.of("persons", List.of(Map.of("name", "샘플 인물", "mood", "serious"))),
                "시장 분석",
                "증시",
                ""
        );

        assertThat(result).isEmpty();
    }

    private PersonPhoto approvedPhoto(String photoId, String personId, PhotoLicenseType licenseType) {
        return PersonPhoto.builder()
                .photoId(photoId)
                .personId(personId)
                .originalPath("/app/data/people/" + photoId + ".png")
                .cutoutPath("/app/data/people/" + photoId + ".cutout.png")
                .licenseType(licenseType)
                .approved(true)
                .rightsReviewStatus(RightsReviewStatus.APPROVED)
                .emotionTag("serious")
                .build();
    }
}
