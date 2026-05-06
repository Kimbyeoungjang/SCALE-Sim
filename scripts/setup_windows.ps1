# Windows setup helper for SCALE-Sim
# Run at repository root:
#   powershell -ExecutionPolicy Bypass -File .\scripts\setup_windows.ps1

$ErrorActionPreference = "Stop"

$pythonCandidates = @("py -3", "python", "python3")
$pythonCmd = $null

foreach ($candidate in $pythonCandidates) {
    $parts = $candidate.Split(" ")
    $exe = $parts[0]
    $args = $parts[1..($parts.Count - 1)]
    try {
        & $exe @args -c "import sys; print(sys.version)" | Out-Null
        $pythonCmd = $candidate
        break
    } catch {
        continue
    }
}

if ($null -eq $pythonCmd) {
    throw "Python 3 was not found. Install Python 3 or add it to PATH."
}

Write-Host "Using Python command: $pythonCmd"

$parts = $pythonCmd.Split(" ")
$exe = $parts[0]
$args = $parts[1..($parts.Count - 1)]

& $exe @args -m venv .venv
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -e .

Write-Host "SCALE-Sim Windows setup complete."
