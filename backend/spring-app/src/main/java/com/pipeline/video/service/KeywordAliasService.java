package com.pipeline.video.service;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Service;

import java.io.InputStream;
import java.util.*;

/** Uses the same backend/shared/keyword_aliases.json as the FastAPI worker. */
@Service
public class KeywordAliasService {
    private final Map<String, List<String>> aliases;

    public KeywordAliasService(ObjectMapper objectMapper) {
        try (InputStream stream = new ClassPathResource("keyword_aliases.json").getInputStream()) {
            Map<String, Object> root = objectMapper.readValue(stream, new TypeReference<>() {});
            Map<String, List<String>> loaded = (Map<String, List<String>>) root.getOrDefault("aliases", Map.of());
            this.aliases = new LinkedHashMap<>();
            loaded.forEach((key, value) -> aliases.put(compact(key), value));
        } catch (Exception exception) {
            throw new IllegalStateException("keyword_aliases.json could not be loaded", exception);
        }
    }

    public Set<String> terms(String text) {
        String compactText = compact(text);
        Set<String> result = new LinkedHashSet<>();
        aliases.forEach((alias, canonical) -> { if (compactText.contains(alias)) result.addAll(canonical); });
        java.util.regex.Matcher matcher = java.util.regex.Pattern.compile("([1-4])\\s*(?:분기|[Qq])").matcher(text == null ? "" : text);
        while (matcher.find()) result.add("Q" + matcher.group(1));
        return result;
    }

    private static String compact(String value) {
        return value == null ? "" : value.replaceAll("\\s+", "").toLowerCase(Locale.ROOT);
    }
}
