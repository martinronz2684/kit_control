; Setup für Kit Control Desktop (PC-Gegenstück zu Sintratec Central).
; Bauen: ISCC.exe /DAppVer=1.0.0 KitControl.iss   (vorher PyInstaller-Ausgabe in ..\dist\KitControl)

#ifndef AppVer
  #define AppVer "1.0.0"
#endif

[Setup]
AppId={{B4C1E0F2-7A3D-4C59-8E21-5D0F6A9B3C77}
AppName=Kit Control
AppVersion={#AppVer}
AppVerName=Kit Control {#AppVer}
AppPublisher=Kit Control
DefaultDirName={localappdata}\Programs\KitControl
DefaultGroupName=Kit Control
DisableProgramGroupPage=yes
DisableDirPage=auto
PrivilegesRequired=lowest
OutputDir=..\..\dist
OutputBaseFilename=KitControl-Setup
SetupIconFile=kitcontrol.ico
UninstallDisplayIcon={app}\KitControl.exe
UninstallDisplayName=Kit Control
WizardStyle=modern
WizardImageFile=wizard-100.bmp,wizard-150.bmp,wizard-200.bmp
WizardSmallImageFile=small-100.bmp,small-150.bmp,small-200.bmp
WizardImageStretch=no
WizardImageBackColor=$110E0C
Compression=lzma2/max
SolidCompression=yes
CloseApplications=yes
ChangesAssociations=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "de"; MessagesFile: "compiler:Languages\German.isl"

[Messages]
de.WelcomeLabel1=Kit Control
de.WelcomeLabel2=Kit Control ist das Gegenstück zu Sintratec Central für deinen Sintratec Kit: Bauteile platzieren, mit eigenen Pulverprofilen slicen, Job per WLAN zum Kit Control am Pi schicken und den Druck live verfolgen.%n%nSintratec Central bleibt unverändert installiert.

[Tasks]
Name: "desktopicon"; Description: "Verknüpfung auf dem Desktop"; GroupDescription: "Zusätzlich:"
Name: "stlassoc"; Description: "STL-Dateien mit Kit Control öffnen (Rechtsklick > Öffnen mit)"; GroupDescription: "Zusätzlich:"

[Files]
Source: "..\..\dist\KitControl\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; alte Programmdateien entfernen, damit nach Updates nichts Veraltetes liegen bleibt (Profile liegen in %APPDATA%)
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{group}\Kit Control"; Filename: "{app}\KitControl.exe"
Name: "{group}\Kit Control deinstallieren"; Filename: "{uninstallexe}"
Name: "{userdesktop}\Kit Control"; Filename: "{app}\KitControl.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Classes\KitControl.stl"; ValueType: string; ValueName: ""; ValueData: "3D-Modell für Kit Control"; Flags: uninsdeletekey; Tasks: stlassoc
Root: HKCU; Subkey: "Software\Classes\KitControl.stl\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\KitControl.exe,0"; Tasks: stlassoc
Root: HKCU; Subkey: "Software\Classes\KitControl.stl\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\KitControl.exe"" ""%1"""; Tasks: stlassoc
Root: HKCU; Subkey: "Software\Classes\.stl\OpenWithProgids"; ValueType: string; ValueName: "KitControl.stl"; ValueData: ""; Flags: uninsdeletevalue; Tasks: stlassoc
Root: HKCU; Subkey: "Software\Classes\.kcp"; ValueType: string; ValueName: ""; ValueData: "KitControl.kcp"; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\KitControl.kcp"; ValueType: string; ValueName: ""; ValueData: "Kit-Control-Projekt"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\KitControl.kcp\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\KitControl.exe,0"
Root: HKCU; Subkey: "Software\Classes\KitControl.kcp\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\KitControl.exe"" ""%1"""

[Run]
Filename: "{app}\KitControl.exe"; Description: "Kit Control starten"; Flags: nowait postinstall skipifsilent
; nach einem Update aus der App heraus (stilles Setup) die App wieder öffnen
Filename: "{app}\KitControl.exe"; Flags: nowait; Check: WizardSilent
