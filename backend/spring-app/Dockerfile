# Stage 1: Build
FROM gradle:8.7-jdk17 AS builder
WORKDIR /app
COPY gradlew gradlew.bat settings.gradle build.gradle ./
COPY gradle gradle
RUN chmod +x gradlew
# Download dependencies (cached layer)
RUN ./gradlew dependencies --no-daemon || true
# Copy source and build
COPY src src
RUN ./gradlew bootJar --no-daemon -x test

# Stage 2: Run
FROM amazoncorretto:17-alpine
WORKDIR /app
RUN mkdir -p /app/data
COPY --from=builder /app/build/libs/*.jar app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "app.jar"]
