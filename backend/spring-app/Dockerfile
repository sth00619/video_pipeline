# Stage 1: Build
FROM gradle:8.7-jdk17 AS builder
WORKDIR /app
COPY spring-app/gradlew spring-app/gradlew.bat spring-app/settings.gradle spring-app/build.gradle ./
COPY spring-app/gradle gradle
RUN chmod +x gradlew
# Download dependencies (cached layer)
RUN ./gradlew dependencies --no-daemon || true
# Copy source and build
COPY spring-app/src src
COPY shared/keyword_aliases.json src/main/resources/keyword_aliases.json
RUN ./gradlew bootJar --no-daemon -x test

# Stage 2: Run
FROM amazoncorretto:17-alpine
WORKDIR /app
RUN mkdir -p /app/data
COPY --from=builder /app/build/libs/*.jar app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "app.jar"]
