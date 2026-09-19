<#
.SYNOPSIS
    Health check for the local-model-in-Codex setup. Read-only: changes nothing.

.DESCRIPTION
    Run this any time Codex feels slow, stuck, or wrong on the local profile.
    It checks each link in the chain in order and tells you which one is broken.
#>
[CmdletBinding()]
param(
    [string] $ProfileName = 'local'
)

$ErrorActionPreference = 'Continue'

$CodexDir     = Join-Path $env:USERPROFILE '.codex'
$ProfileFile  = Join-Path $CodexDir "$ProfileName.config.toml"
$ConfigToml   = Join-Path $CodexDir 'config.toml'
$ManifestPath = Join-Path $CodexDir 'local-ai-setup\manifest.json'
$OllamaBase   = 'http://127.0.0.1:11434'

function Write-Step { param([string]$m) Write-Host ""; Write-Host "==> $m" -ForegroundColor Cyan }
function Write-Ok   { param([string]$m) Write-Host "    [ok]   $m" -ForegroundColor Green }
function Write-Info { param([string]$m) Write-Host "    [info] $m" -ForegroundColor Gray }
function Write-Bad  { param([string]$m) Write-Host "    [BAD]  $m" -ForegroundColor Red }
function Write-Fix  { param([string]$m) Write-Host "           fix: $m" -ForegroundColor Yellow }

Write-Host ""
Write-Host "  Local AI model for Codex CLI - health check" -ForegroundColor White
Write-Host "  -------------------------------------------" -ForegroundColor DarkGray

$failures = 0

# 1. Codex CLI ---------------------------------------------------------
Write-Step "Codex CLI"
if (Get-Command codex -ErrorAction SilentlyContinue) {
    Write-Ok ("Installed: {0}" -f (& codex --version 2>$null | Select-Object -First 1))
} else {
    Write-Bad "Not on PATH."
    Write-Fix "npm install -g @openai/codex"
    $failures++
}

# 2. Ollama installed --------------------------------------------------
Write-Step "Ollama"
if (Get-Command ollama -ErrorAction SilentlyContinue) {
    Write-Ok ("Installed: {0}" -f (& ollama --version 2>$null | Select-Object -First 1))
} else {
    Write-Bad "Not on PATH."
    Write-Fix "Open the Ollama app once from the Start menu, then reopen PowerShell."
    $failures++
}

# 3. Ollama responding -------------------------------------------------
Write-Step "Ollama server on $OllamaBase"
$tags = $null
try {
    $tags = Invoke-RestMethod -Uri "$OllamaBase/api/tags" -TimeoutSec 8
    Write-Ok "Responding."
} catch {
    Write-Bad "Not responding: $($_.Exception.Message)"
    Write-Fix "Start Ollama from the Start menu, wait 10 seconds, run this again."
    $failures++
}

# 4. Context length ----------------------------------------------------
Write-Step "Context window"
$ctxUser = [Environment]::GetEnvironmentVariable('OLLAMA_CONTEXT_LENGTH', 'User')
if ([string]::IsNullOrEmpty($ctxUser)) {
    Write-Bad "OLLAMA_CONTEXT_LENGTH is not set."
    Write-Fix "This is the usual cause of Codex stalling. Re-run Install-CodexLocalAI.ps1."
    $failures++
} elseif ([int]$ctxUser -lt 65536) {
    Write-Bad "OLLAMA_CONTEXT_LENGTH is $ctxUser - Codex wants at least 65536."
    Write-Fix "Re-run the installer, or set it higher in Windows environment variables."
    $failures++
} else {
    Write-Ok "OLLAMA_CONTEXT_LENGTH = $ctxUser"
    if ($env:OLLAMA_CONTEXT_LENGTH -ne $ctxUser) {
        Write-Info "This PowerShell window predates that setting - Ollama itself has it, which is what matters."
    }
}

