[CmdletBinding()]
param(
    [Parameter()]
    [string] $VenvPath,

    [Parameter()]
    [string] $PythonExe,

    [Parameter()]
    [string] $ReportPath,

    [Parameter()]
    [switch] $SkipInstall
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false

$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$upstreamRoot = Join-Path $repoRoot "upstream\osworld"
$lockPath = Join-Path $repoRoot "configs\osworld-native-requirements.lock"
$requirementsPath = Join-Path $upstreamRoot "requirements.txt"
$setupPath = Join-Path $upstreamRoot "setup.py"
$torchBackend = "cpu"

foreach ($requiredPath in @($upstreamRoot, $lockPath, $requirementsPath, $setupPath)) {
    if (-not (Test-Path -LiteralPath $requiredPath)) {
        throw "Required OSWorld bootstrap input not found: $requiredPath"
    }
}

if ([string]::IsNullOrWhiteSpace($VenvPath)) {
    $VenvPath = Join-Path $repoRoot ".venv-osworld-native"
}
$VenvPath = [System.IO.Path]::GetFullPath($VenvPath)

function Invoke-NativeChecked {
    param(
        [Parameter(Mandatory)] [string] $Executable,
        [Parameter(Mandatory)] [string[]] $Arguments,
        [Parameter()] [switch] $Capture
    )

    if ($Capture) {
        $nativeOutput = & $Executable @Arguments
    }
    else {
        & $Executable @Arguments
        $nativeOutput = $null
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Native command failed (exit $LASTEXITCODE): $Executable $($Arguments -join ' ')"
    }
    return $nativeOutput
}

$uvCommand = Get-Command "uv.exe" -CommandType Application -ErrorAction Stop
$uvVersionOutput = Invoke-NativeChecked -Executable $uvCommand.Source -Arguments @("--version") -Capture
$uvVersion = ($uvVersionOutput | Select-Object -Last 1).Trim()

function Resolve-Python312 {
    param([string] $Requested)

    if (-not [string]::IsNullOrWhiteSpace($Requested)) {
        if (Test-Path -LiteralPath $Requested -PathType Leaf) {
            return [System.IO.Path]::GetFullPath($Requested)
        }
        $command = Get-Command $Requested -CommandType Application -ErrorAction Stop
        return $command.Source
    }

    $resolved = Invoke-NativeChecked -Executable $uvCommand.Source -Arguments @(
        "python", "find", "3.12"
    ) -Capture
    if ([string]::IsNullOrWhiteSpace($resolved)) {
        throw "uv could not resolve CPython 3.12. Install it with 'uv python install 3.12'."
    }
    return [System.IO.Path]::GetFullPath(($resolved | Select-Object -Last 1).Trim())
}

$basePython = Resolve-Python312 -Requested $PythonExe
$baseVersion = Invoke-NativeChecked -Executable $basePython -Arguments @(
    "-c",
    "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')"
) -Capture
$baseVersion = ($baseVersion | Select-Object -Last 1).Trim()
if (-not $baseVersion.StartsWith("3.12.")) {
    throw "OSWorld authoritative constraints require CPython 3.12; resolved $basePython ($baseVersion)."
}

$venvPython = Join-Path $VenvPath "Scripts\python.exe"
$pyvenvConfig = Join-Path $VenvPath "pyvenv.cfg"
if (-not (Test-Path -LiteralPath $VenvPath)) {
    $venvParent = Split-Path -Parent $VenvPath
    if (-not (Test-Path -LiteralPath $venvParent)) {
        New-Item -ItemType Directory -Path $venvParent -Force | Out-Null
    }
    Write-Host "Creating isolated OSWorld Python environment: $VenvPath"
    Invoke-NativeChecked -Executable $basePython -Arguments @("-m", "venv", $VenvPath)
}

if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
    throw "Existing target is not a Windows Python venv: $VenvPath"
}
if (-not (Test-Path -LiteralPath $pyvenvConfig -PathType Leaf)) {
    throw "Venv metadata is missing: $pyvenvConfig"
}

