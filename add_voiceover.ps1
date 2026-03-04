<#
.SYNOPSIS
  Generate TTS voiceover and merge with demo-video.mp4.
  Uses Windows SAPI (System.Speech) + ffmpeg. No Python packages needed.
#>
param(
    [string]$VideoPath = "$PSScriptRoot\demo-video.mp4",
    [string]$OutputPath = "$PSScriptRoot\demo-video-narrated.mp4"
)

$ErrorActionPreference = "Stop"

# ── Voiceover script (timed to 60s 2x-speed video) ───────────────
# The video shows: hero → repo input → fetch → SHS gauge → funnel → donut/age → heatmap → sparkline/KPIs → scroll top
# At 2x speed, each scene is roughly half the original timing.

$NarrationText = @"
GitHub Issue Analytics.
Paste any public repository and get a full health dashboard in seconds.

Let's analyze Pallets Flask, a repo with thousands of issues.

The tool fetches all issues via the GitHub API, computing 13 metrics in real time.

Here's the Stale Health Score — a single gauge from 0 to 100, combining resolution rate, median age, and stale ratio. One number tells you if your repo is healthy.

The issue funnel shows where issues get stuck. Open, In Progress, Resolved, Closed. That gap between Open and In Progress? That's your bottleneck.

Issue type distribution and age breakdown show what's piling up and how old the backlog really is.

The label heatmap reveals blind spots — which labels are graveyards where issues go in but never come out.

Time-series sparklines and KPI cards give you the trend at a glance. Is your repo getting healthier or worse?

GitHub Issue Analytics. One pip install. One config file. Full dashboard. Try it live at kustonaut dot github dot io.
"@

$TempDir = $env:TEMP
$WavPath = Join-Path $TempDir "voiceover.wav"
$Mp3Path = Join-Path $TempDir "voiceover.mp3"

# ── Step 1: Generate WAV using Windows SAPI ───────────────────────
Write-Host "`n[1/3] Generating voiceover audio..." -ForegroundColor Cyan

Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer

# Pick a natural-sounding voice (prefer David or Zira)
$voices = $synth.GetInstalledVoices() | Where-Object { $_.Enabled }
Write-Host "  Available voices:"
foreach ($v in $voices) {
    Write-Host "    - $($v.VoiceInfo.Name) ($($v.VoiceInfo.Culture))"
}

# Prefer David (male, clear) or Mark
$preferred = @("David", "Mark", "Zira")
$selectedVoice = $null
foreach ($pref in $preferred) {
    $match = $voices | Where-Object { $_.VoiceInfo.Name -like "*$pref*" } | Select-Object -First 1
    if ($match) {
        $selectedVoice = $match.VoiceInfo.Name
        break
    }
}
if (-not $selectedVoice) {
    $selectedVoice = $voices[0].VoiceInfo.Name
}
Write-Host "  Selected: $selectedVoice" -ForegroundColor Green

$synth.SelectVoice($selectedVoice)
$synth.Rate = 0        # 0 = normal speed (-10 to 10)
$synth.Volume = 100     # Max volume

$synth.SetOutputToWaveFile($WavPath)
$synth.Speak($NarrationText)
$synth.Dispose()

$wavSize = (Get-Item $WavPath).Length / 1MB
$wavMsg = "  WAV generated: $WavPath ({0:N1} MB)" -f $wavSize
Write-Host $wavMsg

# ── Step 2: Get audio duration and adjust speed to match video ────
Write-Host "`n[2/3] Matching audio to video duration..." -ForegroundColor Cyan

# Get video duration
$videoInfo = & ffprobe -v quiet -show_entries format=duration -of csv=p=0 $VideoPath 2>$null
$videoDur = [double]$videoInfo
Write-Host "  Video duration: $([math]::Round($videoDur, 1))s"

# Get audio duration
$audioInfo = & ffprobe -v quiet -show_entries format=duration -of csv=p=0 $WavPath 2>$null
$audioDur = [double]$audioInfo
Write-Host "  Audio duration: $([math]::Round($audioDur, 1))s"

# Calculate tempo adjustment (speed up/slow down audio to match video)
$tempo = $audioDur / $videoDur
Write-Host "  Tempo factor: $([math]::Round($tempo, 3))x"

if ($tempo -gt 2.0) {
    Write-Host "  ⚠ Audio is >2x longer than video. Will chain atempo filters." -ForegroundColor Yellow
    # ffmpeg atempo supports 0.5-2.0, chain for larger
    $filters = @()
    $remaining = $tempo
    while ($remaining -gt 2.0) {
        $filters += "atempo=2.0"
        $remaining = $remaining / 2.0
    }
    $filters += "atempo=$([math]::Round($remaining, 4))"
    $atempoChain = $filters -join ","
} else {
    $atempoChain = "atempo=$([math]::Round($tempo, 4))"
}
Write-Host "  Filter: $atempoChain"

# ── Step 3: Merge audio + video ───────────────────────────────────
Write-Host "`n[3/3] Merging narration with video..." -ForegroundColor Cyan

# First, create tempo-adjusted audio
$adjustedAudio = Join-Path $TempDir "voiceover_adjusted.mp3"
cmd /c "ffmpeg -y -i `"$WavPath`" -af $atempoChain -c:a libmp3lame -b:a 128k `"$adjustedAudio`" 2>NUL"
Write-Host "  Audio adjusted to $atempoChain"

# Then merge with video (video has no audio track, so just add)
cmd /c "ffmpeg -y -i `"$VideoPath`" -i `"$adjustedAudio`" -c:v copy -c:a aac -b:a 128k -map 0:v:0 -map 1:a:0 -shortest `"$OutputPath`" 2>NUL"
Write-Host "  Merge complete."

if (Test-Path $OutputPath) {
    $outSize = [math]::Round((Get-Item $OutputPath).Length / 1MB, 1)
    Write-Host "`n✅ Narrated video saved: $OutputPath" -ForegroundColor Green
    Write-Host "   Size: $outSize MB"
    
    # Cleanup temp files
    Remove-Item $WavPath -ErrorAction SilentlyContinue
    Remove-Item $adjustedAudio -ErrorAction SilentlyContinue
    Remove-Item $Mp3Path -ErrorAction SilentlyContinue
    
    # Open it
    Start-Process $OutputPath
} else {
    Write-Host "❌ Failed to create narrated video" -ForegroundColor Red
}
