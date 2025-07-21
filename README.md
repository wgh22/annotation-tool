# ROS Bag 数据处理与标注工具

本项目提供了一套用于处理 ROS bag 数据并对生成的视频进行标注的工具。它主要包含两个部分：
1.  一个数据处理脚本 (`process_data.py`)，用于从 `.bag` 文件中提取视频、传感器数据等，并将其转换为标准的视频文件和文本文件。
2.  一个基于 PyQt 的图形用户界面 (`main.py`)，用于播放处理后的视频、进行数据标注，并将标注结果保存为 JSON 文件。

整个工作流程已使用 Docker 进行了容器化，以简化环境配置和依赖管理。

## 目录结构

```
.
├── compose.yml         # Docker Compose 配置文件，用于简化容器管理
├── Dockerfile          # Docker 镜像定义文件
├── bagdata/            # 存放原始 .bag 数据文件的输入目录
├── markout/            # 存放标注后生成的 .json 文件的输出目录
├── src/                # 存放所有 Python 源代码
│   ├── main.py         # PyQt 标注程序的主入口
│   ├── process_data.py # 用于预处理 ROS bag 文件的脚本
│   ├── gui/            # 包含 GUI 界面代码
│   └── logic/          # 包含应用程序的业务逻辑
└── video/              # 存放 process_data.py 处理后的视频和数据文件
```

## 环境准备

请确保您的系统已安装以下软件：
- Docker
- Docker Compose

## 使用说明

本工具的使用分为两步：首先处理 ROS bag 数据，然后启动 GUI 程序进行标注。

### 步骤 1: 处理 ROS Bag 数据

此步骤会将 `bagdata` 目录下的 `.bag` 文件转换为 `video` 目录下的视频文件和同步的数据文本文件。

1.  **准备数据**: 将您需要处理的 ROS bag 数据文件夹（例如 `2025_03_11_11_18_45`）放入 `bagdata` 目录中。

2.  **构建 Docker 镜像**: 在 `pyqt` 目录下打开终端，运行以下命令来构建 Docker 镜像。
    ```bash
    docker compose build
    ```

3.  **运行处理脚本**: 使用以下命令运行 `process_data.py` 脚本。
    ```bash
    docker compose up
    python3 process_data.py
    ```
    该命令会启动一个临时的 Docker 容器，在容器内执行处理脚本，将src bagdata video挂载在容器中

    **可选参数**:
    - `--segment`: 如果您的 `bag` 数据中包含了 `keyboard.bag` 文件，用于标记有效数据段的起止，可以添加此参数。脚本会根据键盘事件将数据切分成多个片段。
    - `--bagdir`: 默认为'../bagdata'，可以传参进行更改
    - `--outdir`: 默认为'../video'，可以传参进行更改

### 步骤 2: 启动标注程序

数据处理完成后，您可以启动 PyQt 程序对 `video` 目录下的视频进行标注。

1.  **启动程序**: 在 `pyqt` 目录下打开终端，运行以下命令启动 PyQt 程序。
    ```bash
    python3 main.py
    ```

2.  **使用程序**:
    程序启动后，您就可以在界面中加载 `video` 目录下的视频，进行标注操作。标注后生成的 `.json` 文件将保存在 `markout` 目录中。

## 脚本说明

- **`src/process_data.py`**:
  - **功能**: 遍历 `bag_dir` 下的每个子目录，读取其中的 `.bag` 文件（图像、机械臂状态、手部状态等）。
  - 将不同 topic 的数据进行时间戳对齐和插值。
  - 将图像序列保存为 `.mp4` 视频文件。
  - 将同步后的传感器数据保存为 `.txt` 文件。
  - 支持根据 `keyboard.bag` 的事件进行分段处理。

- **`src/main.py`**:
  - **功能**: 启动一个 PyQt 应用程序。
  - 提供一个用户友好的界面，用于加载和播放 `video` 目录中生成的视频。
  - 允许用户对视频进行标注，并将结果以 `JSON` 格式保存到 `markout` 目录。
  - 具体的标注逻辑和功能请参考 `src/gui` 和 `src/logic` 中的代码。
