# Launch EXE, wait for a visible window with title, capture a bitmap of that
# window (incl. child paints), save to PNG for review.
param(
    [Parameter(Mandatory=$true)][string]$Exe,
    [Parameter(Mandatory=$true)][string]$Out,
    [string]$Title = "LLC"
)
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Win32 {
    [DllImport("user32.dll")]
    public static extern bool GetWindowRect(IntPtr h, out RECT r);
    [DllImport("user32.dll")]
    public static extern bool SetForegroundWindow(IntPtr h);
    [DllImport("user32.dll")]
    public static extern bool PrintWindow(IntPtr h, IntPtr dc, uint flags);
    [StructLayout(LayoutKind.Sequential)]
    public struct RECT { public int L, T, R, B; }
}
"@
$base = [System.IO.Path]::GetFileNameWithoutExtension($Exe)
$deadline = (Get-Date).AddSeconds(60)
$found = $null
$p = Start-Process -FilePath $Exe -PassThru
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Milliseconds 20
    $procs = Get-Process -Name $base -ErrorAction SilentlyContinue
    foreach ($pr in $procs) {
        if ($pr.MainWindowHandle -ne 0 -and $pr.MainWindowTitle -match $Title) { $found = $pr; break }
    }
    if ($found) { break }
}
if (-not $found) { Write-Host "FAIL: no window"; exit 1 }
Start-Sleep -Milliseconds 800   # let first paint / animations settle
# bring to front so CW_PRINTWINDOW captures up-to-date content
[Win32]::SetForegroundWindow($found.MainWindowHandle) | Out-Null
$rect = New-Object Win32+RECT
[Win32]::GetWindowRect($found.MainWindowHandle, [ref]$rect) | Out-Null
$w = $rect.R - $rect.L; $h = $rect.B - $rect.T
$bmp = New-Object System.Drawing.Bitmap $w, $h
$g = [System.Drawing.Graphics]::FromImage($bmp)
$hdc = $g.GetHdc()
[Win32]::PrintWindow($found.MainWindowHandle, $hdc, 2) | Out-Null   # PW_RENDERFULLCONTENT
$g.ReleaseHdc($hdc)
$g.Dispose()
$bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
$bmp.Dispose()
Write-Host ("PASS: captured {0}x{1} -> {2}" -f $w, $h, $Out)
Get-Process -Name $base -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
exit 0