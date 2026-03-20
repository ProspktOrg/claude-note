#Requires -Version 5.1
<#
.SYNOPSIS
    Claude Note Installer for Windows (PowerShell)

.DESCRIPTION
    Installs claude-note using uv for session logging with Claude Code.
    Creates Task Scheduler entries for worker and classifier.

.EXAMPLE
    .\install.ps1
#>

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

function Write-Step([string]$step, [string]$msg) {
    Write-Host "[$step] " -ForegroundColor Blue -NoNewline
    Write-Host $msg
}
function Write-Ok([string]$msg) {
    Write-Host "  [OK] " -ForegroundColor Green -NoNewline
    Write-Host $msg
}
function Write-Warn([string]$msg) {
    Write-Host "  [!] " -ForegroundColor Yellow -NoNewline
    Write-Host $msg
}
function Write-Err([string]$msg) {
    Write-Host "  [X] " -ForegroundColor Red -NoNewline
    Write-Host $msg
}

# Banner
Write-Host ""
Write-Host "   CLAUDE NOTE INSTALLER (Windows)" -ForegroundColor Cyan
Write-Host "   ================================" -ForegroundColor Cyan
Write-Host ""

# =============================================================================
# Preflight
# =============================================================================

Write-Step "1/10" "Checking requirements..."

# Check uv
if (Get-Command uv -ErrorAction SilentlyContinue) {
    $uvVer = (uv --version 2>$null) | Select-Object -First 1
    Write-Ok "uv found ($uvVer)"
} else {
    Write-Err "uv not found"
    $install = Read-Host "  Install uv now? [Y/n]"
    if ($install -ne 'n') {
        irm https://astral.sh/uv/install.ps1 | iex
        $uvBin = Join-Path $env:USERPROFILE ".local\bin"
        $env:PATH = "$uvBin;$env:PATH"
    } else {
        Write-Host "Install uv first: https://docs.astral.sh/uv/getting-started/installation/"
        exit 1
    }
}

# Check git
if (Get-Command git -ErrorAction SilentlyContinue) {
    Write-Ok "git found"
} else {
    Write-Err "git is required"
    exit 1
}

# Check Claude CLI
$claudeAvailable = $false
if (Get-Command claude -ErrorAction SilentlyContinue) {
    Write-Ok "Claude CLI found"
    $claudeAvailable = $true
} else {
    Write-Warn "Claude CLI not found (synthesis disabled)"
}

# =============================================================================
# Vault Path
# =============================================================================

Write-Host ""
Write-Step "2/10" "Configuring vault..."

$configDir = Join-Path $env:USERPROFILE ".config\claude-note"
$configFile = Join-Path $configDir "config.toml"
$vaultPath = ""

if (Test-Path $configFile) {
    $configContent = Get-Content $configFile -Raw
    if ($configContent -match 'vault_root\s*=\s*"([^"]+)"') {
        $existing = $Matches[1]
        Write-Host "  Found existing config: $existing"
        $use = Read-Host "  Use this vault? [Y/n]"
        if ($use -ne 'n') { $vaultPath = $existing }
    }
}

if (-not $vaultPath) {
    $default = Join-Path $env:USERPROFILE "Documents\claude-notes"
    $vaultPath = Read-Host "  Vault path [$default]"
    if (-not $vaultPath) { $vaultPath = $default }

    if (-not (Test-Path $vaultPath)) {
        $create = Read-Host "  Create directory? [Y/n]"
        if ($create -ne 'n') {
            New-Item -ItemType Directory -Path $vaultPath -Force | Out-Null
            Write-Ok "Created $vaultPath"
        } else {
            Write-Err "Vault directory required"
            exit 1
        }
    }
}

Write-Ok "Vault: $vaultPath"

# =============================================================================
# Install
# =============================================================================

Write-Host ""
Write-Step "3/10" "Installing claude-note..."

uv python install 3.11 --quiet 2>$null

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (Test-Path (Join-Path $scriptDir "pyproject.toml")) {
    uv tool install $scriptDir --python 3.11 --force --quiet
} else {
    $tempDir = Join-Path $env:TEMP "claude-note-install"
    if (Test-Path $tempDir) { Remove-Item -Recurse -Force $tempDir }
    git clone --quiet --depth 1 "https://github.com/artemiin/claude-note.git" $tempDir
    uv tool install $tempDir --python 3.11 --force --quiet
    Remove-Item -Recurse -Force $tempDir
}

Write-Ok "claude-note installed"

# =============================================================================
# Templates
# =============================================================================

Write-Host ""
Write-Step "4/10" "Setting up vault templates..."
Write-Host "  (run 'claude-note agents init' after install for v2 structure)"

# =============================================================================
# Configuration
# =============================================================================

Write-Host ""
Write-Step "5/10" "Writing configuration..."

New-Item -ItemType Directory -Path $configDir -Force | Out-Null

$synthMode = "log"
if ($claudeAvailable) { $synthMode = "route" }

$vaultPathForward = $vaultPath -replace '\\', '/'

$configContent = @"
# Claude Note Configuration

vault_root = "$vaultPathForward"

[synthesis]
mode = "$synthMode"
model = "claude-sonnet-4-5-20250929"

[agent]
enabled = false

[mycelium]
enabled = false

[gitnexus]
enabled = false
"@

# Write without BOM -- PS 5.1's -Encoding UTF8 adds BOM which breaks tomllib
[System.IO.File]::WriteAllText($configFile, $configContent, (New-Object System.Text.UTF8Encoding $false))
Write-Ok "Config at $configFile"

