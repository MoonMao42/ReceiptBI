#!/bin/bash

# QueryGPT 完整安装启动脚本 v2.0
# Complete Setup & Start Script v2.0
# 整合了setup.sh的智能配置和start.sh的启动功能

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m'
BOLD='\033[1m'

# 全局变量
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
PYTHON_CMD=""
IS_FIRST_RUN=false
BACKUP_SUFFIX=$(date +%Y%m%d_%H%M%S)

# 打印带颜色的消息
print_message() {
    local type=$1
    local message=$2
    case $type in
        "success") echo -e "${GREEN}✓${NC} $message" ;;
        "error") echo -e "${RED}✗${NC} $message" ;;
        "warning") echo -e "${YELLOW}⚠${NC} $message" ;;
        "info") echo -e "${BLUE}ℹ${NC} $message" ;;
        "header") echo -e "\n${BOLD}${CYAN}$message${NC}" ;;
        "step") echo -e "${MAGENTA}►${NC} $message" ;;
    esac
}

# 打印横幅
print_banner() {
    clear
    echo -e "${CYAN}╔════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║${NC}     ${BOLD}QueryGPT Setup v2.0${NC}                              ${CYAN}║${NC}"
    echo -e "${CYAN}║${NC}     完整安装配置并启动 / Complete Setup & Start       ${CYAN}║${NC}"
    echo -e "${CYAN}╚════════════════════════════════════════════════════════╝${NC}"
    echo ""
}

# 显示进度
show_progress() {
    local current=$1
    local total=$2
    local width=50
    local percentage=$((current * 100 / total))
    local completed=$((width * current / total))
    
    printf "\r["
    printf "%${completed}s" | tr ' ' '='
    printf "%$((width - completed))s" | tr ' ' ' '
    printf "] %d%%" "$percentage"
    
    if [ "$current" -eq "$total" ]; then
        echo ""
    fi
}

# 检查是否首次运行
check_first_run() {
    print_message "header" "检查运行状态 / Checking Run Status"
    
    local indicators=0
    
    if [ ! -d "venv_py310" ] && [ ! -d "venv" ]; then
        ((indicators++))
        print_message "info" "未检测到虚拟环境 / No virtual environment detected"
    fi
    
    if [ ! -f ".env" ]; then
        ((indicators++))
        print_message "info" "未检测到配置文件 / No configuration file detected"
    fi
    
    if [ ! -d "logs" ] || [ ! -d "cache" ]; then
        ((indicators++))
        print_message "info" "未检测到必要目录 / Required directories not detected"
    fi
    
    if [ $indicators -ge 2 ]; then
        IS_FIRST_RUN=true
        print_message "info" "检测到首次运行，将执行完整初始化 / First run detected, performing full initialization"
    else
        print_message "success" "检测到现有安装 / Existing installation detected"
    fi
    echo ""
}

# 检查Python版本
check_python() {
    print_message "header" "检查 Python 环境 / Checking Python Environment"
    
    # 优先检查 python3.10
    if command -v python3.10 &> /dev/null; then
        PYTHON_CMD="python3.10"
        local version=$(python3.10 -V 2>&1 | grep -Po '\d+\.\d+\.\d+')
        print_message "success" "找到 Python 3.10: $version"
    elif command -v python3 &> /dev/null; then
        local version=$(python3 -V 2>&1 | grep -Po '\d+\.\d+\.\d+')
        local major=$(echo $version | cut -d. -f1)
        local minor=$(echo $version | cut -d. -f2)
        
        if [ "$major" -eq 3 ] && [ "$minor" -eq 10 ]; then
            PYTHON_CMD="python3"
            print_message "success" "找到 Python $version"
        else
            print_message "warning" "Python 版本不匹配: $version (推荐 3.10.x)"
            PYTHON_CMD="python3"
        fi
    else
        print_message "error" "未找到 Python 3"
        exit 1
    fi
    echo ""
}

