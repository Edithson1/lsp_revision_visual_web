param(
    [switch]$NoBrowser,
    [string]$ProjectPath = (Split-Path -Parent $PSScriptRoot),
    [ValidateRange(1,65535)][int]$Port = 8765,
    [string]$CsvPath,
    [string]$TemplatePath,
    [string]$Ffmpeg
)
$ErrorActionPreference = 'Stop'
$appFolder = $PSScriptRoot
$projectFolder = [System.IO.Path]::GetFullPath($ProjectPath)
$appUrl = 'http://127.0.0.1:{0}' -f $Port

try {
    $existing = Invoke-RestMethod -Uri "$appUrl/api/catalog" -TimeoutSec 2
    if ($existing.requiredCount -eq 38 -and $existing.sourceCount -eq 290 -and $existing.appVersion -eq 2 -and $existing.paths.originals -eq (Join-Path $projectFolder 'originales_organizados')) {
        if (-not $NoBrowser) { Start-Process $appUrl }
        exit 0
    }
} catch {}

$pythonPrefix = ''
$pythonCommand = Get-Command py.exe -ErrorAction SilentlyContinue
$projectPython = Join-Path $projectFolder 'simulador_escenarios_lsp/.venv/Scripts/python.exe'
$cachedPython = Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
if ($pythonCommand) { $pythonExe = $pythonCommand.Source; $pythonPrefix = '-3 ' }
elseif (Test-Path -LiteralPath $projectPython) { $pythonExe = $projectPython }
elseif ($pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue) { $pythonExe = $pythonCommand.Source }
elseif (Test-Path -LiteralPath $cachedPython) { $pythonExe = $cachedPython }
else { throw 'Se necesita Python 3.10 o posterior. Instálalo y vuelve a ejecutar el lanzador.' }

$dataFolder = Join-Path $appFolder 'data'
$null = New-Item -ItemType Directory -Path $dataFolder -Force
$serverScript = Join-Path $appFolder 'server.py'
$serverArguments = $pythonPrefix + ('"{0}" --port {1} --project "{2}"' -f $serverScript, $Port, $projectFolder)
if ($CsvPath) { $serverArguments += ' --csv "{0}"' -f ([System.IO.Path]::GetFullPath($CsvPath)) }
if ($TemplatePath) { $serverArguments += ' --template "{0}"' -f ([System.IO.Path]::GetFullPath($TemplatePath)) }
if ($Ffmpeg) { $serverArguments += ' --ffmpeg "{0}"' -f ([System.IO.Path]::GetFullPath($Ffmpeg)) }
$serverProcess = Start-Process -FilePath $pythonExe -ArgumentList $serverArguments -WorkingDirectory $appFolder -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $dataFolder 'servidor.log') -RedirectStandardError (Join-Path $dataFolder 'servidor_error.log')

for ($attempt = 0; $attempt -lt 30; $attempt++) {
    Start-Sleep -Milliseconds 300
    try {
        $ready = Invoke-RestMethod -Uri "$appUrl/api/catalog" -TimeoutSec 2
        if ($ready.requiredCount -eq 38 -and $ready.sourceCount -eq 290 -and $ready.appVersion -eq 2) {
            if (-not $NoBrowser) { Start-Process $appUrl }
            exit 0
        }
    } catch {}
    if ($serverProcess.HasExited) { break }
}
throw "No se pudo iniciar la web. Revisa $dataFolder\servidor_error.log y comprueba que el puerto $Port esté disponible."
