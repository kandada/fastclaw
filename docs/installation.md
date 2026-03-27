# 安装指南

## 环境要求

- Python 3.12 或更高版本
- pip 包管理器

## 安装步骤

### 1. 克隆项目

```bash
git clone <repository-url>
cd fastclaw_local
```

### 2. 创建虚拟环境（推荐）

```bash
python3 -m venv .venv
source .venv/bin/activate  # Linux/macOS
# 或
.venv\Scripts\activate  # Windows
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 配置

复制并编辑配置文件：

```bash
cp workspace/settings.json.example workspace/settings.json
```

### 5. 启动服务

```bash
python main.py start
```

## 设置别名（可选）

为方便使用，可以设置命令别名：

### macOS/Linux

编辑 `~/.bashrc` 或 `~/.zshrc`：

```bash
alias fastclaw='PYTHONPATH="/path/to/fastclaw_local/vendor:$PYTHONPATH" python3 /path/to/fastclaw_local/main.py'
```

然后：

```bash
source ~/.zshrc  # 或 source ~/.bashrc
```

之后就可以直接用：

```bash
fastclaw start
fastclaw status
fastclaw chat
```

## 验证安装

```bash
python main.py status
```

输出应显示服务状态。
