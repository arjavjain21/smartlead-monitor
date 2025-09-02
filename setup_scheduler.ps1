# PowerShell script to set up Windows Task Scheduler for Smartlead Monitor
# Run this script as Administrator

$TaskName = "SmartleadAccountMonitor"
$TaskDescription = "Monitor Smartlead accounts for disconnections hourly"
$ScriptPath = Join-Path $PWD "run_monitor.bat"
$WorkingDirectory = $PWD

# Check if running as administrator
if (-NOT ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator"))
{
    Write-Host "This script needs to be run as Administrator." -ForegroundColor Red
    Write-Host "Please right-click and select 'Run as Administrator'" -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}

# Check if task already exists
$existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue

if ($existingTask) {
    Write-Host "Task '$TaskName' already exists." -ForegroundColor Yellow
    $response = Read-Host "Do you want to replace it? (y/n)"
    if ($response -ne 'y') {
        Write-Host "Setup cancelled." -ForegroundColor Yellow
        exit 0
    }
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

# Create the scheduled task action
$Action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$ScriptPath`"" -WorkingDirectory $WorkingDirectory

# Create the trigger (every hour at minute 5)
$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).Date -RepetitionInterval (New-TimeSpan -Hours 1) -RepetitionDuration (New-TimeSpan -Days 365)

# Create the settings
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -RunOnlyIfNetworkAvailable -MultipleInstances IgnoreNew

# Create the principal (run whether user is logged in or not)
$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType S4U -RunLevel Limited

# Register the scheduled task
try {
    Register-ScheduledTask -TaskName $TaskName -Description $TaskDescription -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal
    
    Write-Host "`n========================================" -ForegroundColor Green
    Write-Host "Task Scheduler setup completed!" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "Task Name: $TaskName"
    Write-Host "Schedule: Every hour at minute 5"
    Write-Host "Script: $ScriptPath"
    Write-Host ""
    Write-Host "You can manage this task in Task Scheduler (taskschd.msc)" -ForegroundColor Cyan
    Write-Host ""
    
    $runNow = Read-Host "Do you want to run the task now for testing? (y/n)"
    if ($runNow -eq 'y') {
        Start-ScheduledTask -TaskName $TaskName
        Write-Host "Task started. Check the logs in the audit_logs folder." -ForegroundColor Green
    }
} catch {
    Write-Host "Error creating scheduled task: $_" -ForegroundColor Red
    exit 1
}

Read-Host "`nPress Enter to exit"
