# PowerShell script to set up the environment on Windows

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "Setting up Real-Time Meeting Intelligence" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan

# 1. Check Python
if (Get-Command "python" -ErrorAction SilentlyContinue) {
    Write-Host "Python found: $(python --version)" -ForegroundColor Green
} else {
    Write-Host "Error: Python is not installed or not in PATH." -ForegroundColor Red
    Exit 1
}

# 2. Check Node.js
if (Get-Command "node" -ErrorAction SilentlyContinue) {
    Write-Host "Node.js found: $(node -v)" -ForegroundColor Green
} else {
    Write-Host "Error: Node.js is not installed or not in PATH." -ForegroundColor Red
    Exit 1
}

# 3. Create Virtual Environment
Write-Host "`nSetting up Python virtual environment..." -ForegroundColor Cyan
if (!(Test-Path "venv")) {
    python -m venv venv
    Write-Host "Virtual environment created." -ForegroundColor Green
} else {
    Write-Host "Virtual environment already exists." -ForegroundColor Yellow
}

# 4. Install Backend Dependencies
Write-Host "`nInstalling backend dependencies..." -ForegroundColor Cyan
& .\venv\Scripts\pip.exe install --upgrade pip
& .\venv\Scripts\pip.exe install -r backend/requirements.txt

# 5. Install spaCy Models
Write-Host "`nInstalling spaCy language models..." -ForegroundColor Cyan
try {
    & .\venv\Scripts\python.exe -m spacy download en_core_web_sm
    Write-Host "spaCy language model installed." -ForegroundColor Green
} catch {
    Write-Host "Warning: Failed to download spaCy language model. Continuing." -ForegroundColor Yellow
}

# 6. Check Ollama
Write-Host "`nChecking Ollama installation..." -ForegroundColor Cyan
if (Get-Command "ollama" -ErrorAction SilentlyContinue) {
    Write-Host "Ollama found: $(ollama --version)" -ForegroundColor Green
    Write-Host "Pulling local LLM (gemma3:4b)..." -ForegroundColor Cyan
    ollama pull gemma3:4b
} else {
    Write-Host "Ollama is not installed. Please download it from https://ollama.com" -ForegroundColor Yellow
}

# 7. Install Frontend Dependencies
Write-Host "`nInstalling frontend npm dependencies..." -ForegroundColor Cyan
if (Test-Path "frontend") {
    Push-Location frontend
    npm install
    Pop-Location
    Write-Host "Frontend packages installed." -ForegroundColor Green
} else {
    Write-Host "Error: frontend folder not found." -ForegroundColor Red
}

# 8. Initialize SQLite Database
Write-Host "`nInitializing SQLite Database..." -ForegroundColor Cyan
& .\venv\Scripts\python.exe -c "import sys; sys.path.append('backend'); from db.setup import init_db; init_db(); print('Database schema initialized.')"

Write-Host "`n=========================================" -ForegroundColor Green
Write-Host "Setup Complete!" -ForegroundColor Green
Write-Host "=========================================" -ForegroundColor Green
Write-Host "To run the application:"
Write-Host "1. Start Ollama:   ollama serve"
Write-Host "2. Start Backend:  venv\Scripts\python.exe backend\main.py"
Write-Host "3. Start Frontend: cd frontend; npm run dev"
Write-Host "=========================================" -ForegroundColor Green