# 5. Profile file ------------------------------------------------------
Write-Step "Codex profile '$ProfileName'"
if (Test-Path -LiteralPath $ProfileFile) {
    Write-Ok "Found $ProfileFile"
    $modelLine = Select-String -LiteralPath $ProfileFile -Pattern '^\s*model\s*=' | Select-Object -First 1
    $wireLine  = Select-String -LiteralPath $ProfileFile -Pattern '^\s*wire_api\s*=' | Select-Object -First 1
    if ($modelLine) { Write-Info $modelLine.Line.Trim() }
    if ($wireLine)  { Write-Info $wireLine.Line.Trim() }
} else {
    Write-Bad "Missing $ProfileFile"
    Write-Fix "Re-run Install-CodexLocalAI.ps1  (or just use: codex --oss -m <model>)"
    $failures++
}

# 6. config.toml integrity --------------------------------------------
Write-Step "Your original Codex config"
if (Test-Path -LiteralPath $ManifestPath) {
    $mf = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
    $now = $null
    if (Test-Path -LiteralPath $ConfigToml) {
        $now = (Get-FileHash -LiteralPath $ConfigToml -Algorithm SHA256).Hash
    }
    if ($mf.configTomlSha256 -eq $now) {
        Write-Ok "config.toml is unchanged since the install - your ChatGPT setup is intact."
    } else {
        Write-Info "config.toml has changed since the install (by you or another tool, not by this setup)."
    }
} else {
    Write-Info "No install manifest - skipping this check."
}

# 7. Model present -----------------------------------------------------
Write-Step "Downloaded models"
if ($tags -and $tags.models) {
    foreach ($mm in $tags.models) {
        $sizeGB = [math]::Round($mm.size / 1GB, 1)
        Write-Ok ("{0}  ({1} GB)" -f $mm.name, $sizeGB)
    }
} else {
    Write-Bad "No models downloaded."
    Write-Fix "ollama pull gpt-oss:20b"
    $failures++
}

# 8. Live answer -------------------------------------------------------
Write-Step "Asking the model a question"
$modelTag = $null
if (Test-Path -LiteralPath $ManifestPath) {
    $modelTag = (Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json).model
}
if (-not $modelTag -and $tags -and $tags.models) { $modelTag = $tags.models[0].name }

if ($modelTag) {
    Write-Info "Model: $modelTag (first call loads it into memory - can take a minute)"
    $body = @{
        model    = $modelTag
        messages = @(@{ role='user'; content='Reply with exactly the word: READY' })
        stream   = $false
    } | ConvertTo-Json -Depth 5
    $sw = [Diagnostics.Stopwatch]::StartNew()
    try {
        $r = Invoke-RestMethod -Uri "$OllamaBase/v1/chat/completions" -Method Post `
                -ContentType 'application/json' -Body $body -TimeoutSec 300
        $sw.Stop()
        Write-Ok ("Replied in {0:N1}s: {1}" -f $sw.Elapsed.TotalSeconds, ($r.choices[0].message.content.Trim() -replace '\s+',' '))
    } catch {
        $sw.Stop()
        Write-Bad "No usable answer: $($_.Exception.Message)"
        Write-Fix "Close other heavy apps (Rhino, Illustrator) and try again - this is usually memory pressure."
        $failures++
    }
} else {
    Write-Bad "Could not work out which model to test."
    $failures++
}

# --- Verdict ----------------------------------------------------------
Write-Host ""
if ($failures -eq 0) {
    Write-Host "  ============================================================" -ForegroundColor Green
    Write-Host "   All good. Start it with:  codex --profile $ProfileName" -ForegroundColor Green
    Write-Host "  ============================================================" -ForegroundColor Green
} else {
    Write-Host "  ============================================================" -ForegroundColor Red
    Write-Host "   $failures problem(s) found - see the 'fix:' lines above." -ForegroundColor Red
    Write-Host "  ============================================================" -ForegroundColor Red
}
Write-Host ""
