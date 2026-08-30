FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
# 国内服务器直连 PyPI 极慢：固定用阿里云 PyPI 镜像（服务器在阿里云时最快）
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ -r requirements.txt
COPY app ./app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
