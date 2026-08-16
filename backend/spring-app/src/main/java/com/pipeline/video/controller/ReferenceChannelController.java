package com.pipeline.video.controller;

import com.pipeline.video.domain.ReferenceChannel;
import com.pipeline.video.dto.ReferenceChannelConfirmItem;
import com.pipeline.video.dto.ReferenceChannelCreateRequest;
import com.pipeline.video.dto.ReferenceChannelUpdateRequest;
import com.pipeline.video.service.ReferenceChannelService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/admin/reference-channels")
@RequiredArgsConstructor
@PreAuthorize("hasRole('ADMIN')")
public class ReferenceChannelController {

    private final ReferenceChannelService service;

    @GetMapping
    public List<ReferenceChannel> list(
            @RequestParam(defaultValue = "false") boolean activeOnly
    ) {
        return service.list(activeOnly);
    }

    @PostMapping
    public ResponseEntity<ReferenceChannel> create(
            @Valid @RequestBody ReferenceChannelCreateRequest request,
            Authentication authentication
    ) {
        return ResponseEntity.ok(service.create(request, authentication.getName()));
    }

    @PutMapping("/{id}")
    public ReferenceChannel update(
            @PathVariable long id,
            @Valid @RequestBody ReferenceChannelUpdateRequest request
    ) {
        return service.update(id, request);
    }

    @DeleteMapping("/{id}")
    public ReferenceChannel delete(@PathVariable long id) {
        return service.softDelete(id);
    }

    @PostMapping("/bulk-preview")
    public List<ReferenceChannelService.BulkPreviewItem> preview(
            @RequestBody List<String> channelRefs
    ) {
        return service.preview(channelRefs);
    }

    @PostMapping("/bulk-confirm")
    public ReferenceChannelService.BulkConfirmResult confirm(
            @Valid @RequestBody List<@Valid ReferenceChannelConfirmItem> items,
            Authentication authentication
    ) {
        return service.confirm(items, authentication.getName());
    }

    @PostMapping("/{id}/revalidate")
    public ReferenceChannel revalidate(@PathVariable long id) {
        return service.revalidate(id);
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<Map<String, String>> validationError(MethodArgumentNotValidException exception) {
        String message = exception.getBindingResult().getFieldErrors().stream()
                .findFirst()
                .map(error -> error.getDefaultMessage() == null ? "요청 값을 확인해 주세요." : error.getDefaultMessage())
                .orElse("요청 값을 확인해 주세요.");
        return ResponseEntity.badRequest().body(Map.of(
                "error", "INVALID_REQUEST",
                "message", message
        ));
    }

    @ExceptionHandler(AccessDeniedException.class)
    public ResponseEntity<Map<String, String>> accessDenied() {
        return ResponseEntity.status(HttpStatus.FORBIDDEN).body(Map.of(
                "error", "FORBIDDEN",
                "message", "관리자 권한이 필요합니다."
        ));
    }
}