$pyvenvText = Get-Content -LiteralPath $pyvenvConfig -Raw
if ($pyvenvText -notmatch '(?im)^include-system-site-packages\s*=\s*false\s*$') {
    throw "Refusing non-isolated venv at $VenvPath. Move it aside or choose a fresh -VenvPath; the bootstrap never deletes environments."
}

$venvVersion = Invoke-NativeChecked -Executable $venvPython -Arguments @(
    "-c",
    "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')"
) -Capture
$venvVersion = ($venvVersion | Select-Object -Last 1).Trim()
if (-not $venvVersion.StartsWith("3.12.")) {
    throw "Existing venv is not CPython 3.12: $VenvPath ($venvVersion)."
}

if (-not $SkipInstall) {
    Write-Host "Installing the locked authoritative OSWorld runtime..."
    Invoke-NativeChecked -Executable $uvCommand.Source -Arguments @(
        "pip", "install",
        "--python", $venvPython,
        "--torch-backend", $torchBackend,
        "--link-mode", "copy",
        "--no-deps",
        "--requirement", $lockPath
    )
}

$pipCheck = Invoke-NativeChecked -Executable $venvPython -Arguments @(
    "-m", "pip", "check"
) -Capture
$pipCheckText = ($pipCheck -join [Environment]::NewLine).Trim()

$probeCode = @'
import ast
import hashlib
import importlib.metadata as metadata
import json
import pathlib
import platform
import sys

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

repo_root = pathlib.Path(sys.argv[1]).resolve()
upstream_root = pathlib.Path(sys.argv[2]).resolve()
lock_path = pathlib.Path(sys.argv[3]).resolve()
requirements_path = upstream_root / "requirements.txt"
setup_path = upstream_root / "setup.py"

def file_sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

installed = {}
duplicate_distributions = []
for distribution in metadata.distributions():
    raw_name = distribution.metadata.get("Name")
    if not raw_name:
        continue
    name = canonicalize_name(raw_name)
    previous = installed.get(name)
    if previous is not None and previous != distribution.version:
        duplicate_distributions.append(
            {"name": name, "versions": sorted({previous, distribution.version})}
        )
    installed[name] = distribution.version

installed_lines = [f"{name}=={installed[name]}" for name in sorted(installed)]
installed_payload = ("\n".join(installed_lines) + "\n").encode("utf-8")

lock_requirements = []
for raw_line in lock_path.read_text(encoding="utf-8").splitlines():
    line = raw_line.split("#", 1)[0].strip()
    if line:
        lock_requirements.append(Requirement(line))

lock_violations = []
expected_names = set()
for requirement in lock_requirements:
    if requirement.marker and not requirement.marker.evaluate():
        continue
    name = canonicalize_name(requirement.name)
    expected_names.add(name)
    version = installed.get(name)
    if version is None:
        lock_violations.append(
            {"requirement": str(requirement), "installed": None, "reason": "missing"}
        )
    elif requirement.specifier and not requirement.specifier.contains(
        version, prereleases=True
    ):
        lock_violations.append(
            {
                "requirement": str(requirement),
                "installed": version,
                "reason": "version_mismatch",
            }
        )

allowed_extras = {"pip"}
unexpected_distributions = sorted(set(installed) - expected_names - allowed_extras)

source_requirements = []
for raw_line in requirements_path.read_text(encoding="utf-8").splitlines():
    line = raw_line.split("#", 1)[0].strip()
    if line:
        source_requirements.append(("requirements.txt", Requirement(line)))

setup_tree = ast.parse(setup_path.read_text(encoding="utf-8"), filename=str(setup_path))
setup_requirements = None
for node in ast.walk(setup_tree):
    if not isinstance(node, ast.Call):
        continue
    is_setup = (
        isinstance(node.func, ast.Name) and node.func.id == "setup"
    ) or (
        isinstance(node.func, ast.Attribute) and node.func.attr == "setup"
    )
    if not is_setup:
        continue
    for keyword in node.keywords:
        if keyword.arg == "install_requires":
            setup_requirements = ast.literal_eval(keyword.value)
            break
if not isinstance(setup_requirements, list):
    raise RuntimeError("setup.py install_requires could not be parsed")
source_requirements.extend(
    ("setup.py", Requirement(value)) for value in setup_requirements
)

