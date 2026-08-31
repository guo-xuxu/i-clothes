// ConversationServiceTest.java
package com.iclothes.service;

import java.sql.CallableStatement;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.apache.ibatis.type.BaseTypeHandler;
import org.apache.ibatis.type.JdbcType;
import com.baomidou.mybatisplus.core.MybatisConfiguration;
import com.baomidou.mybatisplus.core.MybatisMapperBuilderAssistant;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.metadata.TableInfoHelper;
import com.iclothes.dto.ConversationDto;
import com.iclothes.entity.Conversation;
import com.iclothes.entity.Message;
import com.iclothes.repository.ConversationMapper;
import com.iclothes.repository.MessageMapper;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class ConversationServiceTest {

    @Mock ConversationMapper conversations;
    @Mock MessageMapper messages;

    @Test
    void getReturnsNullForMissing() {
        UUID id = UUID.randomUUID();
        when(conversations.selectById(id)).thenReturn(null);
        ConversationService service = new ConversationService(conversations, messages);
        assertThat(service.get(1L, id)).isNull();
    }

    @Test
    void createProducesDto() {
        ConversationService service = new ConversationService(conversations, messages);
        ConversationDto dto = service.create(1L);
        assertThat(dto.getId()).isNotNull();
        assertThat(dto.getTitle()).isEqualTo("新对话");
        assertThat(dto.getMessages()).isEmpty();
    }

    @Test
    void trimOnlyDeletesBeyondLimit() {
        // 裁剪逻辑在 RepositoryIT 中覆盖；此处验证不会误删（total <= 50 时不调用 delete）
        ConversationService service = new ConversationService(conversations, messages);
        UUID id = UUID.randomUUID();
        when(messages.selectCount(org.mockito.ArgumentMatchers.any()))
                .thenReturn(10L);
        service.trim(id);
        org.mockito.Mockito.verify(messages, org.mockito.Mockito.never())
                .delete(org.mockito.ArgumentMatchers.any());
    }

    @Test
    void touchUpdatesUpdatedAt() {
        // I3：追加消息后触达 updated_at（列表按更新时间倒序）——mock mapper 下验证 updateById 被调用且时间被刷新
        UUID id = UUID.randomUUID();
        LocalDateTime old = LocalDateTime.now().minusDays(1);
        Conversation existing = new Conversation(id, "标题", old, old, 1L);
        when(conversations.selectById(id)).thenReturn(existing);
        ConversationService service = new ConversationService(conversations, messages);

        service.touch(id);

        ArgumentCaptor<Conversation> cap = ArgumentCaptor.forClass(Conversation.class);
        verify(conversations).updateById(cap.capture());
        assertThat(cap.getValue().getUpdatedAt()).isAfter(old);
    }

    @Test
    void lastMessagesTakesNewestWindowAndRestoresAscendingOrder() throws SQLException {
        // 修复 #2：orderByDesc + LIMIT 取"最近 limit 条"窗口，reverse 恢复升序交给下游。
        // 纯单测无 Spring 上下文：注册 Message 的 TableInfo（UUID 列挂 BaseTypeHandler）才能
        // 解析 LambdaQueryWrapper 的列名并生成 SQL 片段
        MybatisConfiguration configuration = new MybatisConfiguration();
        configuration.getTypeHandlerRegistry().register(UUID.class, new BaseTypeHandler<UUID>() {
            @Override public void setNonNullParameter(PreparedStatement ps, int i, UUID parameter,
                    JdbcType jdbcType) throws SQLException { ps.setObject(i, parameter); }
            @Override public UUID getNullableResult(ResultSet rs, String columnName)
                    throws SQLException { return rs.getObject(columnName, UUID.class); }
            @Override public UUID getNullableResult(ResultSet rs, int columnIndex)
                    throws SQLException { return rs.getObject(columnIndex, UUID.class); }
            @Override public UUID getNullableResult(CallableStatement cs, int columnIndex)
                    throws SQLException { return cs.getObject(columnIndex, UUID.class); }
        });
        TableInfoHelper.initTableInfo(new MybatisMapperBuilderAssistant(configuration, ""),
                Message.class);
        ConversationService service = new ConversationService(conversations, messages);
        UUID id = UUID.randomUUID();
        Message oldest = messageWithId(1L);
        Message newest = messageWithId(2L);
        when(messages.selectList(org.mockito.ArgumentMatchers.any()))
                .thenReturn(new ArrayList<>(List.of(newest, oldest))); // mock DESC 查询返回 [newest, oldest]

        List<Message> result = service.lastMessages(id, 20);

        assertThat(result).containsExactly(oldest, newest); // reverse 后恢复升序

        @SuppressWarnings("unchecked")
        ArgumentCaptor<LambdaQueryWrapper<Message>> cap =
                ArgumentCaptor.forClass(LambdaQueryWrapper.class);
        verify(messages).selectList(cap.capture());
        assertThat(cap.getValue().getSqlSegment())
                .contains("ORDER BY id DESC")
                .contains("LIMIT 20");
    }

    private static Message messageWithId(long id) {
        Message m = new Message();
        m.setId(id);
        return m;
    }
}
