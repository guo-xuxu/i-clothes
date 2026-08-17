package com.iclothes;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import com.iclothes.config.AppProperties;

@SpringBootApplication
@EnableConfigurationProperties(AppProperties.class)
public class IclothesApplication {
    public static void main(String[] args) {
        SpringApplication.run(IclothesApplication.class, args);
    }
}
