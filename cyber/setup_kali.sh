#!/bin/bash
# setup_kali.sh — Kali Linux setup script for FRIDAY Cyber Security Toolkit
# Run this INSIDE your WSL Kali Linux instance
# Or: wsl -d kali-linux -- bash -c "$(cat setup_kali.sh)"

set -euo pipefail  # [#1] Fail on errors, undefined vars, pipe failures

# ── Logging ────────────────────────────────────────────────────────

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_ok()   { echo -e "${GREEN}[+]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[!]${NC} $1"; }
log_err()  { echo -e "${RED}[-]${NC} $1"; }
log_info() { echo -e "[*] $1"; }

# ── Pre-flight checks ──────────────────────────────────────────────

if [ "$(id -u)" -eq 0 ]; then  # [#2]
    log_err "Don't run this as root. Run as normal user (sudo will be used where needed)."
    exit 1
fi

if ! command -v apt &>/dev/null; then
    log_err "apt not found. This script is for Debian/Kali Linux."
    exit 1
fi

# Check internet connectivity [#3]
if ! ping -c 1 -W 5 8.8.8.8 &>/dev/null; then
    log_err "No internet connection. Please connect and retry."
    exit 1
fi

log_ok "Pre-flight checks passed"

# ── System update ──────────────────────────────────────────────────

log_info "Updating package lists..."
sudo apt update -y

log_info "Upgrading installed packages..."
sudo apt upgrade -y

# ── Core bug bounty tools ──────────────────────────────────────────

log_info "Installing core bug bounty tools..."

CORE_TOOLS=(
    nmap
    sqlmap
    ffuf
    gobuster
    subfinder
    nuclei
    httpx-toolkit
    dnsx
    whatweb
    gospider
    wpscan
    jq
    curl
    openssl
    whois
    dnsutils
    dirb
    dirsearch
    nikto
    hydra
    john
    hashcat
    smbclient
    enum4linux
    nikto
    python3-pip
    python3-venv       # [#4] Needed for virtual environments
    libpcap-dev         # [#5] Required by some network tools
    build-essential     # [#6] Required for compiling Python C extensions
)

FAILED_INSTALLS=()

for tool in "${CORE_TOOLS[@]}"; do
    if dpkg -l "$tool" &>/dev/null 2>&1; then
        log_ok "$tool already installed"
    else
        if sudo apt install -y "$tool" 2>/dev/null; then
            log_ok "$tool installed"
        else
            log_warn "$tool failed to install (may not be in repos)"
            FAILED_INSTALLS+=("$tool")
        fi
    fi
done

# ── Go-based tools (some need manual install) [#7] ────────────────

log_info "Checking Go-based tools..."

install_go_tool() {
    local tool_name="$1"
    local install_cmd="$2"

    if command -v "$tool_name" &>/dev/null; then
        log_ok "$tool_name already installed"
        return 0
    fi

    log_info "Installing $tool_name..."
    if eval "$install_cmd" 2>/dev/null; then
        log_ok "$tool_name installed"
    else
        log_warn "$tool_name failed to install"
        FAILED_INSTALLS+=("$tool_name")
    fi
}

# Go is required for some tools
if ! command -v go &>/dev/null; then
    log_info "Installing Go..."
    if sudo apt install -y golang-go 2>/dev/null; then
        log_ok "Go installed"
        export PATH=$PATH:/usr/local/go/bin:$(go env GOPATH)/bin
    else
        log_warn "Go installation failed — some tools may not install"
    fi
fi

# Subfinder and nuclei may need latest version via Go
if command -v go &>/dev/null; then
    install_go_tool "subfinder" \
        "go install -v github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest 2>&1"
    install_go_tool "nuclei" \
        "go install -v github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest 2>&1"
    install_go_tool "httpx" \
        "go install -v github.com/projectdiscovery/httpx/cmd/httpx@latest 2>&1"
    install_go_tool "dnsx" \
        "go install -v github.com/projectdiscovery/dnsx/cmd/dnsx@latest 2>&1"
    install_go_tool "katana" \
        "go install -v github.com/projectdiscovery/katana/cmd/katana@latest 2>&1"
    install_go_tool "naabu" \
        "go install -v github.com/projectdiscovery/naabu/v2/cmd/naabu@latest 2>&1"
    install_go_tool "interactsh-client" \
        "go install -v github.com/projectdiscovery/interactsh/cmd/interactsh-client@latest 2>&1"
fi

# ── Python tools ───────────────────────────────────────────────────

log_info "Installing Python security tools..."

