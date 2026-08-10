package com.pipeline.video.controller;

import com.pipeline.video.config.PricingConfig;
import lombok.Data;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.math.BigDecimal;
import java.util.HashMap;
import java.util.Map;

@Slf4j
@RestController
@RequestMapping("/api/admin/pricing-policy")
public class AdminPolicyController {

    @GetMapping
    public ResponseEntity<Map<String, Object>> getPricingPolicy() {
        Map<String, Object> policy = new HashMap<>();
        policy.put("shortformBudgetCap", PricingConfig.SHORTFORM_BUDGET_CAP_KRW);
        policy.put("longformBudgetCap", PricingConfig.LONGFORM_BUDGET_CAP_KRW);
        policy.put("longformThresholdMinutes", PricingConfig.LONGFORM_THRESHOLD_MINUTES);
        policy.put("usdToKrwRate", PricingConfig.USD_TO_KRW_BUDGET_RATE);
        policy.put("policyVersion", PricingConfig.POLICY_VERSION);
        return ResponseEntity.ok(policy);
    }

    @PostMapping
    public ResponseEntity<Map<String, Object>> updatePricingPolicy(@RequestBody UpdatePolicyRequest request) {
        log.info("관리자 예산 정책 업데이트 요청: shortformCap={}, longformCap={}",
                request.getShortformBudgetCap(), request.getLongformBudgetCap());

        PricingConfig.updatePolicy(request.getShortformBudgetCap(), request.getLongformBudgetCap());

        Map<String, Object> response = new HashMap<>();
        response.put("message", "영상 길이별 예산 정책이 성공적으로 업데이트되었습니다.");
        response.put("shortformBudgetCap", PricingConfig.SHORTFORM_BUDGET_CAP_KRW);
        response.put("longformBudgetCap", PricingConfig.LONGFORM_BUDGET_CAP_KRW);
        return ResponseEntity.ok(response);
    }

    @Data
    public static class UpdatePolicyRequest {
        private BigDecimal shortformBudgetCap;
        private BigDecimal longformBudgetCap;
    }
}
