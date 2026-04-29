$ErrorActionPreference = "Stop"

$ModRoot = Split-Path -Parent $PSScriptRoot
$Managed = Join-Path (Split-Path -Parent (Split-Path -Parent $ModRoot)) "RimWorldWin64_Data\Managed"
$Out = Join-Path $ModRoot "Assemblies\RimworldPython.dll"
$Csc = "$env:WINDIR\Microsoft.NET\Framework64\v4.0.30319\csc.exe"

& $Csc `
  /target:library `
  /nologo `
  /out:$Out `
  /reference:"$Managed\Assembly-CSharp.dll" `
  /reference:"$Managed\Unity.Mathematics.dll" `
  /reference:"$Managed\UnityEngine.dll" `
  /reference:"$Managed\UnityEngine.CoreModule.dll" `
  "$PSScriptRoot\PythonBootstrap.cs"