PYTHON_TOOLS=(
    arjun
    paramspider
    uro
    waybackpy
    trufflehog
    dirsearch       # [#8] Also available as pip package
    pwntools
    impacket
    cloud_enum
)

# Use --break-system-packages only if supported [#9]
PIP_FLAGS="--break-system-packages"
if ! pip3 install --help 2>&1 | grep -q "break-system-packages"; then
    PIP_FLAGS=""
fi

for tool in "${PYTHON_TOOLS[@]}"; do
    if pip3 show "$tool" &>/dev/null 2>&1; then
        log_ok "$tool already installed"
    else
        if pip3 install $PIP_FLAGS "$tool" 2>/dev/null; then
            log_ok "$tool installed"
        else
            log_warn "$tool failed to install via pip"
            FAILED_INSTALLS+=("python:$tool")
        fi
    fi
done

# ── Nuclei templates ──────────────────────────────────────────────

log_info "Updating Nuclei templates..."
if command -v nuclei &>/dev/null; then
    nuclei -update-templates 2>/dev/null || log_warn "Nuclei template update failed (non-critical)"
    log_ok "Nuclei templates updated"
else
    log_warn "Nuclei not found — skipping template update"
fi

# ── Wordlists setup [#10] ─────────────────────────────────────────

log_info "Setting up wordlists..."

WORDLIST_DIR="/usr/share/wordlists"

if [ ! -f "$WORDLIST_DIR/seclists" ] && [ ! -d "$WORDLIST_DIR/seclists" ]; then
    log_info "Downloading SecLists wordlists..."
    if sudo apt install -y seclists 2>/dev/null; then
        log_ok "SecLists installed"
    else
        log_warn "SecLists not in repos — downloading manually..."
        sudo mkdir -p "$WORDLIST_DIR"
        if command -v git &>/dev/null; then
            sudo git clone --depth 1 https://github.com/danielmiessler/SecLists.git \
                "$WORDLIST_DIR/seclists" 2>/dev/null || log_warn "SecLists download failed"
        fi
    fi
else
    log_ok "SecLists already available"
fi

# ── Verify installations ──────────────────────────────────────────

log_info "Verifying installations..."
echo ""

CORE_VERIFY=(
    nmap sqlmap ffuf gobuster nuclei wpscan nikto hydra
    jq curl openssl whois dirb
)

GO_VERIFY=(
    subfinder httpx dnsx gospider katana naabu
)

PYTHON_VERIFY=(
    arjun paramspider uro waybackpy trufflehog
)

INSTALLED=0
MISSING=0

echo "── Core Tools ──"
for tool in "${CORE_VERIFY[@]}"; do
    if command -v "$tool" &>/dev/null || dpkg -l "$tool" &>/dev/null 2>&1; then
        echo -e "  ${GREEN}✓${NC} $tool"
        ((INSTALLED++))
    else
        echo -e "  ${RED}✗${NC} $tool NOT FOUND"
        ((MISSING++))
    fi
done

echo ""
echo "── Go Tools ──"
for tool in "${GO_VERIFY[@]}"; do
    if command -v "$tool" &>/dev/null; then
        echo -e "  ${GREEN}✓${NC} $tool"
        ((INSTALLED++))
    else
        echo -e "  ${RED}✗${NC} $tool NOT FOUND"
        ((MISSING++))
    fi
done

echo ""
echo "── Python Tools ──"
for tool in "${PYTHON_VERIFY[@]}"; do
    if pip3 show "$tool" &>/dev/null 2>&1 || command -v "$tool" &>/dev/null; then
        echo -e "  ${GREEN}✓${NC} $tool"
        ((INSTALLED++))
    else
        echo -e "  ${RED}✗${NC} $tool NOT FOUND"
        ((MISSING++))
    fi
done

# ── Summary ────────────────────────────────────────────────────────

echo ""
echo "════════════════════════════════════════"
echo -e "  Installed: ${GREEN}$INSTALLED${NC}"
echo -e "  Missing:   ${RED}$MISSING${NC}"

if [ ${#FAILED_INSTALLS[@]} -gt 0 ]; then
    echo ""
    log_warn "Failed installs:"
    for f in "${FAILED_INSTALLS[@]}"; do
        echo "    - $f"
    done
fi

if [ "$MISSING" -eq 0 ]; then
    echo ""
    log_ok "All tools installed successfully!"
    echo "FRIDAY's security toolkit is ready."
else
    echo ""
    log_warn "Some tools are missing. Check errors above and retry."
    echo "You can re-run this script safely — it skips already installed tools."
fi

echo "════════════════════════════════════════"
