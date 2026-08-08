#define MyAppName "山东定额助手"
#define MyAppVersion "0.9.7"
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
VersionInfoVersion=0.9.7.0
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription=山东清单定额检索与 AI 辅助分析安装程序
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}
DefaultDirName={localappdata}\Programs\ShandongQuotaAssistant
DefaultGroupName={#MyAppName}
DisableWelcomePage=yes
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=no
DisableFinishedPage=yes
DisableStartupPrompt=yes
ShowLanguageDialog=no
DirExistsWarning=no
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir={#BuildOutputDir}
OutputBaseFilename={#BuildOutputBaseFilename}
SetupIconFile=..\assets\images\app.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
; Keep the entire authorized catalogue in one installer. The source bundle is
; roughly 4 GB but solid LZMA2 compression keeps the distributable below the
; release-host single-file limit, removing the error-prone .bin workflow.
Compression=lzma2/max
SolidCompression=yes
DiskSpanning=no
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no
SetupLogging=yes
UsePreviousAppDir=yes
UsePreviousLanguage=yes

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Messages]
WizardReady=一键安装
ReadyLabel1=点击“一键安装”，其余步骤将自动完成。
ReadyLabel2a=软件会安装到当前用户目录，创建桌面和开始菜单入口，并在完成后自动启动。
ReadyLabel2b=软件会直接更新现有版本，保留当前用户设置，并在完成后自动启动。
ButtonInstall=一键安装(&I)
InstallingLabel=正在安装完整资料库，请稍候…

[Files]
Source: "{#BuildSourceDir}\*"; DestDir: "{app}"; Excludes: "data\*.sqlite-shm,data\*.sqlite-wal"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: files; Name: "{app}\data\shandong_quota.sqlite-shm"
Type: files; Name: "{app}\data\shandong_quota.sqlite-wal"
Type: dirifempty; Name: "{app}\data"
