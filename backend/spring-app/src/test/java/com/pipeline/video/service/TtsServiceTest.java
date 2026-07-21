package com.pipeline.video.service;

import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

class TtsServiceTest {

    @Test
    void providerCopyUsesNarrationWithoutMarkdownSceneHeadings() {
        Map<String, Object> meta = Map.of(
                "script", "## 씬 1: 급락\n첫 문장입니다.\n\n## 씬 2: 반등\n둘째 문장입니다.",
                "sections", List.of(
                        Map.of("title", "씬 1: 급락", "content", "첫 문장입니다."),
                        Map.of("title", "씬 2: 반등", "content", "둘째 문장입니다.")
                )
        );

        String providerCopy = TtsService.narrationFromMeta(meta);

        assertThat(providerCopy).isEqualTo("첫 문장입니다.\n\n둘째 문장입니다.");
        assertThat(providerCopy).doesNotContain("##", "씬 1", "급락");
    }
}
