# 测试指南

## 准备工作

### 1. 配置环境变量
确保 `.env` 文件中已配置：
```
QIANWEN_API_KEY=your_api_key_here
```

### 2. 准备测试图片
将测试图片放在 `test/images/` 目录下，例如：
- `test/images/sample1.jpg` - 穿搭参考图
- `test/images/sample2.jpg` - 场景参考图

可以使用：
- 网上下载的穿搭图片
- 时尚杂志截图
- 场景照片（如咖啡厅、派对等）

## 运行测试

### 激活虚拟环境
```bash
# Windows
.conda\Scripts\activate

# 或者直接用完整路径运行
.conda\Scripts\python test/test_workflow.py
```

### 运行工作流测试
```bash
python test/test_workflow.py
```

## 测试说明

- **test_single_image**: 测试单张图片 + 文字描述
- **test_multiple_images**: 测试多张图片 + 文字描述
- **test_no_description**: 测试只有图片，无文字描述

默认只运行第一个测试，通过后可以取消注释其他测试。
