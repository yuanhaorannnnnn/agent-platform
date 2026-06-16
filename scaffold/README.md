# scaffold

模块化 Bash 配置仓库，支持 Ubuntu / macOS 双平台，通过软链接管理 `~/.bashrc`。

## 结构

```
scaffold/
├── bash/
│   ├── bashrc                # 主入口，OS 自动检测
│   ├── common/               # 跨平台通用
│   │   ├── 00-core           # Shell 默认（history、prompt、shopt）
│   │   ├── 10-env            # PATH helper、EDITOR、NVM
│   │   ├── 20-aliases        # 通用别名（ls、git、kj、config）
│   │   ├── 30-functions      # 通用函数（proxy、tp、git helpers、pix、tmux）
│   │   └── 40-tools          # 通用工具（gcloud、fzf、starship、zoxide）
│   ├── linux/                # Ubuntu 专属
│   │   ├── 00-core           # lesspipe、debian_chroot、dircolors、bash-completion
│   │   ├── 10-env            # CUDA、GCC、CMake、NVim、CARLA/UE5
│   │   ├── 20-aliases        # /media 路径、CARLA 构建、nvidia-smi
│   │   ├── 30-functions      # cuda()、ue_path()
│   │   └── 40-tools          # conda（anaconda3）、fzf（Debian 路径）
│   ├── mac/                  # macOS 专属
│   │   ├── 00-core           # bash-completion（Homebrew 路径）
│   │   ├── 10-env            # Homebrew PATH
│   │   ├── 20-aliases        # open（替代 xdg-open）
│   │   ├── 30-functions      # 预留
│   │   └── 40-tools          # conda（通用检测）、缺失工具告警
│   ├── secrets               # API 密钥（gitignored）
│   └── secrets.example       # 密钥模板
├── bin/
│   ├── claude-switch         # Claude Code 配置切换
│   ├── deploy                # 一键部署 scaffold + agent-platform + agent-skills
│   ├── audit-bin             # ~/.local/bin 脚本溯源（pip/conda/npm/apt/自定义）
│   └── my                    # 输出所有自建 alias/function/script/service
├── Brewfile                  # macOS Homebrew 依赖清单
├── install.sh                # 安装脚本（OS 感知）
└── .gitignore
```

## 安装

```bash
git clone https://github.com/yuanhaorannnnnn/scaffold.git ~/scaffold
cd ~/scaffold && ./install.sh
```

复制密钥模板并填入真实值：

```bash
cp bash/secrets.example bash/secrets
```

修改后重载：`src`（等同于 `source ~/.bashrc`）

### macOS

```bash
# 1. 装 Homebrew 后一键装依赖
brew bundle --file=~/scaffold/Brewfile

# 2. 切换到新版 bash
sudo chsh -s /opt/homebrew/bin/bash $USER

# 3. 安装
cd ~/scaffold && ./install.sh
```

## 工具

### my — 列出所有自建配置

```bash
my                # 全部（alias + function + script + service）
my --alias         # 只看别名
my --script        # 只看 ~/.local/bin 中自建脚本
my --func          # 只看函数
my --svc           # 只看 systemd 服务
```

### audit-bin — 脚本溯源

```bash
audit-bin                     # 审计 ~/.local/bin
audit-bin ~/other-path        # 审计任意目录
```

输出每项的类型：`CUSTOM-SHELL` / `CUSTOM-PYTHON` / `PIP` / `CONDA` / `NPM` / `APT` / `BINARY`

### claude-switch — Claude Code 配置切换

```bash
claude-switch kimi
claude-switch deepseek
claude-switch list
```

### deploy — 一键部署全栈

```bash
./bin/deploy          # 自动 clone 缺失仓库 + 安装
./bin/deploy --pull   # 同上 + 拉取最新
```

## Secrets 配置

```bash
# 官方 Anthropic
CLAUDE_ANTHROPIC_API_KEY="sk-ant-xxxxxxxx"
CLAUDE_ANTHROPIC_MODEL="claude-sonnet-4-5"

# Kimi
KIMI_API_KEY="sk-xxxxxxxx"
KIMI_ANTHROPIC_BASE_URL="https://api.kimi.com/coding/"
KIMI_ANTHROPIC_MODEL="kimi-k2.6"

# DeepSeek
DEEPSEEK_API_KEY="sk-xxxxxxxx"
DEEPSEEK_ANTHROPIC_BASE_URL="https://api.deepseek.com/anthropic"
DEEPSEEK_ANTHROPIC_MODEL="deepseek-v4-pro[1m]"
```

注意：provider 变量不加 `export`，避免泄漏到子进程（如 Codex）。

## Architecture

加载顺序：`common/*` → `linux/*` 或 `mac/*` → `secrets`

OS 层可以覆盖 common 层的任何设置。bashrc 通过 `uname -s` 自动选择平台。
