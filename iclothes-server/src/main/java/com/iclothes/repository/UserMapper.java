package com.iclothes.repository;

import org.apache.ibatis.annotations.Mapper;
import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.iclothes.entity.User;

@Mapper
public interface UserMapper extends BaseMapper<User> {
}
