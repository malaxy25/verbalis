; Inno Setup script: turns dist\Verbalis\ into a Windows installer.
;
;   iscc /DAppVersion=0.7.2 packaging\verbalis.iss
;
; Installs per user (no admin rights) into %LOCALAPPDATA%\Programs\Verbalis.
; An update simply runs a newer installer: it closes a running Verbalis,
; replaces the program files and keeps everything in ~/.verbalis
; (settings, corrections, models, recordings).

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
; Never change the AppId – Windows uses it to recognise updates and the uninstaller
AppId={{6F3B9A2E-4C1D-4E8B-9F27-5A0D3C7E1B48}
AppName=Verbalis
AppVersion={#AppVersion}
AppVerName=Verbalis {#AppVersion}
AppPublisher=Andrea Frehner
AppPublisherURL=https://github.com/malaxy25/verbalis
AppSupportURL=https://github.com/malaxy25/verbalis/issues
DefaultDirName={localappdata}\Programs\Verbalis
DisableDirPage=yes
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=Verbalis-{#AppVersion}-setup
SetupIconFile=..\src\verbalis\ui\verbalis.ico
UninstallDisplayIcon={app}\Verbalis.exe
UninstallDisplayName=Verbalis
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "german"; MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
; Remove the libraries of the previous version before installing the new ones
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\dist\Verbalis\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Verbalis"; Filename: "{app}\Verbalis.exe"
Name: "{autodesktop}\Verbalis"; Filename: "{app}\Verbalis.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Verbalis.exe"; Description: "{cm:LaunchProgram,Verbalis}"; Flags: nowait postinstall skipifsilent
