package com.pipeline.video.service;

import com.pipeline.video.domain.ChannelProfile;
import com.pipeline.video.domain.VideoJob;
import com.pipeline.video.repository.ChannelProfileRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;

/**
 * Resolves one immutable character identity for every job-facing renderer.
 *
 * Image generation and thumbnail generation used to query profiles differently:
 * the former honored characterOverride, while the latter silently used only the
 * channel profile.  Centralising this policy prevents character mixing.
 */
@Service
@RequiredArgsConstructor
public class CharacterAssetResolver {

    private final ChannelProfileRepository channelProfileRepository;

    public ResolvedCharacter resolve(VideoJob job) {
        String profileId = nonBlank(job.getCharacterOverride()) ? job.getCharacterOverride() : job.getChannelId();
        ChannelProfile profile = profileId == null ? null : channelProfileRepository.findById(profileId).orElse(null);
        if (profile == null) {
            return new ResolvedCharacter(null, null, null, null, null, null, null, 1.0f, identityHash("none"));
        }
        String hashInput = String.join("|",
                safe(profile.getChannelId()), safe(profile.getCharacterKey()),
                safe(profile.getCharacterImagePath()), safe(profile.getCharacterStylePrompt()),
                safe(profile.getCharacterPosesDir()), safe(profile.getLoraModelId()),
                safe(profile.getLoraTriggerWord()), safe(profile.getWatermarkPath()),
                String.valueOf(profile.getLoraScale()));
        return new ResolvedCharacter(
                profile.getChannelId(), profile.getCharacterImagePath(), profile.getCharacterStylePrompt(),
                profile.getCharacterPosesDir(), profile.getLoraModelId(), profile.getLoraTriggerWord(),
                profile.getWatermarkPath(),
                profile.getLoraScale() == null ? 1.0f : profile.getLoraScale(), identityHash(hashInput)
        );
    }

    private static boolean nonBlank(String value) {
        return value != null && !value.isBlank();
    }

    private static String safe(String value) {
        return value == null ? "" : value;
    }

    private static String identityHash(String value) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8));
            StringBuilder result = new StringBuilder();
            for (byte part : digest) result.append(String.format("%02x", part));
            return result.toString();
        } catch (Exception exception) {
            throw new IllegalStateException("캐릭터 정체성 해시 생성 실패", exception);
        }
    }

    public record ResolvedCharacter(
            String profileId,
            String imagePath,
            String stylePrompt,
            String posesDir,
            String loraModelId,
            String loraTriggerWord,
            String watermarkPath,
            Float loraScale,
            String identityHash
    ) { }
}
