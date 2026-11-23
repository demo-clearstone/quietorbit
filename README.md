# MOA Valuation Package Automation

The application is in [`new-app`](new-app/README.md).

python -m PyInstaller --noconfirm --clean --onedir --console --name MOAValuationPackage --distpath "dist\windows\publish" --workpath "build\windows" --specpath "build\windows" --add-data "config;config" --add-data "templates;templates" --add-data "logs-updation.xlsx;." --collect-all pymupdf --collect-all uvicorn --hidden-import uvicorn.protocols.http.h11_impl --hidden-import uvicorn.lifespan.on main.py

-r requirements-run.txt
pyinstaller>=6.0

