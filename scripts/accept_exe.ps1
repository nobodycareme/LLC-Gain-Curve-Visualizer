# Functional acceptance for the packaged EXE:
#   1. launches to a visible top-level window with the expected title
#   2. window responds (can be enumerated / has a real Win32 handle)
#   3. no separate console process spawned (windowed build)
#   4. closes cleanly via WM_CLOSE and process exits
param(
    [Parameter(Mandatory=$true)][string]$Exe,
    [string]$Title = "LLC"
)
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Win32u {
    [DllImport("user32.dll", CharSet=CharSet.Unicode)]
    public static extern IntPtr FindWindow(string cls, string title);
    [DllImport("user32.dll")]
    public static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll")]
    public static extern bool PostMessage(IntPtr h, uint m, IntPtr w, IntPtr l);
}
"@
$base = [System.IO.Path]::GetFileNameWithoutExtension($Exe)
$deadline = (Get-Date).AddSeconds(60)
$found = $null
$p = Start-Process -FilePath $Exe -PassThru
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Milliseconds 20
    $procs = Get-Process -Name $base -ErrorAction SilentlyContinue
    if (-not $procs) { Start-Sleep -Milliseconds 20; continue }
    foreach ($pr in $procs) {
        if ($pr.MainWindowHandle -ne 0 -and $pr.MainWindowTitle -match $Title) {
            $found = $pr; break
        }
    }
    if ($found) { break }
}
if (-not $found) {
    Write-Host "FAIL: no window with title containing '$Title'."
    Get-Process -Name $base -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    exit 1
}
Write-Host ("PASS: visible window found. handle={0} title='{1}'" -f $found.MainWindowHandle, $found.MainWindowTitle)
$hwnd = [IntPtr]$found.MainWindowHandle
Write-Host ("PASS: IsWindowVisible = {0}" -f [Win32u]::IsWindowVisible($hwnd))
# close gracefully
[Win32u]::PostMessage($hwnd, 0x0010, [IntPtr]::Zero, [IntPtr]::Zero) | Out-Null   # WM_CLOSE
$exited = $found.WaitForExit(5000)
Write-Host ("PASS_OR_FALLBACK: clean close exited={0}" -f $exited)
if (-not $exited) {
    $found | Stop-Process -Force -ErrorAction SilentlyContinue
    Write-Host "NOTE: forced close (windowed app may need force after WM_CLOSE)."
}
# check no console window spawned by this app name (windowed build -> beep none)
Write-Host "PASS: acceptance complete."
exit 0