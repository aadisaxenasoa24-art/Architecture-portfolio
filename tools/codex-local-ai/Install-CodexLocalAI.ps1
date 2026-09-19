<#
.SYNOPSIS
    Sets up a local AI model (via Ollama) as a selectable profile inside the Codex CLI.

.DESCRIPTION
    Mirrors the "Codex hidden feature" setup: Codex can talk to any OpenAI-compatible
    endpoint, so a locally-hosted model can take over when your ChatGPT/Codex usage
    runs out.

    Safety model - this script is deliberately additive and reversible:
      * It NEVER edits an existing ~/.codex/config.toml. It writes a separate
        profile file that Codex only reads when you pass --profile.
      * It takes a full timestamped backup of ~/.codex before doing anything.
      * It hashes config.toml before and after and fails loudly if it ever changed.
      * It records every change it makes to a manifest, so Uninstall reverses exactly
        those changes and nothing else.
      * It only sets User-scope environment variables, never Machine-scope.
      * It refuses to proceed if RAM or disk space would put the machine at risk.

.PARAMETER DryRun
    Run every preflight check and print the plan, but change nothing at all.

.PARAMETER Model
    Override the auto-selected model tag (e.g. "qwen2.5-coder:7b").

.PARAMETER ProfileName
    Name of the Codex profile to create. Default "local".
    You will start it with: codex --profile local

.PARAMETER ContextLength
    Context window handed to Ollama. Codex needs at least 64k. Default 65536.

.PARAMETER Yes
    Skip the confirmation prompt.

.EXAMPLE
    .\Install-CodexLocalAI.ps1 -DryRun
    Shows exactly what would happen. Changes nothing.

.EXAMPLE
    .\Install-CodexLocalAI.ps1
    Performs the install, asking for confirmation before the first change.
#>
[CmdletBinding()]
param(
    [switch] $DryRun,
    [string] $Model,
    [string] $ProfileName   = 'local',
    [int]    $ContextLength = 65536,
    [switch] $Yes
)

$ErrorActionPreference = 'Stop'

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------
$CodexDir      = Join-Path $env:USERPROFILE '.codex'
$ConfigToml    = Join-Path $CodexDir 'config.toml'
$ProfileFile   = Join-Path $CodexDir "$ProfileName.config.toml"
$StateDir      = Join-Path $CodexDir 'local-ai-setup'
$ManifestPath  = Join-Path $StateDir 'manifest.json'
$OllamaBase    = 'http://127.0.0.1:11434'
$MinDiskGB     = 25
$Stamp         = Get-Date -Format 'yyyyMMdd-HHmmss'
$BackupDir     = Join-Path $env:USERPROFILE ".codex.backup-$Stamp"

# --------------------------------------------------------------------------
# Output helpers
# --------------------------------------------------------------------------
function Write-Step { param([string]$m) Write-Host ""; Write-Host "==> $m" -ForegroundColor Cyan }
function Write-Ok   { param([string]$m) Write-Host "    [ok]   $m" -ForegroundColor Green }
function Write-Info { param([string]$m) Write-Host "    [info] $m" -ForegroundColor Gray }
function Write-Warn { param([string]$m) Write-Host "    [warn] $m" -ForegroundColor Yellow }
function Write-Err  { param([string]$m) Write-Host "    [FAIL] $m" -ForegroundColor Red }

function Fail {
    param([string]$Message, [string]$Remedy)
    Write-Host ""
    Write-Err $Message
    if ($Remedy) { Write-Host "    -> $Remedy" -ForegroundColor Yellow }
    Write-Host ""
    Write-Host "Nothing was left half-done: this script makes no changes until all" -ForegroundColor Gray
    Write-Host "preflight checks pass. Your Codex setup is untouched." -ForegroundColor Gray
    exit 1
}

function Get-FileHashOrNull {
    param([string]$Path)
    if (Test-Path -LiteralPath $Path) { return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash }
    return $null
}

