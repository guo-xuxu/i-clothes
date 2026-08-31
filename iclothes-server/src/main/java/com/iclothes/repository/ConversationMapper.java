package com.iclothes.repository;

import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.iclothes.dto.ConversationSummaryDto;
import com.iclothes.entity.Conversation;

@Mapper
public interface ConversationMapper extends BaseMapper<Conversation> {

    @Select("""
        SELECT c.id::text AS id, c.title,
               (extract(epoch from c.updated_at))::bigint AS updatedAt,
               (SELECT m.content FROM messages m
                 WHERE m.conversation_id = c.id ORDER BY m.id DESC LIMIT 1) AS preview
        FROM conversations c
        WHERE c.user_id = #{userId}
        ORDER BY c.updated_at DESC
        """)
    List<ConversationSummaryDto> selectSummaries(@Param("userId") Long userId);
}
