package com.pipeline.video.controller;

import com.pipeline.video.dto.LoginRequest;
import com.pipeline.video.dto.LoginResponse;
import com.pipeline.video.service.AuthService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/auth")
@RequiredArgsConstructor
public class AuthController {

    private final AuthService authService;

    @PostMapping("/login")
    public ResponseEntity<LoginResponse> login(@RequestBody LoginRequest request) {
        return ResponseEntity.ok(authService.login(request));
    }

    @GetMapping("/me")
    public ResponseEntity<String> me(java.security.Principal principal) {
        return ResponseEntity.ok(principal.getName());
    }
}
