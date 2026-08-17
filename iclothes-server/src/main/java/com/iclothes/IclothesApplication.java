package com.iclothes;

import java.sql.CallableStatement;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Types;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.util.UUID;
import org.apache.ibatis.type.BaseTypeHandler;
import org.apache.ibatis.type.JdbcType;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import com.baomidou.mybatisplus.autoconfigure.ConfigurationCustomizer;
import com.iclothes.config.AppProperties;

@SpringBootApplication
@EnableConfigurationProperties(AppProperties.class)
public class IclothesApplication {
    public static void main(String[] args) {
        SpringApplication.run(IclothesApplication.class, args);
    }

    /**
     * Registers TypeHandlers the bundled MyBatis (3.5.16) does not provide by
     * default, so the entities map cleanly onto the PostgreSQL schema:
     * <ul>
     *   <li>{@link UUID}: the UUID columns (conversations.id,
     *       messages.conversation_id) need an explicit handler for both
     *       parameter binding and result mapping (autoResultMap).</li>
     *   <li>{@link LocalDateTime}: the schema uses TIMESTAMPTZ, which the PG
     *       driver cannot convert directly to LocalDateTime; read via
     *       OffsetDateTime and strip the offset.</li>
     * </ul>
     */
    @Bean
    public ConfigurationCustomizer typeHandlerCustomizer() {
        return configuration -> {
            configuration.getTypeHandlerRegistry().register(UUID.class, new UuidTypeHandler());
            configuration.getTypeHandlerRegistry().register(LocalDateTime.class, new LocalDateTimeTypeHandler());
        };
    }

    static class UuidTypeHandler extends BaseTypeHandler<UUID> {
        @Override
        public void setNonNullParameter(PreparedStatement ps, int i, UUID parameter, JdbcType jdbcType) throws SQLException {
            ps.setObject(i, parameter, Types.OTHER);
        }

        @Override
        public UUID getNullableResult(ResultSet rs, String columnName) throws SQLException {
            return rs.getObject(columnName, UUID.class);
        }

        @Override
        public UUID getNullableResult(ResultSet rs, int columnIndex) throws SQLException {
            return rs.getObject(columnIndex, UUID.class);
        }

        @Override
        public UUID getNullableResult(CallableStatement cs, int columnIndex) throws SQLException {
            return cs.getObject(columnIndex, UUID.class);
        }
    }

    static class LocalDateTimeTypeHandler extends BaseTypeHandler<LocalDateTime> {
        @Override
        public void setNonNullParameter(PreparedStatement ps, int i, LocalDateTime parameter, JdbcType jdbcType) throws SQLException {
            ps.setObject(i, parameter);
        }

        @Override
        public LocalDateTime getNullableResult(ResultSet rs, String columnName) throws SQLException {
            OffsetDateTime odt = rs.getObject(columnName, OffsetDateTime.class);
            return odt == null ? null : odt.toLocalDateTime();
        }

        @Override
        public LocalDateTime getNullableResult(ResultSet rs, int columnIndex) throws SQLException {
            OffsetDateTime odt = rs.getObject(columnIndex, OffsetDateTime.class);
            return odt == null ? null : odt.toLocalDateTime();
        }

        @Override
        public LocalDateTime getNullableResult(CallableStatement cs, int columnIndex) throws SQLException {
            OffsetDateTime odt = cs.getObject(columnIndex, OffsetDateTime.class);
            return odt == null ? null : odt.toLocalDateTime();
        }
    }
}
