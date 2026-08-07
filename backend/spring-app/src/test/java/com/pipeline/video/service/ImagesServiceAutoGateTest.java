package com.pipeline.video.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.pipeline.video.domain.Asset;
import com.pipeline.video.domain.AssetType;
import com.pipeline.video.domain.JobStatus;
import com.pipeline.video.domain.VideoJob;
import com.pipeline.video.dto.ImagesGenerateResponse;
import com.pipeline.video.repository.AssetRepository;
import com.pipeline.video.repository.VideoJobRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.List;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

/**
 * Stage 2-A: AUTO mode image review gate unit tests.
 *
 * Verifies:
 * 1. requires_manual_review=true + AUTO mode -> job.status == IMAGES_RETRY_REQUIRED, confirm() not called
 * 2. requires_manual_review=false + AUTO mode -> normal auto-confirm (no regression)
 * 3. confirm() gate: requires_manual_review=true + username != "AUTO" -> IllegalStateException
 * 4. confirm() gate: username="AUTO" -> passes (internal auto-confirm path)
 */
@ExtendWith(MockitoExtension.class)
class ImagesServiceAutoGateTest {

    @Mock VideoJobRepository jobRepository;
    @Mock AssetRepository assetRepository;
    @Mock AutonomyService autonomyService;
    @Mock GateService gateService;
    @Mock CharacterAssetResolver characterAssetResolver;
    @Mock FastApiClient fastApiClient;
    @Mock CostService costService;

    private ImagesService imagesService;
    private final ObjectMapper objectMapper = new ObjectMapper();

    @BeforeEach
    void setUp() {
        imagesService = spy(new ImagesService(
                jobRepository, assetRepository,
                null,
                characterAssetResolver, fastApiClient,
                gateService, autonomyService, costService
        ));
    }

    @Test
    void confirm_requiresManualReview_nonAutoUser_throws() throws Exception {
        VideoJob job = new VideoJob();
        job.setId(1L);
        job.setStatus(JobStatus.IMAGES_PENDING);

        ImagesGenerateResponse qc = new ImagesGenerateResponse();
        qc.setRequiresManualReview(true);
        qc.setReviewReasons(List.of("VISUAL_MIX_PREFLIGHT_FAILURE:article_evidence<5%"));

        Asset asset = new Asset();
        asset.setMetaJson(objectMapper.writeValueAsString(qc));

        when(jobRepository.findById(1L)).thenReturn(Optional.of(job));
        when(assetRepository.findTopByJobIdAndAssetTypeOrderByCreatedAtDesc(1L, AssetType.IMAGE_QC_REPORT))
                .thenReturn(Optional.of(asset));

        assertThatThrownBy(() -> imagesService.confirm(1L, "SONG"))
                .isInstanceOf(IllegalStateException.class);

        verify(gateService, never()).approve(any(), any(), any(), any());
    }

    @Test
    void confirm_requiresManualReview_autoUsername_passes() throws Exception {
        VideoJob job = new VideoJob();
        job.setId(1L);
        job.setStatus(JobStatus.IMAGES_PENDING);

        ImagesGenerateResponse qc = new ImagesGenerateResponse();
        qc.setRequiresManualReview(true);
        qc.setReviewReasons(List.of("VISUAL_MIX_PREFLIGHT_FAILURE"));

        Asset asset = new Asset();
        asset.setMetaJson(objectMapper.writeValueAsString(qc));

        when(jobRepository.findById(1L)).thenReturn(Optional.of(job));
        when(assetRepository.findTopByJobIdAndAssetTypeOrderByCreatedAtDesc(1L, AssetType.IMAGE_QC_REPORT))
                .thenReturn(Optional.of(asset));

        imagesService.confirm(1L, "AUTO");

        verify(gateService).approve(eq(1L), any(), eq("AUTO"), any());
    }