# =============================================================================
# Vault Structure
# =============================================================================

Write-Host ""
Write-Step "6/10" "Initializing vault structure..."

New-Item -ItemType Directory -Path (Join-Path $vaultPath ".claude-note\queue") -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $vaultPath ".claude-note\state") -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $vaultPath ".claude-note\logs") -Force | Out-Null

Write-Ok "Created .claude-note/ directories"

# =============================================================================
# Task Scheduler
# =============================================================================

Write-Host ""
Write-Step "7/10" "Setting up background worker..."

$claudeNoteBin = (Get-Command claude-note -ErrorAction SilentlyContinue).Source
if (-not $claudeNoteBin) {
    $claudeNoteBin = Join-Path $env:USERPROFILE ".local\bin\claude-note.exe"
}

try {
    $action = New-ScheduledTaskAction -Execute $claudeNoteBin -Argument "worker"
    $trigger = New-ScheduledTaskTrigger -AtLogon
    $taskSettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
    Register-ScheduledTask -TaskName "ClaudeNoteWorker" -Action $action -Trigger $trigger -Settings $taskSettings -Force | Out-Null
    Start-ScheduledTask -TaskName "ClaudeNoteWorker" -ErrorAction SilentlyContinue
    Write-Ok "Worker task created and started"
} catch {
    Write-Warn "Could not create scheduled task (may need admin): $_"
    Write-Host "  Run manually: claude-note worker"
}

# =============================================================================
# GitNexus (optional)
# =============================================================================

Write-Host ""
Write-Step "8/10" "GitNexus code intelligence (optional)..."

$setupGN = Read-Host "  Setup GitNexus code intelligence? [y/N]"
if ($setupGN -match '^[Yy]') {
    if (Get-Command npx -ErrorAction SilentlyContinue) {
        Write-Host "  Indexing repository with GitNexus..."
        & npx -y gitnexus@latest analyze --skills 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-Ok "Repository indexed with GitNexus"
        } else {
            Write-Warn "GitNexus indexing failed (is this a git repo?)"
        }
    } else {
        Write-Warn "npx not found. Install Node.js for GitNexus: https://nodejs.org/"
    }
} else {
    Write-Host "  Skipping. Run later: npx gitnexus analyze --skills"
}

# =============================================================================
# Install Claude Code Hooks
# =============================================================================

Write-Host ""
Write-Step "9/10" "Installing Claude Code hooks..."

$claudeDir = Join-Path $env:USERPROFILE ".claude"
$claudeSettings = Join-Path $claudeDir "settings.json"
New-Item -ItemType Directory -Path $claudeDir -Force | Out-Null

try {
    if (Test-Path $claudeSettings) {
        $settingsObj = Get-Content $claudeSettings -Raw | ConvertFrom-Json
    } else {
        $settingsObj = New-Object PSObject
    }

    $enqueueCmd = @{ type = "command"; command = "claude-note enqueue"; timeout = 5000 }
    $contextCmd = @{ type = "command"; command = "claude-note context"; timeout = 5000 }

    $enqueueOnly = @( @{ hooks = @( $enqueueCmd ) } )
    $enqueueAndContext = @( @{ hooks = @( $enqueueCmd, $contextCmd ) } )

    if (-not ($settingsObj | Get-Member -Name "hooks" -ErrorAction SilentlyContinue)) {
        $settingsObj | Add-Member -NotePropertyName "hooks" -NotePropertyValue (New-Object PSObject) -Force
    }

    $contextOnly = @( @{ hooks = @( $contextCmd ) } )

    $settingsObj.hooks | Add-Member -NotePropertyName "SessionStart" -NotePropertyValue $contextOnly -Force
    $settingsObj.hooks | Add-Member -NotePropertyName "PostToolUse" -NotePropertyValue $enqueueOnly -Force
    $settingsObj.hooks | Add-Member -NotePropertyName "UserPromptSubmit" -NotePropertyValue $enqueueOnly -Force
    $settingsObj.hooks | Add-Member -NotePropertyName "PostCompact" -NotePropertyValue $contextOnly -Force
    $settingsObj.hooks | Add-Member -NotePropertyName "Stop" -NotePropertyValue $enqueueOnly -Force

    $jsonOut = $settingsObj | ConvertTo-Json -Depth 10
    [System.IO.File]::WriteAllText($claudeSettings, $jsonOut, (New-Object System.Text.UTF8Encoding $false))
    Write-Ok "Hooks installed in $claudeSettings"
} catch {
    Write-Warn "Could not auto-install hooks: $_"
    Write-Host "  Add hooks manually to ~/.claude/settings.json"
}

# =============================================================================
# Skills
# =============================================================================

Write-Host ""
Write-Step "10/10" "Checking for skills..."
Write-Host "  (no local skills to install)"

# =============================================================================
# Done
# =============================================================================

Write-Host ""
Write-Host "  =========================================" -ForegroundColor Green
Write-Host "   INSTALLATION COMPLETE" -ForegroundColor Green
Write-Host "   claude-note is ready to capture" -ForegroundColor Green
Write-Host "   knowledge from your sessions" -ForegroundColor Green
Write-Host "  =========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Blue
Write-Host ""
Write-Host "1. Check status: claude-note status"
Write-Host "2. For multi-agent setup: claude-note agents init"
Write-Host ""
