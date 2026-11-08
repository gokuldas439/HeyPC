; Builds the Windows installer. Run through packaging\build.ps1.

[Setup]
AppId={{B6E2F3A1-7C4D-4E58-9A21-5D0C8E1F7A42}
AppName=HeyPC
AppVersion=1.3.0
AppPublisher=gokuldas439
AppPublisherURL=https://github.com/gokuldas439/HeyPC
LicenseFile=..\LICENSE
DefaultDirName={localappdata}\Programs\HeyPC
UsePreviousAppDir=no
DefaultGroupName=HeyPC
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
OutputDir=..\build\installer
OutputBaseFilename=HeyPC-Setup
SetupIconFile=jarvis.ico
UninstallDisplayIcon={app}\HeyPC.exe
Compression=lzma2/fast
SolidCompression=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
AppMutex=VoiceJarvisSingleInstance
WizardStyle=modern

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"
Name: "startup"; Description: "Start HeyPC when Windows starts"; Flags: unchecked

[Files]
Source: "..\build\dist\HeyPC\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion
Source: "..\models\silero_vad.onnx"; DestDir: "{app}\models"; Flags: ignoreversion
Source: "..\models\hey_jarvis_v0.1.onnx"; DestDir: "{app}\models"; Flags: ignoreversion
Source: "..\models\melspectrogram.onnx"; DestDir: "{app}\models"; Flags: ignoreversion
Source: "..\models\embedding_model.onnx"; DestDir: "{app}\models"; Flags: ignoreversion
Source: "..\THIRD_PARTY_NOTICES.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion

[InstallDelete]
Type: filesandordirs; Name: "{app}\models\piper"
Type: filesandordirs; Name: "{localappdata}\Programs\Jarvis"

[UninstallDelete]
Type: filesandordirs; Name: "{localappdata}\HeyPC"

[Icons]
Name: "{group}\HeyPC"; Filename: "{app}\HeyPC.exe"
Name: "{group}\HeyPC Settings"; Filename: "{app}\HeyPC.exe"; Parameters: "--settings"
Name: "{group}\Uninstall HeyPC"; Filename: "{uninstallexe}"
Name: "{userdesktop}\HeyPC"; Filename: "{app}\HeyPC.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "HeyPC"; ValueData: """{app}\HeyPC.exe"""; Tasks: startup
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "HeyPC"; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "Jarvis"; Flags: deletevalue

[Run]
Filename: "{app}\HeyPC.exe"; Description: "Start HeyPC now"; Flags: nowait postinstall skipifsilent