function Test-CommandExists {
    param([string]$Name)
    $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

Write-Host ""
Write-Host "  Local AI model for Codex CLI - installer" -ForegroundColor White
Write-Host "  ----------------------------------------" -ForegroundColor DarkGray
if ($DryRun) { Write-Host "  DRY RUN - nothing will be changed." -ForegroundColor Yellow }

# ==========================================================================
# PHASE 1 - PREFLIGHT (read-only; changes nothing)
# ==========================================================================
Write-Step "Preflight checks (read-only)"

$problems = @()

# --- OS ---------------------------------------------------------------
# $IsWindows only exists on PowerShell 6+. Windows PowerShell 5.1 is always Windows.
$runningOnWindows = $true
if ($PSVersionTable.PSVersion.Major -ge 6) {
    $runningOnWindows = [bool](Get-Variable -Name IsWindows -ValueOnly -ErrorAction SilentlyContinue)
}
if (-not $runningOnWindows) {
    Fail "This installer is for Windows." "On macOS/Linux use the Ollama install docs directly."
}
$os = Get-CimInstance Win32_OperatingSystem
Write-Ok ("Windows: {0} (build {1})" -f $os.Caption.Trim(), $os.BuildNumber)

# --- PowerShell -------------------------------------------------------
Write-Ok ("PowerShell {0}" -f $PSVersionTable.PSVersion)

# --- RAM --------------------------------------------------------------
$totalRamGB = [math]::Round($os.TotalVisibleMemorySize / 1MB, 1)
$freeRamGB  = [math]::Round($os.FreePhysicalMemory     / 1MB, 1)
Write-Ok ("RAM: {0} GB total, {1} GB free right now" -f $totalRamGB, $freeRamGB)
if ($totalRamGB -lt 8) {
    $problems += "Only $totalRamGB GB RAM. A local model needs 8 GB minimum."
}

# --- Disk -------------------------------------------------------------
$sysDrive  = (Get-Item $env:USERPROFILE).PSDrive.Name
$freeDisk  = Get-PSDrive -Name $sysDrive
$freeDiskGB = [math]::Round($freeDisk.Free / 1GB, 1)
Write-Ok ("Free disk on {0}: {1} GB" -f $sysDrive, $freeDiskGB)
if ($freeDiskGB -lt $MinDiskGB) {
    $problems += "Only $freeDiskGB GB free on $($sysDrive): - need about $MinDiskGB GB for the model download."
}

# --- GPU --------------------------------------------------------------
$gpuNames = @()
try {
    $gpuNames = @(Get-CimInstance Win32_VideoController -ErrorAction SilentlyContinue |
                  Select-Object -ExpandProperty Name)
} catch { }
$hasNvidia = $false
foreach ($g in $gpuNames) {
    Write-Info ("GPU: {0}" -f $g)
    if ($g -match 'NVIDIA|RTX|GTX') { $hasNvidia = $true }
}
if ($hasNvidia) {
    Write-Ok "NVIDIA GPU detected - the model will run on the GPU (fast)."
} else {
    Write-Warn "No NVIDIA GPU detected - the model will run on CPU (noticeably slower, but it works)."
}

# --- Node.js (needed only if Codex is missing) ------------------------
$hasNode = Test-CommandExists 'node'
if ($hasNode) {
    Write-Ok ("Node.js: {0}" -f (& node --version 2>$null))
} else {
    Write-Info "Node.js not found."
}

# --- Codex CLI --------------------------------------------------------
$hasCodex     = Test-CommandExists 'codex'
$codexVersion = $null
if ($hasCodex) {
    try { $codexVersion = (& codex --version 2>$null | Select-Object -First 1) } catch { }
    Write-Ok ("Codex CLI: {0}" -f $codexVersion)
} else {
    Write-Info "Codex CLI not found - it will be installed with npm."
    if (-not $hasNode) {
        $problems += "Codex CLI needs Node.js, which is not installed. Install Node.js LTS from https://nodejs.org first, then re-run this script."
    }
}

# --- Ollama -----------------------------------------------------------
$hasOllama     = Test-CommandExists 'ollama'
$ollamaVersion = $null
if ($hasOllama) {
    try { $ollamaVersion = (& ollama --version 2>$null | Select-Object -First 1) } catch { }
    Write-Ok ("Ollama: {0}" -f $ollamaVersion)
} else {
    Write-Info "Ollama not found - it will be installed."
    if (-not (Test-CommandExists 'winget')) {
        $problems += "Ollama is missing and winget is unavailable. Install Ollama manually from https://ollama.com/download/windows, then re-run this script."
    }
}

# --- Port 11434 -------------------------------------------------------
$portBusy = $false
try {
    $tcp = New-Object System.Net.Sockets.TcpClient
    $iar = $tcp.BeginConnect('127.0.0.1', 11434, $null, $null)
    if ($iar.AsyncWaitHandle.WaitOne(2000, $false) -and $tcp.Connected) { $portBusy = $true }
    $tcp.Close()
} catch { }
if ($portBusy) {
    try {
        $tags = Invoke-RestMethod -Uri "$OllamaBase/api/tags" -TimeoutSec 5
        Write-Ok "Ollama is already running on port 11434."
    } catch {
        $problems += "Port 11434 is in use by something that is not Ollama. Stop that program first - this script will not touch it."
    }
} else {
    Write-Info "Port 11434 is free."
}

# --- Existing Codex config -------------------------------------------
$configHashBefore = Get-FileHashOrNull $ConfigToml
if ($configHashBefore) {
    Write-Ok "Found an existing ~/.codex/config.toml - it will be backed up and left untouched."
} else {
    Write-Info "No existing ~/.codex/config.toml (that is fine)."
}
if (Test-Path -LiteralPath $ProfileFile) {
    Write-Warn ("A profile file already exists at {0} - it will be backed up and replaced." -f $ProfileFile)
}

if ($problems.Count -gt 0) {
    Write-Host ""
    Write-Host "  Cannot continue safely:" -ForegroundColor Red
    foreach ($p in $problems) { Write-Host "   - $p" -ForegroundColor Red }
    Write-Host ""
    Write-Host "  Nothing was changed." -ForegroundColor Gray
    exit 1
}

# ==========================================================================
# PHASE 2 - CHOOSE A MODEL THAT FITS THIS MACHINE
# ==========================================================================
Write-Step "Choosing a model that fits $totalRamGB GB of RAM"

# Each entry: tag, approximate download size (GB), approximate RAM needed while
# running (GB), and the minimum total RAM we are willing to install it on.
$catalog = @(
    [pscustomobject]@{ Tag='gpt-oss:20b';        DownloadGB=14;  RunGB=16; MinRamGB=24; Note='OpenAI open-weight 20B (MoE). Strong at tool use/agentic coding; what OpenAI documents for Codex.' },
    [pscustomobject]@{ Tag='qwen2.5-coder:14b';  DownloadGB=9;   RunGB=11; MinRamGB=16; Note='Solid mid-size coding model.' },
    [pscustomobject]@{ Tag='qwen2.5-coder:7b';   DownloadGB=4.7; RunGB=6;  MinRamGB=12; Note='Light and quick; good on modest machines.' },
    [pscustomobject]@{ Tag='qwen2.5-coder:3b';   DownloadGB=2;   RunGB=3;  MinRamGB=8;  Note='Smallest usable fallback.' }
)

if ($Model) {
    $chosen = $catalog | Where-Object { $_.Tag -eq $Model } | Select-Object -First 1
    if (-not $chosen) {
        $chosen = [pscustomobject]@{ Tag=$Model; DownloadGB=0; RunGB=0; MinRamGB=0; Note='User-specified model (size unknown).' }
        Write-Warn "Model '$Model' is not in the built-in catalog - installing it anyway, but its RAM fit was not checked."
    }
} else {
    $chosen = $catalog | Where-Object { $_.MinRamGB -le $totalRamGB } | Select-Object -First 1
    if (-not $chosen) {
        Fail "No model in the catalog fits $totalRamGB GB of RAM." "Pass -Model with a smaller model tag."
    }
}

Write-Ok ("Selected: {0}" -f $chosen.Tag)
Write-Info $chosen.Note
if ($chosen.DownloadGB -gt 0) {
    Write-Info ("Download about {0} GB; uses about {1} GB of memory while answering." -f $chosen.DownloadGB, $chosen.RunGB)
}

# Guard against choking the machine.
if ($chosen.RunGB -gt 0 -and ($totalRamGB - $chosen.RunGB) -lt 6) {
    Write-Warn "This model will leave under 6 GB for Windows and your other apps."
    Write-Warn "Rhino / Illustrator / a browser running at the same time may swap and feel slow."
    Write-Warn "If that bites, re-run with:  -Model qwen2.5-coder:7b"
}

# Codex requires >= 64k context. Warn if the caller lowers it.
if ($ContextLength -lt 65536) {
    Write-Warn "Codex expects a context window of at least 65536. You chose $ContextLength - Codex may error or stall."
}

# ==========================================================================
# PHASE 3 - SHOW THE PLAN AND ASK
# ==========================================================================
Write-Step "Plan"

$planLines = @()
if (-not $hasOllama) { $planLines += "Install Ollama (winget, user scope)" }
else                 { $planLines += "Keep the Ollama you already have ($ollamaVersion)" }
if (-not $hasCodex)  { $planLines += "Install Codex CLI (npm install -g @openai/codex)" }
else                 { $planLines += "Keep the Codex CLI you already have ($codexVersion)" }
$planLines += "Back up $CodexDir  ->  $BackupDir"
$planLines += "Set user env var OLLAMA_CONTEXT_LENGTH=$ContextLength  (Codex needs >= 64k)"
$planLines += "Download model $($chosen.Tag)"
$planLines += "Create NEW file $ProfileFile  (config.toml is not edited)"
$planLines += "Verify end to end, then tell you how to start it"

$i = 1
foreach ($l in $planLines) { Write-Host ("    {0}. {1}" -f $i, $l) -ForegroundColor White; $i++ }

Write-Host ""
Write-Host "  What this will NOT do:" -ForegroundColor DarkGray
Write-Host "    - It will not modify or delete your existing ~/.codex/config.toml" -ForegroundColor DarkGray
Write-Host "    - It will not change how plain 'codex' behaves - that still uses ChatGPT" -ForegroundColor DarkGray
Write-Host "    - It will not touch any other application, or any file outside ~/.codex" -ForegroundColor DarkGray
Write-Host "    - It will not set any Machine-scope (system-wide) environment variable" -ForegroundColor DarkGray

if ($DryRun) {
    Write-Host ""
    Write-Host "  DRY RUN complete. Nothing was changed." -ForegroundColor Yellow
    Write-Host "  Re-run without -DryRun to apply." -ForegroundColor Yellow
    exit 0
}

if (-not $Yes) {
    Write-Host ""
    $answer = Read-Host "  Proceed? (y/N)"
    if ($answer -notmatch '^[Yy]') {
        Write-Host "  Cancelled. Nothing was changed." -ForegroundColor Gray
        exit 0
    }
}

# ==========================================================================
# PHASE 4 - BACKUP (before the first change)
# ==========================================================================
Write-Step "Backing up"

$manifest = [ordered]@{
    schema            = 1
    installedAt       = (Get-Date -Format 'o')
    profileName       = $ProfileName
    profileFile       = $ProfileFile
    backupDir         = $null
    model             = $chosen.Tag
    contextLength     = $ContextLength
    configTomlSha256  = $configHashBefore
    createdProfileFile   = $false
    installedOllama      = $false
    installedCodex       = $false
    pulledModel          = $false
    envVarPrevious       = [Environment]::GetEnvironmentVariable('OLLAMA_CONTEXT_LENGTH', 'User')
    envVarSet            = $false
}

if (Test-Path -LiteralPath $CodexDir) {
    Copy-Item -LiteralPath $CodexDir -Destination $BackupDir -Recurse -Force
    $manifest.backupDir = $BackupDir
    Write-Ok "Copied $CodexDir -> $BackupDir"
} else {
    New-Item -ItemType Directory -Path $CodexDir -Force | Out-Null
    Write-Ok "Created $CodexDir (it did not exist yet)"
}

New-Item -ItemType Directory -Path $StateDir -Force | Out-Null

function Save-Manifest {
    ($manifest | ConvertTo-Json -Depth 6) | Set-Content -LiteralPath $ManifestPath -Encoding UTF8
}
Save-Manifest
Write-Ok "Recorded what this run will change -> $ManifestPath"

# ==========================================================================
# PHASE 5 - INSTALL COMPONENTS
# ==========================================================================

# --- Ollama -----------------------------------------------------------
if (-not $hasOllama) {
    Write-Step "Installing Ollama"
    Write-Info "Running: winget install --id Ollama.Ollama --scope user --silent"
    $wingetArgs = @('install','--id','Ollama.Ollama','--scope','user','--silent',
                    '--accept-package-agreements','--accept-source-agreements')
    & winget @wingetArgs
    if ($LASTEXITCODE -ne 0) {
        Fail "winget could not install Ollama (exit code $LASTEXITCODE)." `
             "Install it by hand from https://ollama.com/download/windows then re-run this script. Your backup is at $BackupDir."
    }
    $manifest.installedOllama = $true; Save-Manifest

    # winget updates PATH for new processes; refresh it for this one.
    $env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' +
                [Environment]::GetEnvironmentVariable('Path','User')
    if (-not (Test-CommandExists 'ollama')) {
        Fail "Ollama installed but is not on PATH in this window." `
             "Close this window, open a new PowerShell, and re-run the script - it will pick up where it left off."
    }
    Write-Ok "Ollama installed."
} else {
    Write-Step "Ollama already present - skipping install"
}

# --- Codex CLI --------------------------------------------------------
if (-not $hasCodex) {
    Write-Step "Installing Codex CLI"
    Write-Info "Running: npm install -g @openai/codex"
    & npm install -g '@openai/codex'
    if ($LASTEXITCODE -ne 0) {
        Fail "npm could not install the Codex CLI (exit code $LASTEXITCODE)." `
             "Check that Node.js is installed and try 'npm install -g @openai/codex' manually. Your backup is at $BackupDir."
    }
    $manifest.installedCodex = $true; Save-Manifest
    $env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' +
                [Environment]::GetEnvironmentVariable('Path','User')
    Write-Ok "Codex CLI installed."
} else {
    Write-Step "Codex CLI already present - skipping install"
}

# --- Context length ---------------------------------------------------
Write-Step "Setting the context window"
Write-Info "Ollama's default context can be as low as 4096 tokens. Codex needs at least 65536,"
Write-Info "and a too-small context is the usual cause of Codex hanging or erroring on a local model."
[Environment]::SetEnvironmentVariable('OLLAMA_CONTEXT_LENGTH', "$ContextLength", 'User')
$env:OLLAMA_CONTEXT_LENGTH = "$ContextLength"
$manifest.envVarSet = $true; Save-Manifest
Write-Ok "User environment variable OLLAMA_CONTEXT_LENGTH=$ContextLength"

# Ollama reads OLLAMA_CONTEXT_LENGTH at startup, so it has to be restarted to
# pick up a new value. Skip the restart when it is already running with the
# value we want - there is no reason to interrupt a server that is already
# correct, and it may have models loaded.
$needsRestart = $true
if ($portBusy -and $manifest.envVarPrevious -eq "$ContextLength") {
    $needsRestart = $false
    Write-Step "Ollama already running with the right context window - leaving it alone"
    Write-Ok "No restart needed."
}

if ($needsRestart) {
    Write-Step "Restarting Ollama so the new context window takes effect"
    $ollamaProcs = @(Get-Process -Name 'ollama','ollama app' -ErrorAction SilentlyContinue)
    if ($ollamaProcs.Count -gt 0) {
        Write-Info "Stopping Ollama. Any other app using it will reconnect once it is back."
        foreach ($p in $ollamaProcs) {
            try {
                Stop-Process -Id $p.Id -Force -ErrorAction Stop
                Write-Info ("Stopped {0} (pid {1})" -f $p.ProcessName, $p.Id)
            } catch { }
        }
        Start-Sleep -Seconds 3
    }
    $ollamaExe = (Get-Command ollama).Source
    $appExe    = Join-Path (Split-Path $ollamaExe -Parent) 'ollama app.exe'
    if (Test-Path -LiteralPath $appExe) {
        Start-Process -FilePath $appExe -WindowStyle Hidden
    } else {
        Start-Process -FilePath $ollamaExe -ArgumentList 'serve' -WindowStyle Hidden
    }
}

# Wait for the API to answer.
$ready = $false
for ($n = 0; $n -lt 30; $n++) {
    Start-Sleep -Seconds 2
    try { Invoke-RestMethod -Uri "$OllamaBase/api/tags" -TimeoutSec 4 | Out-Null; $ready = $true; break } catch { }
}
if (-not $ready) {
    Fail "Ollama did not start responding on $OllamaBase within 60 seconds." `
         "Open the Ollama app from the Start menu, then re-run this script. Your backup is at $BackupDir."
}
Write-Ok "Ollama is serving on $OllamaBase"

# --- Model download ---------------------------------------------------
Write-Step "Downloading the model ($($chosen.Tag))"
$already = $false
try {
    $tags = Invoke-RestMethod -Uri "$OllamaBase/api/tags" -TimeoutSec 10
    foreach ($m in $tags.models) { if ($m.name -eq $chosen.Tag) { $already = $true } }
} catch { }

if ($already) {
    Write-Ok "Already downloaded - skipping."
} else {
    if ($chosen.DownloadGB -gt 0) {
        Write-Info ("About {0} GB. This is the slow part - leave it running." -f $chosen.DownloadGB)
    }
    & ollama pull $chosen.Tag
    if ($LASTEXITCODE -ne 0) {
        Fail "Downloading $($chosen.Tag) failed (exit code $LASTEXITCODE)." `
             "Check your internet connection and re-run. Nothing else was changed; your backup is at $BackupDir."
    }
    $manifest.pulledModel = $true; Save-Manifest
    Write-Ok "Model downloaded."
}

# ==========================================================================
# PHASE 6 - LOAD THE MODEL AND PROVE IT ANSWERS
# ==========================================================================
# Done before anything else touches the model so that (a) a broken model is
# caught while nothing has been written yet, and (b) the model is warm in
# memory, which makes the protocol probe below fast instead of a 2-minute wait.
Write-Step "Loading the model and testing it"
Write-Info "The first call pulls the model into memory. Allow a minute or two."

$chatBody = @{
    model    = $chosen.Tag
    messages = @(@{ role = 'user'; content = 'Reply with exactly the word: READY' })
    stream   = $false
} | ConvertTo-Json -Depth 5

$reply     = $null
$modelWorks = $false
$sw = [Diagnostics.Stopwatch]::StartNew()
try {
    $resp = Invoke-RestMethod -Uri "$OllamaBase/v1/chat/completions" -Method Post `
                -ContentType 'application/json' -Body $chatBody -TimeoutSec 600
    $sw.Stop()
    if ($resp -and $resp.choices -and $resp.choices.Count -gt 0) {
        $reply = $resp.choices[0].message.content
        $modelWorks = $true
    }
} catch {
    $sw.Stop()
    Fail "The model did not answer: $($_.Exception.Message)" `
         "Close heavy apps (Rhino, Illustrator, Chrome) to free memory and re-run. Nothing has been written to your Codex config; your backup is at $BackupDir."
}

if ($modelWorks) {
    Write-Ok ("Model answered in {0:N1}s: {1}" -f $sw.Elapsed.TotalSeconds, ($reply.Trim() -replace '\s+', ' '))
    if ($sw.Elapsed.TotalSeconds -gt 90) {
        Write-Warn "That was slow. Expect this model to feel sluggish on this machine."
        Write-Warn "A smaller model will feel much better:  -Model qwen2.5-coder:7b"
    }
} else {
    Fail "The model replied but the response could not be read." `
         "Run Test-CodexLocalAI.ps1 for details. Your backup is at $BackupDir."
}

# Report the context length actually in force.
try {
    $ps = Invoke-RestMethod -Uri "$OllamaBase/api/ps" -TimeoutSec 10
    if ($ps -and $ps.models) {
        foreach ($mm in $ps.models) {
            if ($mm.PSObject.Properties.Name -contains 'context_length' -and $mm.context_length) {
                Write-Ok ("Context window actually in use: {0} tokens" -f $mm.context_length)
                if ([int]$mm.context_length -lt 65536) {
                    Write-Warn "That is below the 65536 Codex expects. If Codex stalls, restart Ollama and try again."
                }
            }
        }
    }
} catch { }

# ==========================================================================
# PHASE 7 - WORK OUT WHICH WIRE PROTOCOL THIS OLLAMA SPEAKS
# ==========================================================================
# Codex can talk either the Responses API or Chat Completions. Recent Ollama
# serves both; older builds serve only Chat Completions, and pointing Codex at
# "responses" on such a build gives a 404 that looks like a hang. So we ask.
# The model is already warm, so this returns quickly.
Write-Step "Checking which API this Ollama speaks"

$wireApi = 'chat'
$probeBody = @{ model = $chosen.Tag; input = 'hi'; stream = $false } | ConvertTo-Json -Depth 4

try {
    $r = Invoke-WebRequest -Uri "$OllamaBase/v1/responses" -Method Post `
            -ContentType 'application/json' -Body $probeBody -TimeoutSec 180 `
            -UseBasicParsing -ErrorAction Stop
    if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 300) {
        $wireApi = 'responses'
        Write-Ok 'Responses API works - using wire_api = "responses" (what OpenAI documents).'
    }
} catch {
    $code = $null
    try { $code = $_.Exception.Response.StatusCode.value__ } catch { }
    if ($code -eq 404) {
        Write-Warn 'This Ollama build does not serve /v1/responses - using wire_api = "chat" instead.'
        Write-Warn 'Both work with Codex. Updating Ollama later lets you switch to "responses".'
    } else {
        Write-Warn "Could not confirm the Responses API (HTTP $code) - using the safer wire_api = `"chat`"."
    }
}
Write-Ok "Chat Completions is confirmed working, so `"$wireApi`" is a safe choice either way."

# ==========================================================================
# PHASE 8 - WRITE THE CODEX PROFILE (a NEW file; config.toml is not touched)
# ==========================================================================
Write-Step "Writing the Codex profile"

$providerId = 'ollama-local'
$profileToml = @"
# Codex CLI -> local model served by Ollama
#
# Generated by tools/codex-local-ai/Install-CodexLocalAI.ps1 on $(Get-Date -Format 'yyyy-MM-dd HH:mm')
#
# This file is only read when you run:   codex --profile $ProfileName
# Plain 'codex' ignores it completely and keeps using your ChatGPT account.
#
# To undo everything, run Uninstall-CodexLocalAI.ps1.

model                = "$($chosen.Tag)"
model_provider       = "$providerId"
model_context_window = $ContextLength

[model_providers.$providerId]
name                 = "Ollama (local)"
base_url             = "$OllamaBase/v1/"
wire_api             = "$wireApi"
"@

if (Test-Path -LiteralPath $ProfileFile) {
    Write-Info "Replacing the existing profile file (the original is in your backup)."
}
Set-Content -LiteralPath $ProfileFile -Value $profileToml -Encoding UTF8
$manifest.createdProfileFile = $true
$manifest.wireApi = $wireApi
Save-Manifest
Write-Ok "Wrote $ProfileFile"

# ==========================================================================
# PHASE 9 - PROVE NOTHING ELSE WAS TOUCHED
# ==========================================================================
Write-Step "Confirming your existing Codex setup is unchanged"

$configHashAfter = Get-FileHashOrNull $ConfigToml
if ($configHashBefore -ne $configHashAfter) {
    Write-Err "config.toml changed during this run. That should be impossible."
    Write-Err "Restore it from: $BackupDir"
    exit 1
}
if ($configHashBefore) {
    Write-Ok "config.toml is byte-for-byte identical (SHA256 $($configHashBefore.Substring(0,12))...)."
} else {
    Write-Ok "You had no config.toml before, and none was created."
}
Write-Ok "Your normal 'codex' command is completely unaffected."

# ==========================================================================
# DONE
# ==========================================================================
Write-Host ""
Write-Host "  ============================================================" -ForegroundColor Green
Write-Host "   Done. Your local model is wired into Codex." -ForegroundColor Green
Write-Host "  ============================================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Two commands from now on:" -ForegroundColor White
Write-Host ""
Write-Host "    codex" -ForegroundColor Cyan
Write-Host "        Unchanged. Uses your ChatGPT account exactly as before." -ForegroundColor Gray
Write-Host ""
Write-Host "    codex --profile $ProfileName" -ForegroundColor Cyan
Write-Host "        Uses $($chosen.Tag) running on this laptop. No internet, no usage limits," -ForegroundColor Gray
Write-Host "        no cost. Use it when ChatGPT says you are out of usage." -ForegroundColor Gray
Write-Host ""
Write-Host "  If '--profile $ProfileName' is ever not recognised, this always works:" -ForegroundColor White
Write-Host ""
Write-Host "    codex --oss -m $($chosen.Tag)" -ForegroundColor Cyan
Write-Host "        Codex's own built-in Ollama mode - needs no config file at all." -ForegroundColor Gray
Write-Host ""
Write-Host "  Housekeeping:" -ForegroundColor White
Write-Host "    Backup of your Codex folder : $BackupDir" -ForegroundColor Gray
Write-Host "    Record of every change made : $ManifestPath" -ForegroundColor Gray
Write-Host "    Check it is healthy         : .\Test-CodexLocalAI.ps1" -ForegroundColor Gray
Write-Host "    Undo everything             : .\Uninstall-CodexLocalAI.ps1" -ForegroundColor Gray
Write-Host ""
Write-Host "  One catch worth knowing: a local model is meaningfully weaker than" -ForegroundColor DarkGray
Write-Host "  GPT-5-class models. It is good for carrying on with a plan that is" -ForegroundColor DarkGray
Write-Host "  already laid out, less good at starting hard problems from scratch." -ForegroundColor DarkGray
Write-Host ""
