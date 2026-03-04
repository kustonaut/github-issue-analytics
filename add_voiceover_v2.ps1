<#
.SYNOPSIS
  Generate TTS voiceover and merge with demo-video-v2 (MP4 or WebM).
  Uses Windows SAPI (System.Speech) + ffmpeg. No Python packages needed.
.DESCRIPTION
  v0.2.0 narration covering: hero, lifecycle funnel, heatmap, classic funnel,
  gauge, sparklines, KPIs, and feature highlights.
#>
param(
    [string]$VideoPath,
    [string]$OutputPath = "$PSScriptRoot\demo-video-v2-narrated.mp4"
)

$ErrorActionPreference = "Stop"

# Auto-detect video file
if (-not $VideoPath) {
    if (Test-Path "$PSScriptRoot\demo-video-v2.mp4") {
        $VideoPath = "$PSScriptRoot\demo-video-v2.mp4"
    } elseif (Test-Path "$PSScriptRoot\demo-video-v2.webm") {
        $VideoPath = "$PSScriptRoot\demo-video-v2.webm"
    } else {
        Write-Error "No demo video found. Run record_demo_v2.py first."
        exit 1
    }
}

# ── Voiceover script (v0.2.0 — timed to ~45s recording) ───────────
$NarrationText = @"
GitHub Issue Analytics, version 0.2.

Paste any public repository and get a full issue health dashboard in seconds, entirely in your browser.

Let's analyze Flask. The tool fetches all issues from the GitHub API and computes 13 metrics in real time.

Here's the System Health Score. One number from 0 to 100 that combines resolution rate, median age, and stale ratio.

New in version 0.2: the Lifecycle Funnel. Four stages, Intake, Triage, Active, and Closing, with drop-off percentages between each. That gap between Triage and Active? That's your bottleneck.

The classic funnel shows the filing-to-resolution flow. Label distribution and backlog age reveal what's piling up.

The enhanced heatmap now uses green, amber, and red severity coloring across 7 metrics per area. Instantly spot which labels are healthy and which need action.

Time series sparklines and KPI cards give you the trend at a glance.

GitHub Issue Analytics. pip install github-issue-analytics with the viz extra. One config file. Full dashboard. Try it live.
"@

$TempDir = $env:TEMP
$WavPath = Join-Path $TempDir "voiceover_v2.wav"
$Mp3Path = Join-Path $TempDir "voiceover_v2.mp3"

# ── Step 1: Generate WAV using Windows SAPI ───────────────────────
Write-Host "`n[1/3] Generating voiceover audio..." -ForegroundColor Cyan

Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer

# Pick a natural-sounding voice
$voices = $synth.GetInstalledVoices() | Where-Object { $_.Enabled }
Write-Host "  Available voices:"
foreach ($v in $voices) {
    $info = $v.VoiceInfo
    Write-Host "    - $($info.Name) ($($info.Gender), $($info.Culture))"
}

# Prefer David (male, US English) or Zira (female, US English)
$preferred = @("David", "Zira", "Mark", "Eva")
$selectedVoice = $null
foreach ($pref in $preferred) {
    $match = $voices | Where-Object { $_.VoiceInfo.Name -like "*$pref*" }
    if ($match) { $selectedVoice = $match[0].VoiceInfo.Name; break }
}
if ($selectedVoice) {
    $synth.SelectVoice($selectedVoice)
    Write-Host "  Selected voice: $selectedVoice" -ForegroundColor Green
} else {
    Write-Host "  Using default voice" -ForegroundColor Yellow
}

# Configure speech rate (-2 = slightly slower for clarity)
$synth.Rate = -1

# Save to WAV
$synth.SetOutputToWaveFile($WavPath)
$synth.Speak($NarrationText)
$synth.SetOutputToDefaultAudioDevice()
$synth.Dispose()

Write-Host "  WAV saved: $WavPath ($('{0:N1}' -f ((Get-Item $WavPath).Length / 1MB)) MB)"

# ── Step 2: Convert WAV to MP3 with ffmpeg ────────────────────────
Write-Host "`n[2/3] Converting to MP3..." -ForegroundColor Cyan

$ffmpeg = Get-Command ffmpeg -ErrorAction SilentlyContinue
if (-not $ffmpeg) {
    # Try static-ffmpeg from pip (python -c)
    $staticPath = & "C:\dev\venvs\brain-os\Scripts\python.exe" -c "
import static_ffmpeg, shutil
static_ffmpeg.add_paths()
print(shutil.which('ffmpeg') or '')
" 2>$null
    if ($staticPath -and (Test-Path $staticPath)) {
        $ffmpeg = $staticPath.Trim()
    }
}

if (-not $ffmpeg) {
    # Try common locations
    $ffmpegPaths = @(
        "$env:USERPROFILE\scoop\shims\ffmpeg.exe",
        "C:\ffmpeg\bin\ffmpeg.exe",
        "C:\dev\venvs\brain-os\Lib\site-packages\static_ffmpeg\bin\win32\ffmpeg.EXE"
    )
    foreach ($fp in $ffmpegPaths) {
        if (Test-Path $fp) { $ffmpeg = $fp; break }
    }
}

if (-not $ffmpeg) {
    Write-Error "ffmpeg not found! Install: pip install static-ffmpeg"
    exit 1
}

$ffmpegExe = if ($ffmpeg -is [string]) { $ffmpeg } else { $ffmpeg.Source }

& $ffmpegExe -y -i $WavPath -codec:a libmp3lame -qscale:a 4 $Mp3Path 2>&1 | Out-Null
Write-Host "  MP3 saved: $Mp3Path"

# ── Step 3: Merge video + audio ───────────────────────────────────
Write-Host "`n[3/3] Merging video + voiceover..." -ForegroundColor Cyan

# Get video duration
$videoDuration = & $ffmpegExe -i $VideoPath 2>&1 | Select-String "Duration" | ForEach-Object {
    if ($_ -match "Duration:\s*(\d+):(\d+):(\d+)\.(\d+)") {
        [int]$Matches[1]*3600 + [int]$Matches[2]*60 + [int]$Matches[3] + [int]$Matches[4]/100
    }
}
Write-Host "  Video duration: ${videoDuration}s"

# Merge: video + audio, use shortest stream
& $ffmpegExe -y `
    -i $VideoPath `
    -i $Mp3Path `
    -c:v libx264 -preset fast -crf 23 -pix_fmt yuv420p `
    -c:a aac -b:a 128k `
    -shortest `
    -movflags +faststart `
    $OutputPath 2>&1 | Out-Null

if (Test-Path $OutputPath) {
    $size = (Get-Item $OutputPath).Length / 1MB
    Write-Host "`n  Output: $OutputPath ($('{0:N1}' -f $size) MB)" -ForegroundColor Green
} else {
    Write-Error "Failed to create output video"
    exit 1
}

# Cleanup temp files
Remove-Item $WavPath -ErrorAction SilentlyContinue
Remove-Item $Mp3Path -ErrorAction SilentlyContinue

Write-Host "`nDone! Opening video..." -ForegroundColor Green
Start-Process $OutputPath
