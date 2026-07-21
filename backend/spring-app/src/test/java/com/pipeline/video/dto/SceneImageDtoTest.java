package com.pipeline.video.dto;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import java.util.ArrayList;
import java.util.List;

class SceneImageDtoTest {

    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void preservesVerifiedGraphicsAndMotionAcrossAssetRoundTrip() throws Exception {
        String input = """
                {
                  "index": 0,
                  "image_path": "/tmp/scene.png",
                  "market_chart": {"verified": true, "latest": 6747.95},
                  "index_data": {"verified": true, "name": "코스피"},
                  "motion_type": "chart_shock",
                  "bubble_text": "검증 수치",
                  "future_overlay_contract": {"renderer": "v4", "required": true}
                }
                """;

        SceneImageDto scene = mapper.readValue(input, SceneImageDto.class);
        String stored = mapper.writeValueAsString(scene);
        var roundTripped = mapper.readTree(stored);

        assertTrue(roundTripped.path("market_chart").path("verified").asBoolean());
        assertTrue(roundTripped.path("index_data").path("verified").asBoolean());
        assertEquals("chart_shock", roundTripped.path("motion_type").asText());
        assertEquals("검증 수치", roundTripped.path("bubble_text").asText());
        assertEquals("v4", roundTripped.path("future_overlay_contract").path("renderer").asText());
        assertTrue(roundTripped.path("future_overlay_contract").path("required").asBoolean());
    }

    @Test
    void preservesJob134ShapeCountsAcrossEightyFourSceneRoundTrip() throws Exception {
        List<SceneImageDto> scenes = new ArrayList<>();
        for (int index = 0; index < 84; index++) {
            StringBuilder json = new StringBuilder("{\"index\":" + index);
            if (index < 5) json.append(",\"market_chart\":{\"verified\":true}");
            if (index >= 5 && index < 14) json.append(",\"index_data\":{\"verified\":true}");
            if (index < 24) json.append(",\"motion_type\":\"pointing_explain\"");
            json.append(",\"future_scene_field\":{\"source\":\"job134\"}}");
            scenes.add(mapper.readValue(json.toString(), SceneImageDto.class));
        }

        var stored = mapper.readTree(mapper.writeValueAsString(scenes));
        int charts = 0;
        int cards = 0;
        int motions = 0;
        int futureFields = 0;
        for (var scene : stored) {
            if (scene.path("market_chart").isObject()) charts++;
            if (scene.path("index_data").isObject()) cards++;
            if (scene.path("motion_type").isTextual() && !scene.path("motion_type").asText().isBlank()) motions++;
            if (scene.path("future_scene_field").path("source").asText().equals("job134")) futureFields++;
        }
        assertEquals(5, charts);
        assertEquals(9, cards);
        assertEquals(24, motions);
        assertEquals(84, futureFields);
    }
}
