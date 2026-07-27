#define MyAppName "山东定额助手"
#define MyAppVersion "0.5.5"
#define MyAppPublisher "山东定额助手"
#define MyAppExeName "山东定额助手.exe"
#ifndef BuildSourceDir
  #define BuildSourceDir "..\release\山东定额助手-便携版"
#endif
#ifndef BuildOutputDir
  #define BuildOutputDir "..\release"
#endif
#ifndef BuildOutputBaseFilename
  #define BuildOutputBaseFilename "山东定额助手-Setup-" + MyAppVersion
#endif

[Setup]
AppId={{DBCE01BE-5A4E-49AE-98B6-831B2580C70F}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
VersionInfoVersion=0.5.5.0
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription=山东清单定额检索与 AI 辅助分析安装程序
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}
DefaultDirName={localappdata}\Programs\ShandongQuotaAssistant
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir={#BuildOutputDir}
OutputBaseFilename={#BuildOutputBaseFilename}
SetupIconFile=..\assets\images\app.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no
SetupLogging=yes
UsePreviousAppDir=yes

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "快捷方式："; Flags: checkedonce

[Files]
Source: "{#BuildSourceDir}\*"; DestDir: "{app}"; Excludes: "data\*.sqlite-shm,data\*.sqlite-wal"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: files; Name: "{app}\data\shandong_quota.sqlite-shm"
Type: files; Name: "{app}\data\shandong_quota.sqlite-wal"
Type: dirifempty; Name: "{app}\data"
