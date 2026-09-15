#!/bin/bash
# ===================================
# A股智能分析系统 - 测试脚本
# ===================================
#
# 使用方法：
#   ./scripts/test.sh [测试场景]
#
# 测试场景：
#   market      - 仅大盘复盘
#   a-stock     - A股个股分析（茅台、平安银行）
#   etf         - etf分析(卫星etf 563230)
#   single      - 单股模式测试
#   dry-run     - 仅获取数据不分析
#   full        - 完整流程测试
#   quick       - 快速测试（单只股票）
#   all         - 运行所有测试
#
# 示例：
#   ./scripts/test.sh market      # 测试大盘复盘
#   ./scripts/test.sh quick       # 快速测试
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "$REPO_ROOT"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 打印带颜色的信息
info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

header() {
    echo ""
    echo "=============================================="
    echo -e "${GREEN}$1${NC}"
    echo "=============================================="
    echo ""
}

# 检查Python环境
check_python() {
    if ! command -v python3 &> /dev/null; then
        error "Python3 未安装"
        exit 1
    fi
    info "Python版本: $(python3 --version)"
}

# 检查依赖
check_deps() {
    info "检查依赖..."
    python3 -c "import akshare" 2>/dev/null || { warn "akshare 未安装，A股测试可能失败"; }
    success "依赖检查完成"
}

# ==================== 测试场景 ====================

# 测试1: 大盘复盘
test_market() {
    header "测试场景: 大盘复盘"
    info "运行大盘复盘分析..."
    python3 main.py --market-review "$@"
    success "大盘复盘测试完成"
}

# 测试2: A股分析
test_a_stock() {
    header "测试场景: A股分析"
    info "分析A股: 600519(茅台), 000001(平安银行)"
    python3 main.py --stocks 600519,000001  --no-market-review "$@"
    success "A股分析测试完成"
}

# 测试2.5: ETF分析
test_etf() {
    header "测试场景: ETF分析"
    info "分析ETF: 563230(卫星ETF)"
    python3 main.py --stocks 563230,512400 --no-market-review "$@"
    success "ETF分析测试完成"
}

# 测试6: 单股推送模式
test_single() {
    header "测试场景: 单股推送模式"
    info "测试单股推送模式..."
    python3 main.py --stocks 600519 --single-notify --no-market-review
    success "单股推送模式测试完成"
}

# 测试7: dry-run模式
test_dry_run() {
    header "测试场景: Dry-Run 模式"
    info "仅获取数据，不进行AI分析..."
    python3 main.py --stocks 600519,300750 --dry-run --no-notify
    success "Dry-Run 测试完成"
}

# 测试8: 完整流程
test_full() {
    header "测试场景: 完整流程"
    info "运行完整分析流程（个股+大盘）..."
    python3 main.py --stocks 600519 --no-notify
    success "完整流程测试完成"
}

# 测试9: 快速测试
test_quick() {
    header "测试场景: 快速测试"
    info "单只股票快速测试..."
    python3 main.py --stocks 600519 --no-market-review --no-notify "$@"
    success "快速测试完成"
}

# 测试10: 代码识别测试
test_code_recognition() {
    header "测试场景: 代码识别"
    info "测试股票代码识别逻辑..."

    python3 << 'PYTEST'
import sys
sys.path.insert(0, '.')
from src.services.stock_list_parser import IndexRegistry, parse_stock_list

test_cases = [
    ("600519", True, "A股-茅台"),
    ("000001", True, "A股-平安"),
    ("AAPL", False, "非A股代码"),
    ("HK00700", False, "非A股代码"),
]

print("\n股票代码识别测试:")
print("-" * 60)
all_pass = True
for code, expected, desc in test_cases:
    accepted = parse_stock_list(code, registry=IndexRegistry())[0].asset_type != "unsupported"
    ok = accepted == expected
    status = "✅" if ok else "❌"
    all_pass = all_pass and ok
    print(f"{status} {code:10} | accepted:{accepted!s:5} | {desc}")

print("-" * 60)
print(f"{'✅ 所有测试通过!' if all_pass else '❌ 有测试失败!'}")
sys.exit(0 if all_pass else 1)
PYTEST

    success "代码识别测试完成"
}

# 测试12: 语法检查
test_syntax() {
    header "测试场景: Python 语法检查"
    info "检查所有Python文件语法..."

    python3 -m py_compile main.py src/config.py src/notification.py \
        data_provider/akshare_fetcher.py \
        bot/commands/analyze.py

    success "语法检查通过"
}

# 测试13: Flake8 静态检查
test_flake8() {
    header "测试场景: Flake8 静态检查"
    info "运行 Flake8 检查严重错误..."

    if command -v flake8 &> /dev/null; then
        flake8 main.py src/config.py src/notification.py --select=F821,E999 --max-line-length=120
        success "Flake8 检查通过"
    else
        warn "Flake8 未安装，跳过检查"
    fi
}

# 运行所有测试
test_all() {
    header "运行所有测试"

    test_syntax
    test_code_recognition
    test_flake8

    echo ""
    info "以下测试需要网络和API配置，可能会失败:"
    echo ""

    test_dry_run || warn "Dry-Run 测试失败（可能是网络问题）"
    test_quick || warn "快速测试失败（可能是API问题）"

    success "所有测试完成!"
}

# ==================== 主程序 ====================

main() {
    header "A股智能分析系统 - 测试"

    check_python
    check_deps

    case "${1:-help}" in
        market)
            shift
            test_market "$@"
            ;;
        a-stock|a_stock|astock)
            shift
            test_a_stock "$@"
            ;;
        etf)
            shift
            test_etf "$@"
            ;;
        single)
            shift
            test_single "$@"
            ;;
        dry-run|dryrun|dry)
            shift
            test_dry_run "$@"
            ;;
        full)
            shift
            test_full "$@"
            ;;
        quick|q)
            shift
            test_quick "$@"
            ;;
        code|recognition)
            shift
            test_code_recognition "$@"
            ;;
        syntax)
            shift
            test_syntax "$@"
            ;;
        flake8|lint)
            shift
            test_flake8 "$@"
            ;;
        all)
            shift
            test_all "$@"
            ;;
        help|--help|-h|*)
            echo "使用方法: $0 [测试场景]"
            echo ""
            echo "测试场景:"
            echo "  market      - 仅大盘复盘"
            echo "  a-stock     - A股个股分析"
            echo "  etf         - ETF分析"
            echo "  single      - 单股推送模式"
            echo "  dry-run     - 仅获取数据"
            echo "  full        - 完整流程"
            echo "  quick       - 快速测试（推荐）"
            echo "  code        - 代码识别测试"
            echo "  syntax      - 语法检查"
            echo "  flake8      - 静态检查"
            echo "  all         - 运行所有测试"
            echo ""
            echo "示例:"
            echo "  $0 quick     # 快速测试"
            echo "  $0 code      # 测试代码识别"
            echo "  $0 all       # 运行所有测试"
            ;;
    esac
}

main "$@"
