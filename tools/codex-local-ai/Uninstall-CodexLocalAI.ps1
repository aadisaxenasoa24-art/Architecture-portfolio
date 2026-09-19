<#
.SYNOPSIS
    Reverses exactly what Install-CodexLocalAI.ps1 did, and nothing else.

.DESCRIPTION
    Reads the manifest written during install and undoes only the changes recorded
    there. Anything you had before the install is left alone.

    By default the downloaded model is KEPT (it is the slow part to re-download).
    Pass -RemoveModel to delete it too, and -RemoveOllama to uninstall Ollama.

.PARAMETER RemoveModel
    Also delete the downloaded model from Ollama, freeing its disk space.

.PARAMETER RemoveOllama
    Also uninstall Ollama itself - only if this script installed it.

.PARAMETER Yes
    Skip the confirmation prompt.
#>
[CmdletBinding()]
param(
    [switch] $RemoveModel,
    [switch] $RemoveOllama,
    [switch] $Yes
)

$ErrorActionPreference = 'Stop'

$CodexDir     = Join-Path $env:USERPROFILE '.codex'
$StateDir     = Join-Path $CodexDir 'local-ai-setup'
$ManifestPath = Join-Path $StateDir 'manifest.json'
$ConfigToml   = Join-Path $CodexDir 'config.toml'

function Write-Step { param([string]$m) Write-Host ""; Write-Host "==> $m" -ForegroundColor Cyan }
function Write-Ok   { param([string]$m) Write-Host "    [ok]   $m" -ForegroundColor Green }
function Write-Info { param([string]$m) Write-Host "    [info] $m" -ForegroundColor Gray }
function Write-Warn { param([string]$m) Write-Host "    [warn] $m" -ForegroundColor Yellow }

Write-Host ""
Write-Host "  Local AI model for Codex CLI - uninstaller" -ForegroundColor White
Write-Host "  ------------------------------------------" -ForegroundColor DarkGray

if (-not (Test-Path -LiteralPath $ManifestPath)) {
    Write-Host ""
    Write-Warn "No install manifest found at $ManifestPath"
    Write-Warn "Either this was never installed, or it was already removed."
    Write-Host ""
    Write-Host "  If you want to clean up by hand, the only things the installer ever creates are:" -ForegroundColor Gray
    Write-Host "    - a profile file    ~/.codex/<name>.config.toml" -ForegroundColor Gray
    Write-Host "    - a user env var    OLLAMA_CONTEXT_LENGTH" -ForegroundColor Gray
    Write-Host "    - a state folder    ~/.codex/local-ai-setup" -ForegroundColor Gray
    Write-Host ""
    exit 0
}

$m = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json

Write-Step "This will undo the install from $($m.installedAt)"
$actions = @()
if ($m.createdProfileFile) { $actions += "Delete the profile file  $($m.profileFile)" }
if ($m.envVarSet) {
    if ([string]::IsNullOrEmpty($m.envVarPrevious)) {
        $actions += "Remove the user env var OLLAMA_CONTEXT_LENGTH (it did not exist before)"
    } else {
        $actions += "Restore OLLAMA_CONTEXT_LENGTH to its previous value '$($m.envVarPrevious)'"
    }
}
$actions += "Delete the state folder  $StateDir"
if ($RemoveModel -and $m.pulledModel) { $actions += "Delete the model  $($m.model)" }
if ($RemoveOllama) {
    if ($m.installedOllama) { $actions += "Uninstall Ollama (this script installed it)" }
    else { Write-Warn "-RemoveOllama ignored: Ollama was already on this machine before the install." }
}

$i = 1
foreach ($a in $actions) { Write-Host ("    {0}. {1}" -f $i, $a) -ForegroundColor White; $i++ }

Write-Host ""
Write-Host "  Left alone:" -ForegroundColor DarkGray
Write-Host "    - your ~/.codex/config.toml (never edited in the first place)" -ForegroundColor DarkGray
Write-Host "    - the Codex CLI itself" -ForegroundColor DarkGray
if (-not $RemoveModel) { Write-Host "    - the downloaded model (pass -RemoveModel to delete it)" -ForegroundColor DarkGray }
if ($m.backupDir) { Write-Host "    - your backup at $($m.backupDir)" -ForegroundColor DarkGray }

if (-not $Yes) {
    Write-Host ""
    $answer = Read-Host "  Proceed? (y/N)"
    if ($answer -notmatch '^[Yy]') { Write-Host "  Cancelled. Nothing was changed." -ForegroundColor Gray; exit 0 }
}

# --- Check config.toml is still what it was ---------------------------
Write-Step "Verifying your config.toml was never touched"
$currentHash = $null
if (Test-Path -LiteralPath $ConfigToml) {
    $currentHash = (Get-FileHash -LiteralPath $ConfigToml -Algorithm SHA256).Hash
}
if ($m.configTomlSha256 -eq $currentHash) {
    Write-Ok "Unchanged since install, as expected."
} else {
    Write-Warn "config.toml differs from install time - you (or another tool) edited it since."
    Write-Warn "That is fine. This uninstaller will not touch it."
}

# --- Remove the profile file ------------------------------------------
if ($m.createdProfileFile -and (Test-Path -LiteralPath $m.profileFile)) {
    Write-Step "Removing the profile file"
    Remove-Item -LiteralPath $m.profileFile -Force
    Write-Ok "Deleted $($m.profileFile)"
}

# --- Restore the environment variable ---------------------------------
if ($m.envVarSet) {
    Write-Step "Restoring OLLAMA_CONTEXT_LENGTH"
    if ([string]::IsNullOrEmpty($m.envVarPrevious)) {
        [Environment]::SetEnvironmentVariable('OLLAMA_CONTEXT_LENGTH', $null, 'User')
        Write-Ok "Removed (it did not exist before the install)."
    } else {
        [Environment]::SetEnvironmentVariable('OLLAMA_CONTEXT_LENGTH', $m.envVarPrevious, 'User')
        Write-Ok "Set back to '$($m.envVarPrevious)'."
    }
}

# --- Remove the model -------------------------------------------------
if ($RemoveModel -and $m.pulledModel) {
    Write-Step "Deleting the model"
    try {
        & ollama rm $m.model
        Write-Ok "Deleted $($m.model)"
    } catch {
        Write-Warn "Could not delete the model: $($_.Exception.Message)"
    }
}

# --- Uninstall Ollama -------------------------------------------------
if ($RemoveOllama -and $m.installedOllama) {
    Write-Step "Uninstalling Ollama"
    try {
        & winget uninstall --id Ollama.Ollama --silent
        Write-Ok "Ollama uninstalled."
    } catch {
        Write-Warn "Could not uninstall Ollama automatically. Remove it from Settings > Apps."
    }
}

# --- Remove state -----------------------------------------------------
Write-Step "Removing the state folder"
Remove-Item -LiteralPath $StateDir -Recurse -Force
Write-Ok "Deleted $StateDir"

Write-Host ""
Write-Host "  ============================================================" -ForegroundColor Green
Write-Host "   Removed. 'codex' works exactly as it did before." -ForegroundColor Green
Write-Host "  ============================================================" -ForegroundColor Green
if ($m.backupDir) {
    Write-Host ""
    Write-Host "  Your pre-install backup is still at:" -ForegroundColor Gray
    Write-Host "    $($m.backupDir)" -ForegroundColor Gray
    Write-Host "  Delete it whenever you are satisfied nothing is missing." -ForegroundColor Gray
}
Write-Host ""
