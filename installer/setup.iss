; installer/setup.iss
; Inno Setup 6 script for Omni Game Linker
;
; Prerequisites:
;   - Inno Setup 6 installed  (https://jrsoftware.org/isinfo.php)
;   - PyInstaller has already produced dist\OmniGameLinker.exe
;
; Build:
;   Open this file in the Inno Setup Compiler and click Build,
;   OR run from command line:
;     "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\setup.iss
;
; Output:
;   installer\Output\OmniGameLinker_Setup_v1.2.0.exe

#define AppName      "Omni Game Linker"
#define AppVersion   "1.2.0"
#define AppPublisher "YourNameHere"
#define AppExeName   "OmniGameLinker.exe"
#define AppMutex     "OmniGameLinkerRunning"

; ── Source ────────────────────────────────────────────────────────────────────
; Path to the PyInstaller output, relative to the repo root.
; The .iss file lives in installer\ so we go up one level with ..\
#define SourceExe "..\dist\" + AppExeName

[Setup]
AppId={{A7F3C2E1-84B0-4D9F-9A3E-1C2D3E4F5A6B}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL=https://github.com/OWNER/omni-game-linker
AppSupportURL=https://github.com/OWNER/omni-game-linker/issues
AppUpdatesURL=https://github.com/OWNER/omni-game-linker/releases

; Default install dir — user can change during install
; {pf64} = C:\Program Files on 64-bit Windows (requires admin)
DefaultDirName={pf64}\{#AppName}

DefaultGroupName={#AppName}
AllowNoIcons=yes

; Output location and filename
OutputDir=Output
OutputBaseFilename=OmniGameLinker_Setup_v{#AppVersion}

; Compression
Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=yes

; Installer appearance
WizardStyle=modern
WizardSizePercent=120
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\{#AppExeName}

; Admin required to write to Program Files
PrivilegesRequired=admin

; Minimum Windows version: Windows 10
MinVersion=10.0

; 64-bit mode
ArchitecturesInstallIn64BitMode=x64

; Prevent running a second instance of the installer while the app is open
AppMutex={#AppMutex}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon";    Description: "{cm:CreateDesktopIcon}";    GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "startmenuicon";  Description: "Create a Start Menu shortcut"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce

[Files]
; Main executable — the single-file PyInstaller output
Source: "{#SourceExe}"; DestDir: "{app}"; Flags: ignoreversion

; If you ever add an assets folder to the bundle, include it like this:
; Source: "..\assets\*"; DestDir: "{app}\assets"; Flags: ignoreversion recursesubdirs

[Icons]
; Start Menu
Name: "{group}\{#AppName}";         Filename: "{app}\{#AppExeName}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"

; Desktop (only if user checked the task)
Name: "{autodesktop}\{#AppName}";   Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
; Offer to launch the app after install
Filename: "{app}\{#AppExeName}"; \
    Description: "{cm:LaunchProgram,{#StringChange(AppName, '&', '&&')}}"; \
    Flags: nowait postinstall skipifsilent

[UninstallRun]
; Nothing extra needed — the app stores its config in %APPDATA%\OmniGameLinker
; which is intentionally left behind on uninstall (user data).
; If you want to offer removal of config during uninstall, add a custom step here.

[Code]
// Detect if the app is currently running and warn the user before installing
function InitializeSetup(): Boolean;
begin
  if CheckForMutexes('{#AppMutex}') then
  begin
    MsgBox('{#AppName} is currently running. Please close it before continuing.',
           mbError, MB_OK);
    Result := False;
  end
  else
    Result := True;
end;

// Same check before uninstall
function InitializeUninstall(): Boolean;
begin
  if CheckForMutexes('{#AppMutex}') then
  begin
    MsgBox('{#AppName} is currently running. Please close it before uninstalling.',
           mbError, MB_OK);
    Result := False;
  end
  else
    Result := True;
end;
