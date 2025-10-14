@echo off
chcp 65001 >nul
echo =======================
echo [0/4] Verificando credenciais seguras...
echo =======================
if "%KEYGEN_LICENSE_BUNDLE%"=="" (
    if "%KEYGEN_LICENSE_BUNDLE_PATH%"=="" (
        if "%KEYGEN_ACCOUNT_ID%"=="" (
            echo [ERRO] Nenhum ACCOUNT_ID foi fornecido. Consulte docs\keygen_cloud_licensing.md.
            exit /b 1
        )
        if "%KEYGEN_PRODUCT_TOKEN%"=="" (
            echo [ERRO] Nenhum PRODUCT_TOKEN foi fornecido. Utilize o bundle seguro ou injete a variavel.
            exit /b 1
        )
    )
)
echo Os segredos do Keygen foram localizados via canal autenticado.

echo =======================
echo [1/4] Limpando build antigo...
echo =======================
rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul
rmdir /s /q dist_final 2>nul
mkdir dist_final

echo =======================
echo [2/4] Ofuscando todos os módulos com PyArmor...
echo =======================
call venv\Scripts\activate
pyarmor gen --recursive --output dist/obfuscated_project main.py

echo =======================
echo [3/4] Copiando módulos adicionais...
echo =======================
:: Copia módulos principais
copy "license_checker.py" "dist\obfuscated_project" /Y
copy "video_processing_logic.py" "dist\obfuscated_project" /Y

:: Copia subpastas de segurança
xcopy "security" "dist\obfuscated_project\security" /E /I /Y
xcopy "tools" "dist\obfuscated_project\tools" /E /I /Y
xcopy "processing" "dist\obfuscated_project\processing" /E /I /Y

echo =======================
echo [4/4] Criando o EXE final com PyInstaller...
echo =======================
pyinstaller ^
--name EditorAutomatico ^
--onefile ^
--windowed ^
--clean ^
--noconsole ^
--distpath ./dist_final ^
--icon="icone.ico" ^
--paths=dist/obfuscated_project ^
--hidden-import platform ^
--hidden-import ttkbootstrap ^
--hidden-import tkinter.messagebox ^
--add-data "ffmpeg;ffmpeg" ^
--add-data "security/runtime_manifest.json;security" ^
--add-data "security/license_authority_keys.json;security" ^
--add-data "dist/obfuscated_project/pyarmor_runtime_000000;pyarmor_runtime_000000" ^
dist/obfuscated_project/main.py

echo =======================
echo ✅ Build concluído!
echo Executável pronto em dist_final\
pause
