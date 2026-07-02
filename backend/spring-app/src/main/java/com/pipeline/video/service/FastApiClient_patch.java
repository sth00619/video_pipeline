// FastApiClient.java의 postJson() 메서드에서
// 아래 라인을 수정:

// 기존:
// conn.setRequestProperty("Content-Type", "application/json");

// 변경:
// conn.setRequestProperty("Content-Type", "application/json; charset=UTF-8");

// 그리고 jsonBody 인코딩도 명시:
// byte[] bodyBytes = jsonBody.getBytes(java.nio.charset.StandardCharsets.UTF_8);
// os.write(bodyBytes);
// (기존 코드에도 StandardCharsets.UTF_8이 이미 있으면 확인만)