constraint_violations = []
active_constraint_count = 0
source_counts = {"requirements.txt": 0, "setup.py": 0}
for source, requirement in source_requirements:
    if requirement.marker and not requirement.marker.evaluate():
        continue
    active_constraint_count += 1
    source_counts[source] += 1
    name = canonicalize_name(requirement.name)
    version = installed.get(name)
    if version is None:
        constraint_violations.append(
            {
                "source": source,
                "requirement": str(requirement),
                "installed": None,
                "reason": "missing",
            }
        )
    elif requirement.specifier and not requirement.specifier.contains(
        version, prereleases=True
    ):
        constraint_violations.append(
            {
                "source": source,
                "requirement": str(requirement),
                "installed": version,
                "reason": "version_mismatch",
            }
        )

import psutil
import psutil._psutil_windows as psutil_binary
import cv2
import matplotlib
import numpy
import pandas
import PIL
import torch
from desktop_env.desktop_env import DesktopEnv
from desktop_env.providers.docker.manager import DockerVMManager
from desktop_env.providers.docker.provider import DockerProvider

print(json.dumps(
    {
        "interpreter": {
            "executable": sys.executable,
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
            "prefix": sys.prefix,
            "base_prefix": sys.base_prefix,
        },
        "installed_distributions": {
            "count": len(installed_lines),
            "sha256": hashlib.sha256(installed_payload).hexdigest(),
            "duplicate_distributions": duplicate_distributions,
        },
        "lock_check": {
            "passed": (
                not lock_violations
                and not unexpected_distributions
                and not duplicate_distributions
            ),
            "checked": len(expected_names),
            "allowed_extras": sorted(allowed_extras),
            "unexpected_distributions": unexpected_distributions,
            "violations": lock_violations,
        },
        "upstream_constraints": {
            "passed": not constraint_violations,
            "checked": active_constraint_count,
            "violations": constraint_violations,
            "sources": {
                "requirements.txt": {
                    "path": str(requirements_path),
                    "sha256": file_sha256(requirements_path),
                    "checked": source_counts["requirements.txt"],
                },
                "setup.py": {
                    "path": str(setup_path),
                    "sha256": file_sha256(setup_path),
                    "checked": source_counts["setup.py"],
                },
            },
        },
        "runtime_versions": {
            "numpy": numpy.__version__,
            "torch": torch.__version__,
            "opencv_python_headless": cv2.__version__,
            "matplotlib": matplotlib.__version__,
            "pandas": pandas.__version__,
            "pillow": PIL.__version__,
            "psutil": psutil.__version__,
        },
        "imports": {
            "desktop_env": {
                "module": DesktopEnv.__module__,
                "file": sys.modules[DesktopEnv.__module__].__file__,
            },
            "psutil": {
                "version": psutil.__version__,
                "file": psutil.__file__,
                "binary_file": psutil_binary.__file__,
            },
            "docker_provider": {
                "manager_module": DockerVMManager.__module__,
                "provider_module": DockerProvider.__module__,
            },
        },
    },
    sort_keys=True,
))
'@

$previousPythonPath = $env:PYTHONPATH
try {
    $env:PYTHONPATH = "$repoRoot$([System.IO.Path]::PathSeparator)$upstreamRoot"
    Push-Location $upstreamRoot
    try {
        $probeJson = Invoke-NativeChecked -Executable $venvPython -Arguments @(
            "-c", $probeCode, $repoRoot, $upstreamRoot, $lockPath
        ) -Capture
    }
    finally {
        Pop-Location
    }
}
finally {
    $env:PYTHONPATH = $previousPythonPath
}
$probe = ($probeJson | Select-Object -Last 1) | ConvertFrom-Json

if ($probe.lock_check.passed -ne $true) {
    throw "Installed distributions do not exactly satisfy the OSWorld lock."
}
if ($probe.upstream_constraints.passed -ne $true) {
    throw "Installed distributions violate authoritative OSWorld requirements."
}

