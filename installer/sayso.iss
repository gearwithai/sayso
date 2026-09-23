; Inno Setup script - builds SaysoSetup.exe from the PyInstaller output in dist\Sayso
#define AppVersion "0.2.0"

[Setup]
AppId={{8F3C2A1E-5B7D-4E9A-9C1F-5A7E2D3B4C60}
AppName=Sayso
AppVersion={#AppVersion}
AppPublisher=GearWithAI
DefaultDirName={localappdata}\Programs\Sayso
DefaultGroupName=Sayso
DisableProgramGroupPage=yes
DisableDirPage=yes
; Per-user install: no admin prompt
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=SaysoSetup-{#AppVersion}
SetupIconFile=..\sayso\sayso.ico
UninstallDisplayIcon={app}\Sayso.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes

[Tasks]
Name: "startup"; Description: "Start Sayso when Windows starts"; GroupDescription: "Options:"
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Options:"; Flags: unchecked

[Files]
Source: "..\dist\Sayso\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\Sayso"; Filename: "{app}\Sayso.exe"
Name: "{autodesktop}\Sayso"; Filename: "{app}\Sayso.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Sayso"; \
  ValueData: """{app}\Sayso.exe"""; Tasks: startup; Flags: uninsdeletevalue

[Run]
Filename: "{app}\Sayso.exe"; Description: "Launch Sayso now"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "taskkill"; Parameters: "/IM Sayso.exe /F"; Flags: runhidden; RunOnceId: "KillSayso"

[UninstallDelete]
; Settings and downloaded models live in %APPDATA%\Sayso
Type: filesandordirs; Name: "{userappdata}\Sayso"