# 设置虚拟环境
setup_venv() {
    print_message "header" "配置虚拟环境 / Configuring Virtual Environment"
    
    local venv_dir="venv_py310"
    
    if [ -d "$venv_dir" ]; then
        if [ -f "$venv_dir/bin/activate" ]; then
            print_message "info" "使用现有虚拟环境 / Using existing virtual environment"
        else
            print_message "warning" "虚拟环境损坏，重新创建... / Virtual environment corrupted, recreating..."
            rm -rf "$venv_dir"
            $PYTHON_CMD -m venv "$venv_dir"
        fi
    else
        print_message "info" "创建虚拟环境... / Creating virtual environment..."
        $PYTHON_CMD -m venv "$venv_dir"
        print_message "success" "虚拟环境创建成功 / Virtual environment created"
    fi
    
    # 激活虚拟环境
    source "$venv_dir/bin/activate"
    
    # 升级pip
    print_message "info" "升级 pip... / Upgrading pip..."
    pip install --upgrade pip --quiet
    print_message "success" "pip 已升级 / pip upgraded"
    echo ""
}

# 安装依赖
install_dependencies() {
    print_message "header" "管理项目依赖 / Managing Dependencies"
    
    if [ ! -f "requirements.txt" ]; then
        print_message "warning" "未找到 requirements.txt，创建默认依赖 / Creating default requirements.txt"
        cat > requirements.txt << 'EOF'
Flask==2.3.3
flask-cors==4.0.0
pymysql==1.1.0
python-dotenv==1.0.0
openai==1.3.0
litellm==1.0.0
open-interpreter==0.4.3
pandas==2.0.3
numpy==1.24.3
matplotlib==3.7.2
seaborn==0.12.2
plotly==5.15.0
EOF
    fi
    
    # 检查是否需要安装
    local need_install=false
    
    if ! pip show flask &> /dev/null || ! pip show open-interpreter &> /dev/null; then
        need_install=true
    fi
    
    if [ "$need_install" = true ] || [ "$IS_FIRST_RUN" = true ]; then
        print_message "info" "安装依赖包... / Installing dependencies..."
        print_message "warning" "这可能需要几分钟，请耐心等待... / This may take a few minutes, please be patient..."
        
        # 特别处理 OpenInterpreter
        if grep -q "open-interpreter" requirements.txt; then
            print_message "warning" "安装 OpenInterpreter 0.4.3 (较大，需要时间)... / Installing OpenInterpreter 0.4.3 (large, takes time)..."
            echo "正在下载和安装，请稍候... / Downloading and installing, please wait..."
            
            # 不使用quiet，显示进度
            pip install "open-interpreter==0.4.3" --progress-bar on 2>&1 | while IFS= read -r line; do
                # 只显示关键信息
                if [[ "$line" == *"Downloading"* ]] || [[ "$line" == *"Installing"* ]] || [[ "$line" == *"Successfully"* ]]; then
                    echo "  $line"
                fi
            done
            print_message "success" "OpenInterpreter 安装完成 / OpenInterpreter installed"
        fi
        
        # 安装其他依赖
        print_message "info" "安装其他依赖包... / Installing other dependencies..."
        echo "进度 / Progress:"
        
        # 显示简化的进度
        pip install -r requirements.txt 2>&1 | while IFS= read -r line; do
            if [[ "$line" == *"Collecting"* ]]; then
                package=$(echo "$line" | sed 's/Collecting //' | cut -d' ' -f1)
                echo -n "  📦 安装 / Installing: $package... "
            elif [[ "$line" == *"Successfully installed"* ]]; then
                echo "✓"
            elif [[ "$line" == *"Requirement already satisfied"* ]]; then
                package=$(echo "$line" | sed 's/.*Requirement already satisfied: //' | cut -d' ' -f1)
                echo "  ✓ 已安装 / Already installed: $package"
            fi
        done
        
        echo ""
        print_message "success" "所有依赖安装完成！/ All dependencies installed!"
    else
        print_message "success" "依赖已是最新 / Dependencies up to date"
    fi
    echo ""
}

