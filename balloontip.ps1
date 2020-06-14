Add-Type -AssemblyName System.Windows.Forms
$global:balloon = New-Object System.Windows.Forms.NotifyIcon
$path = (Get-Process -id $pid).Path
#$path = "C:\Program Files\Sublime Text 3\sublime_text.exe"
$balloon.Icon            = [System.Drawing.Icon]::ExtractAssociatedIcon($path)
$balloon.BalloonTipIcon  = [System.Windows.Forms.ToolTipIcon]::Warning
$balloon.BalloonTipText  = $Args[0]
$balloon.BalloonTipTitle = "REMINDER: @ " + $Args[1]
$balloon.Visible         = $true
$balloon.ShowBalloonTip(5000)