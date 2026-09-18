@echo off
setlocal
cd /d "%~dp0"
call "C:\Program Files\Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvars64.bat"
if errorlevel 1 exit /b 1
set "PROBE_SDK_INC=%~dp0sdk-packages\microsoft.windows.sdk.cpp\c\Include\10.0.28000.0"
set "PROBE_SDK_LIB=%~dp0sdk-packages\microsoft.windows.sdk.cpp.x64\c"
set "INCLUDE=%PROBE_SDK_INC%\ucrt;%PROBE_SDK_INC%\shared;%PROBE_SDK_INC%\um;%INCLUDE%"
set "LIB=%PROBE_SDK_LIB%\ucrt\x64;%PROBE_SDK_LIB%\um\x64;%LIB%"
cl /nologo /std:c++17 /EHsc /W4 /utf-8 /MT /LD transaction-probe.cpp /link /OUT:clipchannel_transaction_probe.aux2 user32.lib


