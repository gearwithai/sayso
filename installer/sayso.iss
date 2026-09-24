; Inno Setup script - builds SaysoSetup.exe from the PyInstaller output in dist\Sayso
#ifndef AppVersion
  #define AppVersion "0.5.2"
#endif

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
OutputBaseFilename=SaysoSetup
SetupIconFile=..\sayso\sayso.ico
UninstallDisplayIcon={app}\Sayso.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
DisableWelcomePage=yes
DisableReadyPage=yes
AppPublisherURL=https://gearwithai.github.io/sayso/
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=force

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Options:"; Flags: unchecked

[Files]
Source: "..\dist\Sayso\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\Sayso"; Filename: "{app}\Sayso.exe"
Name: "{autodesktop}\Sayso"; Filename: "{app}\Sayso.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Sayso.exe"; Description: "Launch Sayso now"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "taskkill"; Parameters: "/IM Sayso.exe /F"; Flags: runhidden; RunOnceId: "KillSayso"

[UninstallDelete]
; Settings and downloaded models live in %APPDATA%\Sayso
Type: filesandordirs; Name: "{userappdata}\Sayso"

[Code]
// Close a running Sayso before files are replaced (it lives in the tray, so ask it firmly)
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Code: Integer;
begin
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM Sayso.exe', '', SW_HIDE, ewWaitUntilTerminated, Code);
  Sleep(500);
  Result := '';
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    RegDeleteValue(HKEY_CURRENT_USER, 'Software\Microsoft\Windows\CurrentVersion\Run', 'Sayso');
end;
