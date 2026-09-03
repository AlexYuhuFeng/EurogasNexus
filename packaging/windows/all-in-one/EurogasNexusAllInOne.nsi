Unicode true

!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "x64.nsh"

!ifndef VERSION
  !error "VERSION is required"
!endif
!ifndef OUTPUT_FILE
  !error "OUTPUT_FILE is required"
!endif
!ifndef SOURCE_ROOT
  !error "SOURCE_ROOT is required"
!endif
!ifndef CLIENT_INSTALLER
  !error "CLIENT_INSTALLER is required"
!endif
!ifndef API_IMAGE_ARCHIVE
  !error "API_IMAGE_ARCHIVE is required"
!endif
!ifndef API_IMAGE
  !error "API_IMAGE is required"
!endif

Name "Eurogas Nexus AllInOne"
OutFile "${OUTPUT_FILE}"
InstallDir "$PROGRAMFILES64\Eurogas Nexus AllInOne"
InstallDirRegKey HKLM "Software\Eurogas Nexus\AllInOne" "InstallDir"
RequestExecutionLevel admin
SetCompressor /SOLID lzma
ShowInstDetails show
ShowUninstDetails show
BrandingText "Eurogas Nexus ${VERSION}"

VIProductVersion "${VERSION}.0"
VIAddVersionKey /LANG=1033 "ProductName" "Eurogas Nexus AllInOne"
VIAddVersionKey /LANG=1033 "CompanyName" "Eurogas Nexus"
VIAddVersionKey /LANG=1033 "FileDescription" "Docker-based local evaluation environment"
VIAddVersionKey /LANG=1033 "FileVersion" "${VERSION}"
VIAddVersionKey /LANG=1033 "ProductVersion" "${VERSION}"
VIAddVersionKey /LANG=1033 "LegalCopyright" "Copyright Eurogas Nexus"

!define MUI_ABORTWARNING
!define MUI_FINISHPAGE_RUN "$SYSDIR\WindowsPowerShell\v1.0\powershell.exe"
!define MUI_FINISHPAGE_RUN_TEXT "Open Eurogas Nexus"
!define MUI_FINISHPAGE_RUN_PARAMETERS "-NoProfile -ExecutionPolicy Bypass -File $\"$INSTDIR\scripts\install\windows\Manage-EurogasNexusAllInOne.ps1$\" -Action Open"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"
!insertmacro MUI_LANGUAGE "SimpChinese"

