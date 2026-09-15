param([Parameter(Mandatory=$true)][int]$DesktopProcessId)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient
$taskProcess = Get-Process -Id $DesktopProcessId
if ($taskProcess.ProcessName -ne 'PBIDesktop') { throw 'Target process is not Power BI Desktop.' }
$processCondition = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty, $DesktopProcessId)
$taskWindow = [System.Windows.Automation.AutomationElement]::RootElement.FindFirst([System.Windows.Automation.TreeScope]::Children, $processCondition)
if ($null -eq $taskWindow) { throw 'The matching Desktop window is unavailable.' }
$nameCondition = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty, 'Refresh')
$typeCondition = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Button)
$buttonCondition = New-Object System.Windows.Automation.AndCondition($nameCondition, $typeCondition)
$refreshButton = $taskWindow.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $buttonCondition)
if ($null -eq $refreshButton -or -not $refreshButton.Current.IsEnabled) {
    throw 'The enabled English-language Refresh command was not found. Load data in Desktop and verify again without native refresh.'
}
$refreshButton.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
@{status='invoked'; mechanism='native_accessibility_command'; pid=$DesktopProcessId; detail='Refresh requested once. Runtime DAX checks must confirm loaded results.'} | ConvertTo-Json -Compress
