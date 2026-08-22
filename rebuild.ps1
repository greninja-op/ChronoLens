Write-Host "Rebuilding ChronoLens..."
Set-Location "$PSScriptRoot"
python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
Write-Host "ChronoLens rebuild complete!"
