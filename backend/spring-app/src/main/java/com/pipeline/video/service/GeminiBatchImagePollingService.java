package com.pipeline.video.service;

import com.pipeline.video.domain.Asset;
import com.pipeline.video.domain.AssetType;
import com.pipeline.video.dto.ImagesGenerateResponse;
import com.pipeline.video.repository.AssetRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;

/** Completes durable Gemini Pro image batches without holding an HTTP request open. */
@Service
@Slf4j
@RequiredArgsConstructor
public class GeminiBatchImagePollingService {
    private final AssetRepository assetRepository;
    private final FastApiClient fastApiClient;
    private final ImagesService imagesService;

    @Scheduled(fixedDelayString = "${gemini.pro-batch.poll-ms:30000}")
    public void pollPendingBatches() {
        for (Asset batchAsset : assetRepository.findByAssetType(AssetType.IMAGE_BATCH)) {
            try {
                ImagesGenerateResponse result = fastApiClient.getImageBatchStatus(batchAsset.getJobId());
                if ("BATCH_COMPLETE".equals(result.getStatus())) {
                    imagesService.completeBatch(batchAsset.getJobId(), batchAsset.getId(), result);
                } else if ("BATCH_FAILED".equals(result.getStatus())) {
                    log.error("Gemini Pro Batch failed: jobId={}, batch={}, error={}",
                            batchAsset.getJobId(), result.getBatchJobName(), result.getError());
                }
            } catch (Exception e) {
                // Keep the persisted manifest and retry on the next interval.
                log.warn("Gemini Pro Batch polling deferred: jobId={}, error={}",
                        batchAsset.getJobId(), e.getMessage());
            }
        }
    }
}
