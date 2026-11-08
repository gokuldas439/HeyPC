; Builds the Windows installer. Run through packaging\build.ps1.

[Setup]
AppId={{B6E2F3A1-7C4D-4E58-9A21-5D0C8E1F7A42}
AppName=Jarvis
AppVersion=1.1.0
AppPublisher=gokuldas439
AppPublisherURL=https://github.com/gokuldas439/voice-jarvis
LicenseFile=..\LICENSE
DefaultDirName={localappdata}\Programs\Jarvis
DefaultGroupName=Jarvis
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
OutputDir=..\build\installer
OutputBaseFilename=Jarvis-Setup
SetupIconFile=jarvis.ico
UninstallDisplayIcon={app}\Jarvis.exe
Compression=lzma2/fast
SolidCompression=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
AppMutex=VoiceJarvisSingleInstance
WizardStyle=modern

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"
Name: "startup"; Description: "Start Jarvis when Windows starts"; Flags: unchecked

[Files]
Source: "..\build\dist\Jarvis\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion
Source: "..\models\*"; DestDir: "{app}\models"; Flags: recursesubdirs ignoreversion
Source: "..\THIRD_PARTY_NOTICES.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion

[InstallDelete]
Type: filesandordirs; Name: "{app}\models\piper"

[Icons]
Name: "{group}\Jarvis"; Filename: "{app}\Jarvis.exe"
Name: "{group}\Jarvis Settings"; Filename: "{app}\Jarvis.exe"; Parameters: "--settings"
Name: "{group}\Uninstall Jarvis"; Filename: "{uninstallexe}"
Name: "{userdesktop}\Jarvis"; Filename: "{app}\Jarvis.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Jarvis"; ValueData: """{app}\Jarvis.exe"""; Tasks: startup
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "Jarvis"; Flags: uninsdeletevalue

[Run]
Filename: "{app}\Jarvis.exe"; Description: "Start Jarvis now"; Flags: nowait postinstall skipifsilent