# 创建目录结构
create_directories() {
    print_message "header" "检查目录结构 / Checking Directory Structure"
    
    local dirs=("logs" "cache" "output" "backend/data" "config" "backup")
    local created=0
    
    for dir in "${dirs[@]}"; do
        if [ ! -d "$dir" ]; then
            mkdir -p "$dir"
            ((created++))
            print_message "success" "创建目录 / Created: $dir"
        fi
    done
    
    if [ $created -eq 0 ]; then
        print_message "success" "所有目录已存在 / All directories exist"
    fi
    echo ""
}

# 配置环境变量
setup_env() {
    print_message "header" "管理配置文件 / Managing Configuration"
    
    # 创建 .env.example
    if [ ! -f ".env.example" ]; then
        cat > .env.example << 'EOF'
# API配置
API_KEY=your-api-key-here
API_BASE_URL=https://api.openai.com/v1/
DEFAULT_MODEL=gpt-4

# 数据库配置
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_password
DB_DATABASE=test_db

# 系统配置
LOG_LEVEL=INFO
LOG_FILE=logs/app.log
CACHE_TTL=3600
OUTPUT_DIR=output
CACHE_DIR=cache
EOF
    fi
    
    if [ -f ".env" ]; then
        print_message "success" "检测到现有配置文件，保持不变 / Existing configuration detected, keeping it"
        print_message "info" "如需重置配置，请删除 .env 文件后重新运行"
        print_message "info" "To reset config, delete .env and run again"
    else
        print_message "info" "创建配置文件... / Creating configuration file..."
        
        # 先检查是否有.env.example
        if [ -f ".env.example" ]; then
            print_message "info" "从模板创建配置 / Creating from template"
            cp .env.example .env
            
            # 交互式询问用户选择API类型
            echo ""
            print_message "info" "请选择API类型 / Please choose API type:"
            echo "  1) GPT API (需要API密钥 / Requires API key)"
            echo "  2) Ollama 本地模型 (免费 / Free)"
            echo ""
            read -p "请输入选择 (1-2) / Enter choice (1-2): " api_choice
            
            if [ "$api_choice" = "2" ]; then
                # 修改为Ollama配置
                sed -i.bak 's/^API_KEY=sk-YOUR-API-KEY-HERE/API_KEY=not-needed-for-local/' .env
                sed -i.bak 's|^API_BASE_URL=https://api.example.com/v1/|API_BASE_URL=http://localhost:11434/v1|' .env
                sed -i.bak 's/^DEFAULT_MODEL=gpt-4.1/DEFAULT_MODEL=llama2/' .env
                rm -f .env.bak
                print_message "success" "已配置为Ollama本地模型 / Configured for Ollama"
            else
                print_message "warning" "请编辑 .env 文件填入你的API密钥"
                print_message "warning" "Please edit .env file to add your API key"
            fi
        else
            # 创建默认配置
            cat > .env << 'EOF'
# API配置
API_KEY=sk-YOUR-API-KEY-HERE
API_BASE_URL=https://api.example.com/v1/
DEFAULT_MODEL=gpt-4.1

# 数据库配置
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=
DB_DATABASE=test

# 系统配置
LOG_LEVEL=INFO
LOG_FILE=logs/app.log
CACHE_TTL=3600
OUTPUT_DIR=output
CACHE_DIR=cache
EOF
            print_message "success" "配置文件已创建 / Configuration created"
            print_message "warning" "默认配置使用本地Ollama，如需其他API请编辑.env文件"
            print_message "warning" "Default config uses local Ollama, edit .env for other APIs"
        fi
    fi
    
    # 创建模型配置
    setup_models
    echo ""
}

