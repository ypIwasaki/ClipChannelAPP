@echo off
setlocal
if "%AVIUTL2_SDK%"=="" (
  echo Set AVIUTL2_SDK to the directory containing plugin2.h.
  exit /b 1
)
if "%WIN_SDK_PACKAGES%"=="" (
  echo Set WIN_SDK_PACKAGES to the directory containing microsoft.windows.sdk.cpp.
  exit /b 1
)
call "C:\Program Files\Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvars64.bat"
if errorlevel 1 exit /b 1
set "WIN_SDK_INC=%WIN_SDK_PACKAGES%\microsoft.windows.sdk.cpp\c\Include\10.0.28000.0"
set "WIN_SDK_LIB=%WIN_SDK_PACKAGES%\microsoft.windows.sdk.cpp.x64\c"
set "INCLUDE=%WIN_SDK_INC%\ucrt;%WIN_SDK_INC%\shared;%WIN_SDK_INC%\um;%INCLUDE%"
set "LIB=%WIN_SDK_LIB%\ucrt\x64;%WIN_SDK_LIB%\um\x64;%LIB%"
cl /nologo /std:c++17 /EHsc /W4 /wd4828 /utf-8 /MT /LD /I"%AVIUTL2_SDK%" "%~dp0subtitle-import.cpp" comdlg32.lib user32.lib /link /OUT:"%~dp0clipchannel_subtitles.aux2"
