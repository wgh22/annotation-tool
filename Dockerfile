# 使用官方的 ROS Noetic 基础镜像
FROM osrf/ros:noetic-desktop-full

# 设置非交互式安装，避免构建时卡住
ENV DEBIAN_FRONTEND=noninteractive

# 更新包列表并安装 Python3 pip 和其他依赖
RUN apt-get update && apt-get install -y \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 库
# tqdm 用于显示进度条
RUN pip3 install --no-cache-dir numpy opencv-python tqdm

# 创建工作目录
WORKDIR /app

# 将 src 文件夹复制到容器的 /app/src 目录下
COPY ./src ./src

# 设置默认命令，当容器启动时，会进入 bash
# 这样你就可以手动运行脚本了
CMD ["bash"]
