param(
    [string]$LogLevel = "info",
    [string]$Pool = "solo"
)

$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

$Workers = @(
    @{
        Title = "arxiv-worker-pdf-download"
        Queue = "paper.pdf_download"
        Name = "pdf-download@%h"
    },
    @{
        Title = "arxiv-worker-parsing"
        Queue = "paper.parsing"
        Name = "parsing@%h"
    },
    @{
        Title = "arxiv-worker-chunking"
        Queue = "paper.chunking"
        Name = "chunking@%h"
    },
    @{
        Title = "arxiv-worker-indexing"
        Queue = "paper.indexing"
        Name = "indexing@%h"
    }
)

foreach ($Worker in $Workers) {
    $Command = @"
`$Host.UI.RawUI.WindowTitle = '$($Worker.Title)'
Set-Location -LiteralPath '$ProjectRoot'
`$env:PYTHONPATH = 'src'
celery -A worker.celery_app:celery_app worker -Q $($Worker.Queue) --pool=$Pool --loglevel=$LogLevel -n $($Worker.Name)
"@

    Start-Process powershell.exe -ArgumentList @(
        "-NoExit",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        $Command
    )
}

Write-Host "Started 4 Celery worker windows:"
foreach ($Worker in $Workers) {
    Write-Host "- $($Worker.Queue) as $($Worker.Name)"
}
