package com.iclothes.repository;

import org.apache.ibatis.annotations.Mapper;
import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.iclothes.entity.Message;

@Mapper
public interface MessageMapper extends BaseMapper<Message> {
}
