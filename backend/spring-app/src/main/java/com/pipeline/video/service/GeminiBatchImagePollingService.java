package com.pipeline.video.service;

import com.pipeline.video.domain.Asset;
import com.pipeline.video.domain.AssetType;
import com.pipeline.video.dto.ImagesGenerateResponse;
import com.pipeline.video.repository.AssetRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/** Completes durable Gemini Pro image batches without holding an HTTP request open. */
@Service
@Slf4j
@RequiredArgsConstructor
public class GeminiBatchImagePollingService {
    private final AssetRepository assetRepository;
    private final FastApiClient fastApiClient;
    private final ImagesService imagesService;
    private final Map<Long, Integer> consecutivePollingErrors = new ConcurrentHashMap<>();

    @Scheduled(fixedDelayString = "${gemini.pro-batch.poll-ms:30000}")
    public void pollPendingBatches() {
        for (Asset batchAsset : assetRepository.findByAssetTypeAndMetaJsonContaining(AssetType.IMAGE_BATCH, "BATCH_PENDING")) {
            try {
                ImagesGenerateResponse result = fastApiClient.getImageBatchStatus(batchAsset.getJobId());
                if ("BATCH_COMPLETE".equals(result.getStatus())) {
                    imagesService.completeBatch(batchAsset.getJobId(), batchAsset.getId(), result);
                    consecutivePollingErrors.remove(batchAsset.getId());
                } else if ("BATCH_FAILED".equals(result.getStatus())) {
                    log.error("Gemini Pro Batch failed: jobId={}, batch={}, error={}",
                            batchAsset.getJobId(), result.getBatchJobName(), result.getError());
                    imagesService.failBatch(batchAsset.getJobId(), batchAsset.getId(), result.getError());
                    consecutivePollingErrors.remove(batchAsset.getId());
                }
            } catch (Exception e) {
                int attempts = consecutivePollingErrors.merge(batchAsset.getId(), 1, Integer::sum);
                if (attempts >= 20) {
                    imagesService.failBatch(batchAsset.getJobId(), batchAsset.getId(), "POLL_STALLED after 20 polling errors: " + e.getMessage());
                    consecutivePollingErrors.remove(batchAsset.getId());
                    log.error("Gemini Pro Batch polling stopped after repeated failures: jobId={}", batchAsset.getJobId());
                } else {
                    log.warn("Gemini Pro Batch polling deferred: jobId={}, attempt={}, error={}",
                            batchAsset.getJobId(), attempts, e.getMessage());
                }
            }
        }
    }
}