# 配置模型设置
setup_models() {
    print_message "info" "配置模型设置... / Configuring model settings..."
    
    # 创建示例配置
    if [ ! -f "config/models.example.json" ]; then
        cat > config/models.example.json << 'EOF'
{
  "models": [
    {
      "id": "gpt-4.1",
      "name": "GPT-4.1",
      "type": "openai",
      "api_base": "https://api.openai.com/v1/",
      "api_key": "your-api-key-here",
      "max_tokens": 4096,
      "temperature": 0.7,
      "status": "active"
    }
  ]
}
EOF
    fi
    
    # 如果没有models.json，创建一个
    if [ ! -f "config/models.json" ]; then
        cat > config/models.json << 'EOF'
{
  "models": [
    {
      "id": "ollama-llama2",
      "name": "Ollama Llama2 (本地免费)",
      "type": "ollama",
      "api_base": "http://localhost:11434/v1",
      "api_key": "not-needed",
      "max_tokens": 4096,
      "temperature": 0.7,
      "status": "active"
    },
    {
      "id": "gpt-4",
      "name": "GPT-4 (需要API密钥)",
      "type": "openai",
      "api_base": "https://api.openai.com/v1/",
      "api_key": "your-openai-api-key-here",
      "max_tokens": 4096,
      "temperature": 0.7,
      "status": "inactive"
    },
    {
      "id": "claude-3",
      "name": "Claude 3 (需要API密钥)",
      "type": "anthropic",
      "api_base": "https://api.anthropic.com/v1",
      "api_key": "your-anthropic-api-key-here",
      "max_tokens": 4096,
      "temperature": 0.7,
      "status": "inactive"
    },
    {
      "id": "custom-api",
      "name": "自定义API (配置你的API)",
      "type": "custom",
      "api_base": "https://your-api-endpoint.com/v1",
      "api_key": "your-custom-api-key-here",
      "max_tokens": 4096,
      "temperature": 0.7,
      "status": "inactive"
    }
  ]
}
EOF
        print_message "success" "模型配置已创建 / Model configuration created"
        print_message "info" "默认启用Ollama本地模型，其他模型需配置API密钥"
    fi
    
    # 创建config.json
    if [ ! -f "config/config.json" ]; then
        cat > config/config.json << 'EOF'
{
  "features": {
    "smart_routing": {
      "enabled": false
    }
  }
}
EOF
    fi
}

# 查找可用端口 - 跨平台版本
find_available_port() {
    local port=5000
    local max_port=5010
    
    # 检测运行环境
    local is_wsl=false
    local is_macos=false
    if grep -qi microsoft /proc/version 2>/dev/null; then
        is_wsl=true
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        is_macos=true
    fi
    
    while [ $port -le $max_port ]; do
        local port_available=false
        
        if [ "$is_macos" = true ]; then
            # macOS: 使用 lsof
            if ! lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
                port_available=true
            fi
        elif [ "$is_wsl" = true ] || [[ "$OSTYPE" == "linux-gnu"* ]]; then
            # WSL/Linux: 使用 ss 或 netstat
            if command -v ss >/dev/null 2>&1; then
                if ! ss -tln | grep -q ":$port "; then
                    port_available=true
                fi
            elif command -v netstat >/dev/null 2>&1; then
                if ! netstat -tln 2>/dev/null | grep -q ":$port "; then
                    port_available=true
                fi
            else
                # 最后尝试直接连接测试
                if ! (echo > /dev/tcp/127.0.0.1/$port) >/dev/null 2>&1; then
                    port_available=true
                fi
            fi
        else
            # 默认方法
            if ! (echo > /dev/tcp/127.0.0.1/$port) >/dev/null 2>&1; then
                port_available=true
            fi
        fi
        
        if [ "$port_available" = true ]; then
            echo $port
            return 0
        fi
        
        print_message "info" "端口 $port 已被占用，尝试下一个... / Port $port occupied, trying next..."
        port=$((port + 1))
    done
    
    print_message "error" "无法找到可用端口 / No available port found"
    return 1
}

