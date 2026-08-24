FROM eclipse-temurin:21-jre
WORKDIR /app
COPY iclothes-server/target/iclothes-server-0.1.0.jar app.jar
COPY frontend/dist ./dist
ENV FRONTEND_DIST=dist
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "app.jar"]
