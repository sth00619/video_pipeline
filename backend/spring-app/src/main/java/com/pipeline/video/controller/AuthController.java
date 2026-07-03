package com.pipeline.video.controller;

import com.pipeline.video.dto.LoginRequest;
import com.pipeline.video.dto.LoginResponse;
import com.pipeline.video.dto.RegisterRequest;
import com.pipeline.video.dto.UserResponse;
import com.pipeline.video.service.AuthService;
import com.pipeline.video.service.UserService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/auth")
@RequiredArgsConstructor
public class AuthController {

    private final AuthService authService;
    private final UserService userService;

    @PostMapping("/login")
    public ResponseEntity<LoginResponse> login(@RequestBody LoginRequest request) {
        return ResponseEntity.ok(authService.login(request));
    }

    @PostMapping("/register")
    public ResponseEntity<UserResponse> register(@RequestBody RegisterRequest request) {
        return ResponseEntity.ok(userService.register(request));
    }

    @GetMapping("/me")
    public ResponseEntity<UserResponse> me(java.security.Principal principal) {
        return ResponseEntity.ok(userService.getByUsername(principal.getName()));
    }
}