# 系统健康检查
health_check() {
    print_message "header" "系统健康检查 / System Health Check"
    
    local score=0
    local max_score=5
    
    # 检查虚拟环境
    if [ -d "venv_py310" ] || [ -d "venv" ]; then
        ((score++))
        print_message "success" "虚拟环境 / Virtual environment: OK"
    else
        print_message "error" "虚拟环境 / Virtual environment: Missing"
    fi
    
    # 检查配置文件
    if [ -f ".env" ]; then
        ((score++))
        print_message "success" "配置文件 / Configuration: OK"
    else
        print_message "error" "配置文件 / Configuration: Missing"
    fi
    
    # 检查目录
    if [ -d "logs" ] && [ -d "cache" ] && [ -d "output" ]; then
        ((score++))
        print_message "success" "目录结构 / Directory structure: OK"
    else
        print_message "warning" "目录结构 / Directory structure: Incomplete"
    fi
    
    # 检查依赖
    if pip show flask &> /dev/null; then
        ((score++))
        print_message "success" "核心依赖 / Core dependencies: OK"
    else
        print_message "error" "核心依赖 / Core dependencies: Missing"
    fi
    
    # 检查端口
    if find_available_port &> /dev/null; then
        ((score++))
        print_message "success" "端口可用 / Port available: OK"
    fi
    
    echo ""
    print_message "info" "健康评分 / Health Score: $score/$max_score"
    
    if [ $score -eq $max_score ]; then
        print_message "success" "系统状态完美 / System is perfect!"
    elif [ $score -ge 3 ]; then
        print_message "warning" "系统基本就绪 / System mostly ready"
    else
        print_message "error" "系统需要初始化 / System needs initialization"
    fi
    echo ""
}

# 启动服务
start_server() {
    print_message "header" "启动服务 / Starting Service"
    
    # 查找可用端口
    local PORT=$(find_available_port)
    if [ -z "$PORT" ]; then
        exit 1
    fi
    
    export PORT
    
    # 清除代理环境变量
    unset http_proxy
    unset https_proxy
    unset HTTP_PROXY
    unset HTTPS_PROXY
    
    echo ""
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}✓ 系统启动成功！${NC}"
    echo -e "访问地址: ${BLUE}http://localhost:${PORT}${NC}"
    echo -e "停止服务: ${YELLOW}Ctrl+C${NC}"
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    
    # 自动打开浏览器 (macOS)
    if [[ "$OSTYPE" == "darwin"* ]]; then
        sleep 2 && open "http://localhost:${PORT}" &
    fi
    
    # 启动Flask应用
    cd backend && python app.py
}

# 清理函数
cleanup() {
    echo ""
    print_message "info" "服务已停止 / Service stopped"
    if [ -n "$VIRTUAL_ENV" ]; then
        deactivate 2>/dev/null
    fi
    exit 0
}

# 错误处理
error_handler() {
    local line_no=$1
    print_message "error" "脚本在第 $line_no 行出错 / Script failed at line $line_no"
    cleanup
    exit 1
}

# 设置信号处理
trap 'error_handler $LINENO' ERR
trap cleanup INT TERM EXIT

# 主函数
main() {
    print_banner
    
    # 检查是否在项目根目录
    if [ ! -f "backend/app.py" ]; then
        print_message "error" "请在项目根目录运行此脚本 / Please run from project root"
        exit 1
    fi
    
    # 完整的设置和启动流程
    check_first_run
    check_python
    setup_venv
    install_dependencies
    create_directories
    setup_env
    health_check
    start_server
}

# 处理命令行参数
case "${1:-}" in
    --help|-h)
        echo "QueryGPT Setup - 完整安装启动脚本"
        echo "用法: ./setup.sh [选项]"
        echo ""
        echo "选项:"
        echo "  无参数        执行完整安装并启动"
        echo "  --help, -h    显示帮助信息"
        echo ""
        exit 0
        ;;
    *)
        main
        ;;
esac