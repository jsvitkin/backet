param(
    [string]$InstallRoot = "$env:LOCALAPPDATA\backet\llama-cpp-vulkan",
    [string]$ModelPath = ""
)

$ErrorActionPreference = "Stop"

Write-Host "llama.cpp Vulkan fallback setup"
Write-Host "Install root: $InstallRoot"

New-Item -ItemType Directory -Force -Path $InstallRoot | Out-Null

Write-Host ""
Write-Host "This script intentionally does not download model weights."
Write-Host "Place a GGUF model in an operator-controlled cache, then start llama-server like this:"
Write-Host ""

if ($ModelPath) {
    Write-Host "llama-server --host 127.0.0.1 --port 8080 --model `"$ModelPath`" --ctx-size 2048 --n-gpu-layers 999"
} else {
    Write-Host "llama-server --host 127.0.0.1 --port 8080 --model H:\Models\your-model.gguf --ctx-size 2048 --n-gpu-layers 999"
}

Write-Host ""
Write-Host "Recommended build path:"
Write-Host "  1. Install Visual Studio Build Tools and Vulkan SDK."
Write-Host "  2. Clone https://github.com/ggml-org/llama.cpp outside the vault."
Write-Host "  3. Build with: cmake -B build -DGGML_VULKAN=ON; cmake --build build --config Release"
Write-Host "  4. Add build\bin\Release to PATH or set BACKET_LLAMA_CPP_SERVER."
