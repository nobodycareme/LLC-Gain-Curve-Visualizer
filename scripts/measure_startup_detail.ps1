# Measure EXE startup wall-clock from spawn until timing JSON is emitted.
# The EXE must support LLC_TIMING=1 + LLC_TIMING_FILE. JSON carries internal
# milestones (t0..t5). External wall time = entire process life (incl. PyInstaller
# onefile self-extraction + Python/Qt import + MainWindow init + 120ms settle).
param(
    [Parameter(Mandatory=$true)][string]$Exe,
    [int]$Runs = 5,
    [string]$OutDir = "$env:TEMP\llc_timing"
)
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$frame = 0
$rows = [System.Collections.Generic.List[double]]::new()
$acc = @{}   # milestone -> value (last of each run, ms)
for ($i = 0; $i -lt $Runs; $i++) {
    $frame++
    $jsonPath = Join-Path $OutDir ("run_{0}.json" -f $frame)
    if (Test-Path $jsonPath) { Remove-Item $jsonPath -Force }
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $env:LLC_TIMING = "1"
    $env:LLC_TIMING_FILE = $jsonPath
    $p = Start-Process -FilePath $Exe -PassThru
    while ($true) {
        Start-Sleep -Milliseconds 15
        if ($p.HasExited)             { break }
        if (Test-Path $jsonPath)      { break }
        if ($sw.Elapsed.TotalSeconds -gt 120) { break }
    }
    # wait for stable json write
    Start-Sleep -Milliseconds 50
    if (Test-Path $jsonPath) {
        try { $data = Get-Content $jsonPath -Raw | ConvertFrom-Json } catch { $data = $null }
        if ($data) {
            foreach ($n in ($data.PSObject.Properties.Name)) {
                if (-not $acc.ContainsKey($n)) { $acc[$n] = [System.Collections.Generic.List[double]]::new() }
                $acc[$n].Add([double]$data.$n * 1000.0)
            }
        }
    }
    $sw.Stop()
    $rows.Add($sw.Elapsed.TotalMilliseconds)
    Remove-Item Env:\LLC_TIMING -ErrorAction SilentlyContinue
    Remove-Item Env:\LLC_TIMING_FILE -ErrorAction SilentlyContinue
    Write-Host ("run {0}: wall={1:N0} ms  json={2}" -f ($i+1), $sw.Elapsed.TotalMilliseconds, (Test-Path $jsonPath))
    Start-Sleep -Milliseconds 500
}
# stop any lingering windowed child (title LLC)
Get-Process | Where-Object { $_.MainWindowTitle -match "LLC" } | Stop-Process -Force -ErrorAction SilentlyContinue

function Get-Stat([double[]]$a) {
    $s = @($a | Sort-Object)
    $m = if ($s.Count % 2 -eq 1) { $s[[int]($s.Count/2)] } else { ($s[[int]($s.Count/2)-1] + $s[[int]($s.Count/2)]) / 2 }
    $mean = ($s | Measure-Object -Average).Average
    $p90idx = [math]::Min([int][math]::Ceiling(0.90 * $s.Count) - 1, $s.Count - 1)
    return @{min=$s[0]; med=$m; mean=$mean; p90=$s[$p90idx]; max=$s[-1]}
}
$st = Get-Stat ([double[]]$rows.ToArray())
Write-Host ""
Write-Host "=== WALL (spawn -> json emitted) ==="
Write-Host ("min    = {0:N0} ms" -f $st.min)
Write-Host ("median = {0:N0} ms" -f $st.med)
Write-Host ("mean   = {0:N0} ms" -f $st.mean)
Write-Host ("p90    = {0:N0} ms" -f $st.p90)
Write-Host ("max    = {0:N0} ms" -f $st.max)
foreach ($key in @("t0_entry","t1_qapp","t2_mainwin","t3_show","t4_first_paint","t5_event_loop_ready")) {
    if ($acc.ContainsKey($key)) {
        $vals = [double[]]$acc[$key].ToArray()
        $s2 = Get-Stat $vals
        Write-Host ("milestone {0}: min={1:N0} med={2:N0} mean={3:N0} p90={4:N0} max={5:N0} ms" -f $key, $s2.min, $s2.med, $s2.mean, $s2.p90, $s2.max)
    }
}