$resolvedVenv = [System.IO.Path]::GetFullPath($VenvPath)
$resolvedInterpreter = [System.IO.Path]::GetFullPath([string] $probe.interpreter.executable)
if (-not $resolvedInterpreter.StartsWith($resolvedVenv, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Import probe escaped the target venv: $resolvedInterpreter"
}
$resolvedPsutil = [System.IO.Path]::GetFullPath([string] $probe.imports.psutil.binary_file)
if (-not $resolvedPsutil.StartsWith($resolvedVenv, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "psutil binary escaped the target venv: $resolvedPsutil"
}

if ([string]::IsNullOrWhiteSpace($ReportPath)) {
    $ReportPath = Join-Path $VenvPath "osworld-native-bootstrap-report.json"
}
$ReportPath = [System.IO.Path]::GetFullPath($ReportPath)
$reportParent = Split-Path -Parent $ReportPath
if (-not (Test-Path -LiteralPath $reportParent)) {
    New-Item -ItemType Directory -Path $reportParent -Force | Out-Null
}

$pyvenvSha256 = (Get-FileHash -LiteralPath $pyvenvConfig -Algorithm SHA256).Hash.ToLowerInvariant()
$lockSha256 = (Get-FileHash -LiteralPath $lockPath -Algorithm SHA256).Hash.ToLowerInvariant()
$fingerprintMaterial = @(
    "schema=osworld-native-python-bootstrap-v1",
    "interpreter=$resolvedInterpreter",
    "interpreter_version=$($probe.interpreter.version)",
    "base_prefix=$($probe.interpreter.base_prefix)",
    "pyvenv_cfg_sha256=$pyvenvSha256",
    "lock_sha256=$lockSha256",
    "installed_distributions_sha256=$($probe.installed_distributions.sha256)",
    "requirements_sha256=$($probe.upstream_constraints.sources.'requirements.txt'.sha256)",
    "setup_sha256=$($probe.upstream_constraints.sources.'setup.py'.sha256)",
    "desktop_env=$($probe.imports.desktop_env.file)",
    "psutil_binary=$resolvedPsutil",
    "uv=$uvVersion",
    "torch_backend=$torchBackend"
) -join [Environment]::NewLine
$sha256 = [System.Security.Cryptography.SHA256]::Create()
try {
    $fingerprintBytes = [System.Text.Encoding]::UTF8.GetBytes(
        $fingerprintMaterial + [Environment]::NewLine
    )
    $environmentFingerprint = [Convert]::ToHexString(
        $sha256.ComputeHash($fingerprintBytes)
    ).ToLowerInvariant()
}
finally {
    $sha256.Dispose()
}

$report = [ordered]@{
    schema_version = "osworld-native-python-bootstrap-v1"
    passed = $true
    environment_fingerprint_sha256 = $environmentFingerprint
    repository_root = $repoRoot
    venv_path = $resolvedVenv
    upstream_root = $upstreamRoot
    interpreter = $probe.interpreter
    isolation = [ordered]@{
        include_system_site_packages = $false
        pyvenv_cfg_sha256 = $pyvenvSha256
    }
    lock = [ordered]@{
        path = $lockPath
        sha256 = $lockSha256
        installed_distributions = $probe.installed_distributions
        check = $probe.lock_check
    }
    installer = [ordered]@{
        uv_version = $uvVersion
        torch_backend = $torchBackend
    }
    upstream_constraints = $probe.upstream_constraints
    pip_check = [ordered]@{
        passed = $true
        output = $pipCheckText
    }
    runtime_versions = $probe.runtime_versions
    imports = $probe.imports
}

$reportTemp = "$ReportPath.tmp.$PID"
try {
    $report | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $reportTemp -Encoding utf8
    Move-Item -LiteralPath $reportTemp -Destination $ReportPath -Force
}
finally {
    if (Test-Path -LiteralPath $reportTemp) {
        Remove-Item -LiteralPath $reportTemp -Force
    }
}

Write-Host "OSWorld native Python bootstrap passed."
Write-Host "Interpreter: $resolvedInterpreter ($venvVersion)"
Write-Host "psutil: $($probe.imports.psutil.version) [$resolvedPsutil]"
Write-Host "Upstream constraints: $($probe.upstream_constraints.checked) checked"
Write-Host "Lock SHA256: $lockSha256"
Write-Host "Environment fingerprint: $environmentFingerprint"
Write-Host "Report: $ReportPath"
