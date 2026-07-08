package com.pipeline.video.controller;

import com.pipeline.video.domain.ChannelProfile;
import com.pipeline.video.repository.ChannelProfileRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequestMapping("/api/channels")
@RequiredArgsConstructor
public class ChannelProfileController {

    private final ChannelProfileRepository channelProfileRepository;

    @GetMapping
    public ResponseEntity<List<ChannelProfile>> getAll() {
        return ResponseEntity.ok(channelProfileRepository.findAll());
    }

    @GetMapping("/{id}")
    public ResponseEntity<ChannelProfile> getOne(@PathVariable String id) {
        return channelProfileRepository.findById(id)
                .map(ResponseEntity::ok)
                .orElse(ResponseEntity.notFound().build());
    }

    @PostMapping
    public ResponseEntity<ChannelProfile> save(@RequestBody ChannelProfile profile) {
        if (profile.getChannelId() == null || profile.getChannelId().isBlank()) {
            return ResponseEntity.badRequest().build();
        }
        return ResponseEntity.ok(channelProfileRepository.save(profile));
    }

    @DeleteMapping("/{id}")
    public ResponseEntity<Void> delete(@PathVariable String id) {
        if (!channelProfileRepository.existsById(id)) {
            return ResponseEntity.notFound().build();
        }
        channelProfileRepository.deleteById(id);
        return ResponseEntity.ok().build();
    }
}
