param(
    [int]$BinMB = 3,
    [int]$Retry = 3
)
# One-command push for a slow uplink.
#
# Windows PowerShell 5.1 reads .ps1 as GBK unless there's a BOM, so every
# message in this file is ASCII on purpose -- no Chinese here.
#
# What it does:
#   1. If there are uncommitted changes, commits them in packs of <= BinMB.
#   2. If exactly one unpushed commit is bigger than BinMB, splits it up.
#   3. Pushes pack by pack, retrying a failed pack instead of starting over.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File tools\push.ps1
#   powershell -ExecutionPolicy Bypass -File tools\push.ps1 -BinMB 2

$ErrorActionPreference = 'Continue'
$Repo = Split-Path $PSScriptRoot -Parent
Set-Location $Repo
$BIN = $BinMB * 1MB

function Log($msg) {
    Write-Host ("[{0}] {1}" -f (Get-Date -Format 'HH:mm:ss'), $msg)
}

function Get-Changes {
    $list = @()
    git -c core.quotepath=false status --porcelain -uall | ForEach-Object {
        $p = $_.Substring(3).Trim('"')
        $size = 0
        if (Test-Path $p -PathType Leaf) { $size = (Get-Item $p).Length }
        $k = 'other'
        if ($p -match '^images/(\d{4}\.\d{2}\.\d{2})/w/') { $k = 'webp-' + $Matches[1] }
        elseif ($p -match '^images/(\d{4}\.\d{2}\.\d{2})/') { $k = 'jpg-' + $Matches[1] }
        $list += [pscustomobject]@{ Path = $p; Size = $size; Key = $k }
    }
    return $list
}

function New-Packs($changes) {
    $order = @($changes | Select-Object -ExpandProperty Key -Unique)
    # push the page itself last, so a mid-way deploy never points at missing files
    $order = @($order | Where-Object { $_ -ne 'other' }) + @('other')
    $packs = @()
    foreach ($k in $order) {
        $group = @($changes | Where-Object { $_.Key -eq $k } | Sort-Object Path)
        $buf = @(); $bytes = 0
        foreach ($e in $group) {
            if ($bytes + $e.Size -gt $BIN -and $buf.Count -gt 0) {
                $packs += , $buf; $buf = @(); $bytes = 0
            }
            $buf += $e; $bytes += $e.Size
        }
        if ($buf.Count -gt 0) { $packs += , $buf }
    }
    return $packs
}

function Push-WithRetry {
    param([string]$Label)
    for ($try = 1; $try -le $Retry; $try++) {
        $t0 = Get-Date
        $out = (git push --porcelain origin main 2>&1 | Out-String)
        if ($LASTEXITCODE -eq 0) {
            $sec = [math]::Round(((Get-Date) - $t0).TotalSeconds)
            Log ("  ok: " + $Label + " in " + $sec + "s")
            return $true
        }
        Log ("  failed (attempt " + $try + "/" + $Retry + "): " + $Label)
        $out.Trim().Split("`n") | Select-Object -Last 3 | ForEach-Object { Log ("    " + $_.Trim()) }
        if ($try -lt $Retry) { Start-Sleep -Seconds 5 }
    }
    return $false
}

# --- 1. commit whatever is not committed -------------------------------
$changes = @(Get-Changes)
if ($changes.Count -gt 0) {
    $mb = [math]::Round((($changes | Measure-Object Size -Sum).Sum / 1MB), 2)
    Log ("uncommitted: " + $changes.Count + " files, " + $mb + " MB")
    $packs = @(New-Packs $changes)
    Log ("split into " + $packs.Count + " pack(s)")
    $n = 0
    foreach ($pack in $packs) {
        $n++
        $size = [math]::Round((($pack | Measure-Object Size -Sum).Sum / 1MB), 2)
        $tag = $pack[0].Key
        foreach ($e in $pack) { git add -A -- $e.Path }
        git commit -q -m ("images " + $n + "/" + $packs.Count + " (" + $tag + ", " + $size + " MB)")
        if ($LASTEXITCODE -ne 0) { Log "commit failed"; exit 1 }
        Log ("committed pack " + $n + "/" + $packs.Count + " (" + $tag + ", " + $size + " MB)")
    }
}
else {
    Log "working tree clean"
}

# --- 2. if a single huge commit is waiting, split it -------------------
$ahead = [int](git rev-list --count origin/main..HEAD)
if ($ahead -eq 1) {
    $big = @(git -c core.quotepath=false diff-tree --no-commit-id --name-only -r HEAD)
    $sum = 0
    foreach ($p in $big) {
        $size = [int](git cat-file -s ("HEAD:" + $p) 2>$null)
        if ($size -gt 0) { $sum += $size }
    }
    if ($sum -gt $BIN) {
        Log ("single unpushed commit holds " + [math]::Round($sum / 1MB, 2) + " MB, splitting it")
        git reset --soft HEAD~1 | Out-Null
        git restore --staged . | Out-Null
        $changes = @(Get-Changes)
        $packs = @(New-Packs $changes)
        Log ("split into " + $packs.Count + " pack(s)")
        $n = 0
        foreach ($pack in $packs) {
            $n++
            $size = [math]::Round((($pack | Measure-Object Size -Sum).Sum / 1MB), 2)
            $tag = $pack[0].Key
            foreach ($e in $pack) { git add -A -- $e.Path }
            git commit -q -m ("images " + $n + "/" + $packs.Count + " (" + $tag + ", " + $size + " MB)")
            if ($LASTEXITCODE -ne 0) { Log "commit failed"; exit 1 }
        }
    }
}

# --- 3. push, one commit at a time, retrying the one that fails -------
$ahead = [int](git rev-list --count origin/main..HEAD)
Log ("commits to push: " + $ahead)
for ($i = 1; $i -le $ahead; $i++) {
    $ok = Push-WithRetry ("commit " + $i + "/" + $ahead)
    if (-not $ok) {
        Log "stopped: the rest stays local, just run this script again"
        exit 1
    }
}

Log ("done. ahead=" + (git rev-list --count origin/main..HEAD) + " dirty=" + ((Get-Changes).Count))
exit 0
