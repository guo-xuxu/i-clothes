package com.iclothes.controller;

import java.io.File;
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import com.iclothes.config.AppProperties;

@RestController
public class StaticController {

    private final AppProperties properties;

    public StaticController(AppProperties properties) { this.properties = properties; }

    @GetMapping(value = "/", produces = MediaType.TEXT_HTML_VALUE)
    public Resource index() {
        return new FileSystemResource(new File(properties.getFrontend().getDir(), "index.html"));
    }
}