Section "Eurogas Nexus AllInOne" SEC_MAIN
  SectionIn RO
  ${IfNot} ${RunningX64}
    MessageBox MB_ICONSTOP "Eurogas Nexus AllInOne requires 64-bit Windows."
    Abort
  ${EndIf}

  SetOutPath "$INSTDIR\deploy\runtime"
  File "${SOURCE_ROOT}\deploy\runtime\compose.yaml"
  File "${SOURCE_ROOT}\deploy\runtime\Caddyfile"

  SetOutPath "$INSTDIR\scripts\install\windows"
  File "${SOURCE_ROOT}\scripts\install\windows\Install-EurogasNexusServerRuntime.ps1"
  File "${SOURCE_ROOT}\scripts\install\windows\Install-EurogasNexusAllInOne.ps1"
  File "${SOURCE_ROOT}\scripts\install\windows\Manage-EurogasNexusAllInOne.ps1"

  SetOutPath "$INSTDIR\docs"
  File "${SOURCE_ROOT}\docs\deployment\DEPLOYMENT_ROLES-EN.md"
  File "${SOURCE_ROOT}\docs\deployment\DEPLOYMENT_ROLES-CN.md"
  File "${SOURCE_ROOT}\docs\deployment\ALL_IN_ONE_INSTALLER-EN.md"
  File "${SOURCE_ROOT}\docs\deployment\ALL_IN_ONE_INSTALLER-CN.md"

  SetOutPath "$INSTDIR\payload"
  File /oname=Eurogas-Nexus-Client-setup.exe "${CLIENT_INSTALLER}"
  File /oname=eurogas-nexus-api-amd64.tar "${API_IMAGE_ARCHIVE}"

  WriteUninstaller "$INSTDIR\Uninstall-Eurogas-Nexus-AllInOne.exe"
  WriteRegStr HKLM "Software\Eurogas Nexus\AllInOne" "InstallDir" "$INSTDIR"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\EurogasNexusAllInOne" "DisplayName" "Eurogas Nexus AllInOne"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\EurogasNexusAllInOne" "DisplayVersion" "${VERSION}"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\EurogasNexusAllInOne" "Publisher" "Eurogas Nexus"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\EurogasNexusAllInOne" "InstallLocation" "$INSTDIR"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\EurogasNexusAllInOne" "UninstallString" '"$INSTDIR\Uninstall-Eurogas-Nexus-AllInOne.exe"'
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\EurogasNexusAllInOne" "NoModify" 1

  CreateDirectory "$SMPROGRAMS\Eurogas Nexus"
  CreateShortCut "$SMPROGRAMS\Eurogas Nexus\Open Eurogas Nexus.lnk" "$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" '-NoProfile -ExecutionPolicy Bypass -File "$INSTDIR\scripts\install\windows\Manage-EurogasNexusAllInOne.ps1" -Action Open'
  CreateShortCut "$SMPROGRAMS\Eurogas Nexus\Start services.lnk" "$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" '-NoProfile -ExecutionPolicy Bypass -File "$INSTDIR\scripts\install\windows\Manage-EurogasNexusAllInOne.ps1" -Action Start'
  CreateShortCut "$SMPROGRAMS\Eurogas Nexus\Stop services.lnk" "$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" '-NoProfile -ExecutionPolicy Bypass -File "$INSTDIR\scripts\install\windows\Manage-EurogasNexusAllInOne.ps1" -Action Stop'
  CreateShortCut "$SMPROGRAMS\Eurogas Nexus\Runtime status.lnk" "$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" '-NoProfile -ExecutionPolicy Bypass -File "$INSTDIR\scripts\install\windows\Manage-EurogasNexusAllInOne.ps1" -Action Status'
  CreateShortCut "$SMPROGRAMS\Eurogas Nexus\Runtime logs.lnk" "$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" '-NoProfile -ExecutionPolicy Bypass -File "$INSTDIR\scripts\install\windows\Manage-EurogasNexusAllInOne.ps1" -Action Logs'
  CreateShortCut "$SMPROGRAMS\Eurogas Nexus\Uninstall AllInOne.lnk" "$INSTDIR\Uninstall-Eurogas-Nexus-AllInOne.exe"

  DetailPrint "Configuring Docker, PostgreSQL, migrations, API, preview data, and desktop Client..."
  nsExec::ExecToLog '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "$INSTDIR\scripts\install\windows\Install-EurogasNexusAllInOne.ps1" -Action Install -ClientInstallerPath "$INSTDIR\payload\Eurogas-Nexus-Client-setup.exe" -ApiImageArchivePath "$INSTDIR\payload\eurogas-nexus-api-amd64.tar" -ApiImage "${API_IMAGE}"'
  Pop $0
  ${If} $0 != 0
    MessageBox MB_ICONSTOP "Eurogas Nexus deployment failed. Review Eurogas Nexus\Logs\all-in-one-install.log under the Windows ProgramData folder, then rerun this installer. No database password or provider credential is written to the installer log."
    SetErrorLevel $0
    Abort
  ${EndIf}
SectionEnd

Section "Uninstall"
  DetailPrint "Stopping local services. The PostgreSQL data volume will be preserved."
  MessageBox MB_YESNO|MB_ICONEXCLAMATION|MB_DEFBUTTON2 "Permanently delete the Eurogas Nexus PostgreSQL data volume? Choose No to preserve all runtime data for repair or reinstall." IDNO preserve_data
  nsExec::ExecToLog '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "$INSTDIR\scripts\install\windows\Manage-EurogasNexusAllInOne.ps1" -Action PurgeData -ConfirmPurge'
  Pop $1
  ${If} $1 != 0
    MessageBox MB_ICONEXCLAMATION "The requested PostgreSQL data purge failed. Installed application files will be removed; review the runtime log before deleting Docker volumes manually."
  ${EndIf}
  preserve_data:
  nsExec::ExecToLog '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "$INSTDIR\scripts\install\windows\Install-EurogasNexusAllInOne.ps1" -Action Uninstall -UninstallClient'
  Pop $0
  ${If} $0 != 0
    MessageBox MB_ICONEXCLAMATION "Some runtime services could not be stopped. Installed files will be removed, but the PostgreSQL data volume remains preserved."
  ${EndIf}

  Delete "$SMPROGRAMS\Eurogas Nexus\Open Eurogas Nexus.lnk"
  Delete "$SMPROGRAMS\Eurogas Nexus\Start services.lnk"
  Delete "$SMPROGRAMS\Eurogas Nexus\Stop services.lnk"
  Delete "$SMPROGRAMS\Eurogas Nexus\Runtime status.lnk"
  Delete "$SMPROGRAMS\Eurogas Nexus\Runtime logs.lnk"
  Delete "$SMPROGRAMS\Eurogas Nexus\Uninstall AllInOne.lnk"
  RMDir "$SMPROGRAMS\Eurogas Nexus"

  DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\EurogasNexusAllInOne"
  DeleteRegKey HKLM "Software\Eurogas Nexus\AllInOne"
  RMDir /r "$INSTDIR"
SectionEnd