    @Test
    void confirm_noManualReview_anyUser_passes() throws Exception {
        VideoJob job = new VideoJob();
        job.setId(1L);
        job.setStatus(JobStatus.IMAGES_PENDING);

        ImagesGenerateResponse qc = new ImagesGenerateResponse();
        qc.setRequiresManualReview(false);

        Asset asset = new Asset();
        asset.setMetaJson(objectMapper.writeValueAsString(qc));

        when(jobRepository.findById(1L)).thenReturn(Optional.of(job));
        when(assetRepository.findTopByJobIdAndAssetTypeOrderByCreatedAtDesc(1L, AssetType.IMAGE_QC_REPORT))
                .thenReturn(Optional.of(asset));

        imagesService.confirm(1L, "SONG");

        verify(gateService).approve(eq(1L), any(), eq("SONG"), any());
    }

    @Test
    void autoMode_requiresManualReview_setsRetryRequired_and_doesNotConfirm() throws Exception {
        VideoJob job = new VideoJob();
        job.setId(1L);
        job.setStatus(JobStatus.IMAGES_PENDING);

        Asset ttsAsset = new Asset();
        ttsAsset.setMetaJson("{}");
        Asset scriptAsset = new Asset();
        scriptAsset.setMetaJson("{}");

        ImagesGenerateResponse result = new ImagesGenerateResponse();
        result.setRequiresManualReview(true);
        result.setReviewReasons(List.of("VISUAL_MIX_PREFLIGHT_FAILURE"));

        CharacterAssetResolver.ResolvedCharacter mockChar = new CharacterAssetResolver.ResolvedCharacter(
                "profile-1", "/path/to/img", "style", "/path/to/poses", null, null, null, 1.0f, "0123456789abcdef"
        );

        when(jobRepository.findById(1L)).thenReturn(Optional.of(job));
        when(assetRepository.findTopByJobIdAndAssetTypeOrderByCreatedAtDesc(1L, AssetType.TTS_AUDIO)).thenReturn(Optional.of(ttsAsset));
        when(assetRepository.findTopByJobIdAndAssetTypeOrderByCreatedAtDesc(1L, AssetType.SCRIPT)).thenReturn(Optional.of(scriptAsset));
        when(characterAssetResolver.resolve(job)).thenReturn(mockChar);
        when(fastApiClient.generateImages(any(), any(), any(), any(), any(), any(), any(), any(), any(), any(), any(), any())).thenReturn(result);
        when(autonomyService.isAuto(job)).thenReturn(true);

        imagesService.generate(1L, "AUTO");

        assertThat(job.getStatus()).isEqualTo(JobStatus.IMAGES_RETRY_REQUIRED);
        verify(jobRepository).save(job);
        verify(imagesService, never()).confirm(eq(1L), any());
    }

    @Test
    void autoMode_noManualReview_callsConfirmAuto() throws Exception {
        VideoJob job = new VideoJob();
        job.setId(1L);
        job.setStatus(JobStatus.IMAGES_PENDING);

        Asset ttsAsset = new Asset();
        ttsAsset.setMetaJson("{}");
        Asset scriptAsset = new Asset();
        scriptAsset.setMetaJson("{}");

        ImagesGenerateResponse result = new ImagesGenerateResponse();
        result.setRequiresManualReview(false);

        CharacterAssetResolver.ResolvedCharacter mockChar = new CharacterAssetResolver.ResolvedCharacter(
                "profile-1", "/path/to/img", "style", "/path/to/poses", null, null, null, 1.0f, "0123456789abcdef"
        );

        when(jobRepository.findById(1L)).thenReturn(Optional.of(job));
        when(assetRepository.findTopByJobIdAndAssetTypeOrderByCreatedAtDesc(1L, AssetType.TTS_AUDIO)).thenReturn(Optional.of(ttsAsset));
        when(assetRepository.findTopByJobIdAndAssetTypeOrderByCreatedAtDesc(1L, AssetType.SCRIPT)).thenReturn(Optional.of(scriptAsset));
        when(characterAssetResolver.resolve(job)).thenReturn(mockChar);
        when(fastApiClient.generateImages(any(), any(), any(), any(), any(), any(), any(), any(), any(), any(), any(), any())).thenReturn(result);
        when(autonomyService.isAuto(job)).thenReturn(true);
        doNothing().when(imagesService).confirm(eq(1L), eq("AUTO"));

        imagesService.generate(1L, "AUTO");

        verify(imagesService).confirm(eq(1L), eq("AUTO"));
    }
}