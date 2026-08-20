# Measure EXE startup: launch -> first visible top-level window matching title.
# NOTE: onefile spawns a child process that holds the real window, so we poll
# the whole process table for a window with a matching title.
param(
    [Parameter(Mandatory=$true)][string]$Exe,
    [int]$Runs = 5,
    [string]$Title = "LLC"
)
$sw = [System.Diagnostics.Stopwatch]::new()
$results = [System.Collections.Generic.List[double]]::new()
$baseName = [System.IO.Path]::GetFileNameWithoutExtension($Exe)
for ($i = 0; $i -lt $Runs; $i++) {
    $sw.Restart()
    $p = Start-Process -FilePath $Exe -PassThru
    $deadline = (Get-Date).AddSeconds(120)
    $ready = $false
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Milliseconds 10
        $hit = Get-Process -Name $baseName -ErrorAction SilentlyContinue |
               Where-Object { $_.MainWindowHandle -ne 0 -and $_.MainWindowTitle -match $Title }
        if ($hit) { $ready = $true; break }
    }
    $sw.Stop()
    $results.Add($sw.Elapsed.TotalMilliseconds)
    Write-Host ("run {0}: {1:N0} ms  (window_ready={2})" -f ($i+1), $sw.Elapsed.TotalMilliseconds, $ready)
    Start-Sleep -Milliseconds 600
    Get-Process -Name $baseName -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 400
}
$arr = @($results | Sort-Object)
$min = $arr[0]; $max = $arr[-1]
$med = if ($arr.Count % 2 -eq 1) { $arr[[int]($arr.Count/2)] } else { ($arr[[int]($arr.Count/2)-1] + $arr[[int]($arr.Count/2)]) / 2 }
Write-Host ""
Write-Host ("min    = {0:N0} ms"  -f $min)
Write-Host ("median = {0:N0} ms"  -f $med)
Write-Host ("max    = {0:N0} ms"  -f $max)